import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from app.config import Settings
from app.embedding_profiles import QWEN_DIGEST, QWEN_MODEL, QWEN_SPACE, QUERY_PREFIX
from app.local_embeddings import OllamaEmbeddingProvider, BATCH_SIZE
from app.models import EvidenceSegment, RetrievalHit
from app.providers import grounded_hits
from app.retrieval import fuse_and_rerank
from app.sources.contracts import SourceError
from uuid import uuid4


@pytest.fixture
def embedding_server():
    state = {'calls': [], 'model': QWEN_MODEL, 'digest': QWEN_DIGEST, 'tokens': 12}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            state['calls'].append(self.path)
            self.send_response(200); self.end_headers()
            payload = {'models': [] if state.get('missing') else [{'name': state['model'], 'digest': state['digest']}]}
            self.wfile.write(json.dumps(payload).encode())
        def do_POST(self):
            state['calls'].append(self.path)
            state['request'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(state.get('status', 200))
            if state.get('redirect'): self.send_header('Location', 'http://remote.example/embeddings')
            self.end_headers()
            vector = state.get('vector', [1.] + [0.] * 1023)
            payload = {'model': state.get('response_model', QWEN_MODEL), 'embeddings': [vector for _ in state['request']['input']], 'prompt_eval_count': state['tokens']}
            if state.get('wrong_count'): payload['embeddings'] = []
            self.wfile.write(state.get('raw', json.dumps(payload).encode()))
            if state.get('swap'): state['digest'] = 'a' * 64
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True); thread.start()
    try:
        yield OllamaEmbeddingProvider(f'http://127.0.0.1:{server.server_port}'), state
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def test_native_batch_query_instruction_digest_and_usage(embedding_server, monkeypatch):
    provider, state = embedding_server
    monkeypatch.setenv('HTTP_PROXY', 'http://unreachable.example:80')
    output = provider.embed_query('Servis çalışıyor mu?')
    assert output.input_tokens == 12 and len(output.vectors[0]) == 1024
    assert state['calls'] == ['/api/tags', '/api/embed', '/api/tags']
    assert state['request']['input'] == [QUERY_PREFIX + 'Servis çalışıyor mu?']
    assert state['request']['truncate'] is False and state['request']['keep_alive'] == 0
    assert provider.space_id == QWEN_SPACE and provider.model_digest == QWEN_DIGEST
    documents = ['literal transcript', 'another transcript']
    assert len(provider.embed_documents(documents).vectors) == 2
    assert state['request']['input'] == documents
    assert '/api/pull' not in state['calls']


@pytest.mark.parametrize('patch', [
    {'vector': [1.] * 64}, {'vector': [0.] * 1024}, {'vector': [True] + [0.] * 1023},
    {'vector': [float('nan')] + [0.] * 1023}, {'vector': [float('inf')] + [0.] * 1023},
    {'vector': [10**300] + [0.] * 1023}, {'wrong_count': True}, {'tokens': True}, {'tokens': -1},
    {'response_model': 'cloud'}, {'raw': b'x'*400001}, {'raw': b'{"embeddings":'},
])
def test_invalid_vectors_or_usage_are_never_indexed(embedding_server, patch):
    provider, state = embedding_server; state.update(patch)
    with pytest.raises(SourceError) as error: provider.embed_query('health')
    assert error.value.code == 'invalid_embeddings'
    assert provider.capacity.acquire(blocking=False); provider.capacity.release()


@pytest.mark.parametrize('patch,code', [
    ({'missing': True}, 'local_embeddings_not_installed'),
    ({'digest': 'a'*64}, 'embedding_model_changed'),
    ({'swap': True}, 'embedding_model_changed'),
    ({'status': 503}, 'local_embeddings_unavailable'),
    ({'status': 400}, 'embedding_input_limit'),
    ({'status': 302, 'redirect': True}, 'local_embeddings_unavailable'),
])
def test_manifest_failures_and_redirects_have_no_fallback(embedding_server, patch, code):
    provider, state = embedding_server; state.update(patch)
    with pytest.raises(SourceError) as error: provider.embed_documents(['health'])
    assert error.value.code == code and '/api/pull' not in state['calls']
    if code == 'local_embeddings_unavailable': assert error.value.transient


