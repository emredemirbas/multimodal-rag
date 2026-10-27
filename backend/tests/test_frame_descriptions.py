"""Actual bounded HTTP transport; all image-model output is an explicit fixture."""
import base64
from dataclasses import replace
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from uuid import uuid4

import pytest

from app.config import Settings
from app.sources.contracts import SourceError
from app.vision.descriptions_client import (DescriptionIdentity, FrameDescription,
    LocalDescriptionProvider, MODEL, description_text)
from app.vision.index import chunks
from app.vision.media import encode_png


def identity():
    return DescriptionIdentity(model_digest='a'*64,engine='0.40.3')


def description(**overrides):
    return FrameDescription(kind='diagram',summary='Two boxes joined by an arrow.',
        details=['PRIVATE_DESCRIPTION <script>literal</script>'],uncertainties=['Purpose is not shown.'],
        abstained=False,**overrides)


@pytest.fixture
def image_model():
    state={'calls':[], 'digest':'a'*64, 'content':description().model_dump(), 'override':{}, 'status':200}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_GET(self): self.respond()
        def do_POST(self): self.respond()
        def respond(self):
            state['calls'].append(self.path)
            if self.command=='POST': state[self.path]=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/tags': payload={'models':[{'name':MODEL,'digest':state['digest']}]}
            elif self.path=='/api/show': payload={'capabilities':['completion','vision'],'details':{'family':'qwen35'},**state.get('show',{})}
            elif self.path=='/api/version': payload={'version':state.get('version','0.40.3')}
            elif self.path=='/api/chat':
                payload={'model':MODEL,'done':True,'done_reason':'stop','message':{'role':'assistant','content':json.dumps(state['content'])},
                    'prompt_eval_count':12,'eval_count':30,**state['override']}
                if state.get('drift'): state['digest']='b'*64
            else: raise AssertionError('No pull/cloud/tool endpoint is allowed')
            self.send_response(state['status']); self.send_header('Content-Type','application/json')
            if state['status']==302: self.send_header('Location','http://example.test:80/private')
            self.end_headers(); self.wfile.write(state.get('raw',json.dumps(payload).encode()))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True); thread.start()
    try: yield LocalDescriptionProvider(f'http://127.0.0.1:{server.server_port}','a'*64),state
    finally: server.shutdown();server.server_close();thread.join(timeout=2)


def test_actual_image_only_http_identity_usage_and_no_proxy_or_private_logs(image_model,monkeypatch,caplog):
    provider,state=image_model
    monkeypatch.setenv('HTTP_PROXY','http://unreachable.example.test:80')
    image=encode_png(16,16,bytes(256))
    result=provider.describe(image,16,16,provider.ready())
    assert result.identity==identity() and result.description==description()
    assert (result.input_tokens,result.output_tokens,result.input_sha256)==(12,30,hashlib.sha256(image).hexdigest())
    payload=state['/api/chat']
    assert payload['think'] is False and payload['stream'] is False and payload['keep_alive']==0
    assert payload['options']=={'temperature':0,'num_ctx':4096,'num_predict':512,'num_thread':4}
    assert 'tools' not in payload and len(payload['messages'])==2
    assert payload['format']['additionalProperties'] is False
    assert payload['messages'][1]=={'role':'user','content':'Describe only this image.','images':[base64.b64encode(image).decode()]}
    assert state['calls'].count('/api/chat')==1 and set(state['calls'])=={'/api/chat','/api/tags','/api/show','/api/version'}
    assert 'PRIVATE_DESCRIPTION' not in caplog.text and 'PRIVATE_DESCRIPTION' not in repr(result)
    assert description_text(result.description).startswith('Unreviewed image-model description:')


