import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from uuid import uuid4

import pytest

from app.config import Settings
from app.local_model import OllamaAnswerProvider, checked_local_url
from app.models import EvidenceSegment, RetrievalHit
from app.sources.contracts import SourceError


def hit():
    return RetrievalHit(segment=EvidenceSegment(id=uuid4(), tenant_id='test', project_id=uuid4(), source_id=uuid4(),
        modality='transcript',start_ms=1000,end_ms=5000,text='GET /health reports service availability.',embedding=[0]*64),
        source_filename='test.vtt',score=1)


@pytest.fixture
def local_server():
    evidence = hit()
    state = {'calls': [], 'status': 200, 'tags': {'models': [{'name': 'qwen3:4b', 'digest': 'a'*64}]},
             'content': {'answer': 'GET /health reports service availability.', 'abstained': False, 'citations': [str(evidence.segment.id)]}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def do_GET(self):
            state['calls'].append(self.path)
            self.send_response(state['status'])
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps(state['tags']).encode())

        def do_POST(self):
            state['calls'].append(self.path)
            state['request'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            payload = {'model':'qwen3:4b','done':True,'message':{'role':'assistant','content':json.dumps(state['content'])},
                       'prompt_eval_count':123,'eval_count':35,**state.get('override',{})}
            self.send_response(state['status'])
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(state.get('raw',json.dumps(payload).encode()))

    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval':.05}, daemon=True)
    thread.start()
    try:
        yield OllamaAnswerProvider(f'http://127.0.0.1:{server.server_port}'), evidence, state
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@pytest.mark.parametrize('url', ['https://api.example.test:443','http://ollama.com:11434','http://10.0.0.1:11434',
    'http://localhost:11434/api','http://user:pass@localhost:11434','http://localhost:11434?target=cloud',
    'http://localhost:11434#cloud','http://localhost','http://localhost:70000'])
def test_only_local_endpoint_configuration_is_accepted(url):
    with pytest.raises(ValueError): checked_local_url(url)


def test_no_paid_provider_or_cloud_model_configuration():
    with pytest.raises(ValueError): Settings(development_auth_token='long-test-token', answer_provider='paid-provider')
    with pytest.raises(ValueError): OllamaAnswerProvider('http://localhost:11434', model='qwen3:4b-cloud')


def test_structured_local_answer_and_usage_without_tools_or_history(local_server, monkeypatch):
    provider, evidence, state = local_server
    monkeypatch.setenv('HTTP_PROXY','http://unreachable.example.test:80')
    answer = provider.answer('What is GET /health?', [evidence])
    assert not answer.abstained and answer.cited_hits == [evidence]
    assert (answer.input_tokens, answer.output_tokens, answer.model_digest) == (123,35,'a'*64)
    request = state['request']
    assert state['calls'] == ['/api/tags','/api/chat']
    assert request['think'] is False and request['stream'] is False and request['options']['num_predict'] == 256
    assert 'tools' not in request and len(request['messages']) == 2
    assert request['format']['properties']['citations']['items']['enum'] == [str(evidence.segment.id)]
    assert request['keep_alive'] == 0
    assert json.loads(request['messages'][1]['content'])['evidence'][0]['id'] == str(evidence.segment.id)


def test_empty_evidence_abstains_without_network_and_busy_does_not_retry(local_server):
    provider, evidence, state = local_server
    empty = provider.answer('unsupported',[])
    assert empty.abstained and empty.input_tokens == 0 and not state['calls']
    unsupported = provider.answer('Kubernetes ingress TLS setup', [evidence])
    assert unsupported.abstained and unsupported.provider == 'local-evidence-policy' and not state['calls']
    provider.capacity.acquire()
    try:
        with pytest.raises(SourceError) as busy: provider.answer('health',[evidence])
        assert busy.value.code == 'local_model_busy' and not state['calls']
    finally: provider.capacity.release()


@pytest.mark.parametrize('case', ['foreign_citation','duplicates','contradiction','missing_citation','extra','invalid_usage','tool_call','oversized','truncated'])
def test_invalid_model_output_is_not_returned(local_server, case):
    provider,evidence,state = local_server
    if case == 'foreign_citation': state['content']['citations']=[str(uuid4())]
    if case == 'duplicates': state['content']['citations']*=2
    if case == 'contradiction': state['content']['abstained']=True
    if case == 'missing_citation': state['content']['citations']=[]
    if case == 'extra': state['content']['execute']='curl attacker.example'
    if case == 'invalid_usage': state['override']={'eval_count':True}
    if case == 'tool_call': state['override']={'message':{'role':'assistant','tool_calls':[{'function':'fetch'}]}}
    if case == 'oversized': state['raw']=b'x'*65_537
    if case == 'truncated': state['raw']=b'{"done":true'
    with pytest.raises(SourceError) as error: provider.answer('health',[evidence])
    assert error.value.code == 'invalid_model_answer'
    assert provider.capacity.acquire(blocking=False)
    provider.capacity.release()


def test_missing_model_and_unavailable_service_do_not_fallback_or_download(local_server):
    provider,evidence,state=local_server
    state['tags']={'models':[]}
    with pytest.raises(SourceError) as missing: provider.answer('health',[evidence])
    assert missing.value.code == 'local_model_not_installed' and state['calls']==['/api/tags']
    state['status']=503
    with pytest.raises(SourceError) as unavailable: provider.answer('health',[evidence])
    assert unavailable.value.code == 'local_model_unavailable'
    assert '/api/pull' not in state['calls']


def test_expired_shared_answer_budget_skips_inference_and_releases_capacity(local_server):
    from time import perf_counter
    provider, evidence, state = local_server
    with pytest.raises(SourceError) as error:
        provider.answer_with_budget('health', [evidence], perf_counter()-1)
    assert error.value.code == 'local_model_unavailable' and not state['calls']
    assert provider.capacity.acquire(blocking=False)
    provider.capacity.release()
