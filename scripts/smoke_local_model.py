"""Explicit real local-model smoke; never downloads weights or invokes a paid API."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    api='http://127.0.0.1:'+os.getenv('API_PORT','8000')
    web='http://127.0.0.1:'+os.getenv('FRONTEND_PORT','3000')
    auth={'Authorization':'Bearer '+os.environ['DEVELOPMENT_AUTH_TOKEN']}

    def request(path, method='GET', body=None, expected=200, headers=None):
        data=json.dumps(body).encode() if isinstance(body,dict) else body
        try:
            with urlopen(Request(api+path,data=data,method=method,headers={**auth,'Content-Type':'application/json',**(headers or {})}),timeout=35) as response:
                raw,status,result_headers=response.read(128_000),response.status,response.headers
        except HTTPError as error:
            raw,status,result_headers=error.read(128_000),error.code,error.headers
        if status!=expected:
            code=json.loads(raw).get('code','request_failed') if raw else 'request_failed'
            raise RuntimeError(f'{status}:{code}')
        return json.loads(raw) if raw else None,result_headers

    def stream(path, body):
        try:
            with urlopen(Request(web+path,data=json.dumps(body).encode(),method='POST',headers={'Content-Type':'application/json','Origin':web}),timeout=35) as response:
                assert response.headers['Content-Type'].startswith('text/event-stream')
                raw=response.read(128_000)
        except HTTPError as error:
            payload=json.loads(error.read(4096))
            print('Local delivery failed with HTTP %s, safe code %s.'%(error.code,payload.get('code','unavailable')),flush=True)
            raise
        return json.loads(raw.split(b'event: complete\ndata: ')[1].split(b'\n\n')[0])

    runtime,_=request('/api/v1/runtime')
    assert runtime['mode']=='ollama' and runtime['spend_policy']=='no-paid-provider', 'Enable explicit local mode first'
    project,_=request('/api/v1/projects','POST',{'title':'Owned local-model smoke '+uuid4().hex[:8]},201)
    path='/api/v1/projects/'+project['id']
    try:
        boundary='owned-'+uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="authorization_mode"\r\n\r\nowner_upload\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\nsmoke-{uuid4().hex}\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="owned-local.vtt"\r\nContent-Type: text/vtt\r\n\r\n'
              'WEBVTT\n\n00:01.250 --> 00:05.500\nGET /health reports service availability.\n'
              f'\r\n--{boundary}--\r\n').encode()
        registered,_=request(path+'/sources/uploads','POST',body,202,{'Content-Type':'multipart/form-data; boundary='+boundary})
        for _ in range(120):
            job,_=request(path+'/jobs/'+registered['job']['id'])
            if job['status']=='succeeded': break
            assert job['status'] not in {'failed','cancelled'}
            time.sleep(.25)
        else: raise RuntimeError('Owned upload did not finish')
        conversation,_=request(path+'/conversations','POST',{'idempotency_key':'local-'+uuid4().hex},201)
        message_path='/api/projects/'+project['id']+'/conversations/'+conversation['id']+'/messages'
        message={'question':'Which endpoint reports service availability?','idempotency_key':'local-'+uuid4().hex}
        started=time.monotonic()
        answered=stream(message_path,message)
        assert not answered['response']['abstained'] and answered['response']['provider']=='ollama-local'
        assert '/health' in answered['response']['answer'] and answered['response']['citations'][0]['source_id']==registered['source']['id']
        assert stream(message_path,message)['id']==answered['id']
        print('PASS: real local answer, stable citation, BFF/SSE and same-key replay; %.2fs first answer.'%(time.monotonic()-started),flush=True)
        unsupported=stream(message_path,{'question':'Does this tutorial teach Kubernetes ingress TLS setup?','idempotency_key':'local-'+uuid4().hex})
        assert unsupported['response']['abstained'] and not unsupported['response']['citations']
        assert unsupported['response']['provider']=='local-evidence-policy'
        history,_=request(path+'/conversations/'+conversation['id'])
        assert len(history['turns'])==2
        with urlopen(web+'/projects/'+project['id'],timeout=10) as response:
            assert b'Local Ollama answer mode' in response.read(2_000_000)
        print('PASS: application-side unsupported-question guard (no model call), persisted history and honest UI mode.',flush=True)
    finally:
        _,headers=request(path,'DELETE',expected=204)
        for _ in range(120):
            ticket,_=request(path+'/cleanup/'+headers['X-Cleanup-ID'])
            if ticket['status']=='completed': break
            assert ticket['status']!='failed'
            time.sleep(.25)
        else: raise RuntimeError('Owned cleanup did not complete')
        request(path,expected=404)
        print('PASS: owned local-model test project and files removed; cleanup completed.',flush=True)


if __name__=='__main__':
    try: main()
    except Exception as error:
        raise SystemExit('FAIL: local-model smoke ('+type(error).__name__+'); check safe API/model status.') from None