@pytest.mark.parametrize('case',['extra','oversize','missing','boolean_tokens','negative_tokens','tool','role','not_done','length','malformed','nonobject'])
def test_rejects_invalid_output_without_inference_retry(image_model,case):
    provider,state=image_model
    if case=='extra': state['content']['execute']='curl private.example'
    if case=='oversize': state['content']['summary']='x'*361
    if case=='missing': del state['content']['uncertainties']
    if case=='boolean_tokens': state['override']['eval_count']=True
    if case=='negative_tokens': state['override']['prompt_eval_count']=-1
    if case=='tool': state['override']['message']={'role':'assistant','tool_calls':[{'function':'fetch'}]}
    if case=='role': state['override']['message']={'role':'user','content':'{}'}
    if case=='not_done': state['override']['done']=False
    if case=='length': state['override']['done_reason']='length'
    if case=='malformed': state['override']['message']={'role':'assistant','content':'{"kind":'}
    if case=='nonobject': state['override']['message']=[]
    with pytest.raises(SourceError) as failure: provider.describe(encode_png(16,16,bytes(256)),16,16,identity())
    assert failure.value.code=='invalid_visual_description' and state['calls'].count('/api/chat')==1


@pytest.mark.parametrize('case',['digest','cloud','family','capability','version','redirect','overlong','invalid_json','drift'])
def test_unready_changed_or_unsafe_model_never_falls_back(image_model,case):
    provider,state=image_model
    if case=='digest': state['digest']='b'*64
    if case=='cloud': state['show']={'remote_host':'cloud.example'}
    if case=='family': state['show']={'details':{'family':'other'}}
    if case=='capability': state['show']={'capabilities':['completion']}
    if case=='version': state['version']='PRIVATE/path'
    if case=='redirect': state['status']=302
    if case=='overlong': state['raw']=b'x'*65537
    if case=='invalid_json': state['raw']=b'['
    if case=='drift': state['drift']=True
    with pytest.raises(SourceError): provider.describe(encode_png(16,16,bytes(256)),16,16,identity())
    assert state['calls'].count('/api/chat')==(1 if case=='drift' else 0)
    assert '/api/pull' not in state['calls']


@pytest.mark.parametrize('url',['https://api.example.test:443','http://10.0.0.1:11434','http://localhost:11434/api','http://user:secret@localhost:11434'])
def test_no_remote_or_credential_bearing_endpoint(url):
    with pytest.raises(ValueError): LocalDescriptionProvider(url,'a'*64)


def test_opt_in_requires_digest_and_never_changes_default_provider():
    baseline=Settings(development_auth_token='fixture-development-token')
    assert baseline.frame_descriptions_enabled is False and baseline.vision_model_digest==''
    with pytest.raises(ValueError): replace(baseline,frame_descriptions_enabled=True)
    with pytest.raises(ValueError): replace(baseline,vision_model_digest='latest')
    assert replace(baseline,frame_descriptions_enabled=True,vision_model_digest='a'*64).answer_provider==baseline.answer_provider


@pytest.mark.parametrize('change',[{'kind':'unclear'},{'summary':' '},{'summary':'x\x00'},
    {'details':['x'*101]},{'uncertainties':['a','b','c']},{'abstained':True}])
def test_strict_bounded_coherent_output(change):
    with pytest.raises(ValueError): FrameDescription.model_validate({**description().model_dump(),**change})


def test_abstention_and_mixed_chunks_preserve_separate_literal_ocr_and_bounded_legacy():
    absent=FrameDescription(kind='unclear',summary='',details=[],uncertainties=['Unreadable.'],abstained=True)
    assert description_text(absent)==''
    frames=[dict(id=uuid4(),timestamp_ms=i*5000,ocr_text='😀'*16000) for i in range(20)]
    scope=('fixture',uuid4(),uuid4(),4)
    legacy=chunks(*scope,frames)
    mixed=chunks(*scope,frames,descriptions={frame['id']:description() for frame in frames})
    assert len(legacy)==280 and len(mixed)==300 and max(len(row['text']) for row in mixed)<=1200
    assert mixed==chunks(*scope,frames,descriptions={frame['id']:description() for frame in frames})
    assert not set(row['segment_id'] for row in mixed)&set(row['segment_id'] for row in legacy)
    for frame in frames:
        pieces=[row for row in mixed if row['frame_id']==frame['id']]
        assert all(row['start_ms']==frame['timestamp_ms'] for row in pieces)
        assert ''.join(row['text'].removeprefix('Unreviewed OCR text:\n') for row in pieces[:-1])==frame['ocr_text']
        assert pieces[-1]['text']==description_text(description())
    assert not chunks(*scope,[{**frames[0],'ocr_text':''}],descriptions={frames[0]['id']:absent})