def test_bounds_capacity_unknown_tokens_and_no_remote_provider(embedding_server):
    provider, state = embedding_server
    for texts in [[], ['health'] * (BATCH_SIZE+1), ['x'*1201], [None]]:
        with pytest.raises(SourceError): provider.embed_documents(texts)
    assert not state['calls']
    provider.capacity.acquire()
    try:
        with pytest.raises(SourceError) as error: provider.embed_query('health')
        assert error.value.code == 'local_embeddings_busy' and not state['calls']
    finally: provider.capacity.release()
    state['tokens'] = None
    assert provider.embed_query('health').input_tokens is None
    with pytest.raises(ValueError): Settings(development_auth_token='test-development-token', embedding_provider='paid')


def test_timeouts_are_retryable_without_leaking_local_input(embedding_server, monkeypatch):
    provider, state = embedding_server
    def fail(*args, **kwargs): raise TimeoutError('private transcript and secret endpoint')
    monkeypatch.setattr(provider.opener, 'open', fail)
    with pytest.raises(SourceError) as error: provider.embed_query('private question')
    assert error.value.transient and error.value.code == 'local_embeddings_unavailable'
    assert 'private' not in str(error.value) and error.value.__cause__ is None
    assert not state['calls']


@pytest.mark.anyio
async def test_semantic_runtime_is_authenticated_and_inline_ingestion_is_disabled():
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.store import InMemoryStore
    from conftest import MappingAuthenticator, auth_headers
    settings = Settings(environment='test', development_auth_token='test-development-token', embedding_provider='ollama', store_backend='memory')
    app = create_app(settings=settings,store=InMemoryStore(),authenticator=MappingAuthenticator())
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        assert (await client.get('/api/v1/runtime')).status_code == 401
        runtime = (await client.get('/api/v1/runtime',headers=auth_headers())).json()
        assert runtime['retrieval'] == 'local-semantic-and-lexical' and runtime['embedding_space'] == QWEN_SPACE
        project = (await client.post('/api/v1/projects',headers=auth_headers(),json={'title':'Semantic mode'})).json()
        response = await client.post('/api/v1/projects/'+project['id']+'/sources/transcripts',headers=auth_headers(),json={
            'filename':'sample.vtt','content':'WEBVTT\n\n00:00.000 --> 00:01.000\nhealth','authorization_mode':'owner_upload','idempotency_key':'sample-semantic'})
        assert response.status_code == 503 and response.json()['code'] == 'validation_endpoint_unavailable'
        # Scope preflight must reject these without trying the unavailable local model.
        for path, headers in [('/api/v1/projects/'+project['id']+'/questions',auth_headers('tenant-b')),
                              ('/api/v1/projects/'+str(uuid4())+'/questions',auth_headers())]:
            assert (await client.post(path,headers=headers,json={'question':'health'})).status_code == 404


def test_semantic_guard_uses_raw_cosine_not_fused_score_and_reranks_paraphrases():
    def hit(text, similarity, *, space=QWEN_SPACE):
        return RetrievalHit(segment=EvidenceSegment(tenant_id='test',project_id=uuid4(),source_id=uuid4(),
            modality='transcript',start_ms=0,end_ms=1000,text=text,embedding=[1.],embedding_space=space),
            source_filename='fixture.vtt',score=99.,semantic_similarity=similarity)
    relevant, lexical_noise = hit('GET /health returns 200 when the API is running.', .65), hit('The server is alive in a metaphor.', .25)
    results = fuse_and_rerank('Which route tells me the server is alive?', [[lexical_noise], [relevant,lexical_noise]], 4, semantic_mode=True)
    assert results[0].segment.id == relevant.segment.id and results[0].score < .1
    assert grounded_hits('Which route tells me the server is alive?', results) == results[:1]
    assert not grounded_hits('server alive', [lexical_noise])
    assert not grounded_hits('TLS Kubernetes', [hit('GET /health', .99, space='signed-hash-v1:64')])
