"""Explicit real-worker/local semantic probe; owns and cleans only its test project."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    api = 'http://127.0.0.1:' + os.getenv('API_PORT', '8000')
    web = 'http://127.0.0.1:' + os.getenv('FRONTEND_PORT', '3000')
    auth = {'Authorization': 'Bearer ' + os.environ['DEVELOPMENT_AUTH_TOKEN']}

    def request(path, method='GET', body=None, expected=200, content_type='application/json'):
        data = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
        try:
            with urlopen(Request(api+path, data=data, method=method, headers={**auth,'Content-Type':content_type}), timeout=30) as response:
                status, raw, headers = response.status, response.read(2_000_000), response.headers
        except HTTPError as error:
            status, raw, headers = error.code, error.read(128_000), error.headers
        if status != expected:
            raise RuntimeError(f'{status}:{json.loads(raw).get("code","request_failed") if raw else "request_failed"}')
        return (json.loads(raw) if raw else None), headers

    def wait_job(job):
        for _ in range(120):
            current, _ = request(path+'/jobs/'+job['id'])
            if current['status'] == 'succeeded': return
            if current['status'] in {'failed','cancelled'}: raise RuntimeError(current['failure_code'])
            time.sleep(.25)
        raise RuntimeError('Owned job did not finish')

    runtime, _ = request('/api/v1/runtime')
    assert runtime['retrieval'] == 'local-semantic-and-lexical' and runtime['spend_policy'] == 'no-paid-provider'
    project, _ = request('/api/v1/projects', 'POST', {'title':'Owned semantic smoke '+uuid4().hex[:8]}, 201)
    path = '/api/v1/projects/' + project['id']
    try:
        boundary = 'owned-'+uuid4().hex
        transcript = ('WEBVTT\n\n00:01.250 --> 00:05.500\nThe GET /health endpoint responds with status 200 to show the API is running.\n\n'
                      '00:20.000 --> 00:25.000\nPydantic validates request bodies and rejects invalid input with a 422 response.\n\n'
                      '00:40.000 --> 00:45.000\nPostgreSQL transactions commit all statements together or roll back the entire transaction on error.\n')
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="authorization_mode"\r\n\r\nowner_upload\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\nsmoke-{uuid4().hex}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="semantic.vtt"\r\nContent-Type: text/vtt\r\n\r\n'
                f'{transcript}\r\n--{boundary}--\r\n').encode()
        registered, _ = request(path+'/sources/uploads','POST',body,202,'multipart/form-data; boundary='+boundary)
        wait_job(registered['job'])
        source_path = path+'/sources/'+registered['source']['id']
        indexed, _ = request(source_path)
        assert indexed['active_embedding_space'] == runtime['embedding_space'] and not indexed['reindex_required']
        cases = [
            ('Which route tells me the server is alive?', '/health'),
            ('Uygulamanın çalışıp çalışmadığını hangi adresten anlayabilirim?', '/health'),
            ('How do I deploy Kubernetes with TLS certificates?', None),
            ('What is the capital of France?', None),
        ]
        for question, expected in cases:
            started = time.monotonic()
            answer, _ = request(path+'/questions','POST',{'question':question})
            if expected:
                assert not answer['abstained'] and expected in answer['answer']
                assert answer['citations'][0]['source_id'] == registered['source']['id']
                assert answer['citations'][0]['start_ms'] == 1250
                old_segment = answer['citations'][0]['segment_id']
            else: assert answer['abstained'] and not answer['citations']
            print(f'PASS: {question} ({time.monotonic()-started:.2f}s)', flush=True)
        refreshed, _ = request(source_path+'/reprocess','POST',{'idempotency_key':'reindex-'+uuid4().hex},202)
        wait_job(refreshed['job'])
        evidence, _ = request(path+'/evidence/'+old_segment)
        assert evidence['generation'] == 1 and evidence['start_ms'] == 1250
        with urlopen(web+'/projects/'+project['id'], timeout=15) as response:
            html = response.read(2_000_000)
            assert b'Local semantic search:' in html and b'Qwen3 Embedding 0.6B' in html
        print('PASS: actual worker indexing, immutable old evidence after reprocessing and honest SSR mode.', flush=True)
    finally:
        _, headers = request(path, 'DELETE', expected=204)
        for _ in range(120):
            ticket, _ = request(path+'/cleanup/'+headers['X-Cleanup-ID'])
            if ticket['status'] == 'completed': break
            if ticket['status'] == 'failed': raise RuntimeError('Owned cleanup failed')
            time.sleep(.25)
        else: raise RuntimeError('Owned cleanup incomplete')
        request(path, expected=404)
        print('PASS: owned semantic test project/files removed; cleanup completed.', flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        raise SystemExit('FAIL: semantic smoke ('+type(error).__name__+'); inspect safe local model/job status.') from None
