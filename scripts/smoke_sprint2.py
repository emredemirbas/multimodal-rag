"""Actual Compose worker/outbox/S3 proof; creates and deletes only its own project."""
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    token = os.environ['DEVELOPMENT_AUTH_TOKEN']
    origin = f"http://127.0.0.1:{os.getenv('API_PORT', '8000')}"
    frontend = f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '3000')}"

    def request(path, method='GET', body=None, expected=200, content_type='application/json'):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': content_type}
        try:
            with urlopen(Request(origin+path, data=data, method=method, headers=headers), timeout=15) as response:
                status, content, response_headers = response.status, response.read(2_000_000), response.headers
        except HTTPError as error:
            status, content, response_headers = error.code, error.read(2_000_000), error.headers
        if status != expected:
            raise RuntimeError(f'{method} {path}: expected {expected}, got {status}')
        return (json.loads(content) if content else None), response_headers

    project, _ = request('/api/v1/projects', 'POST', {'title': f'Ingestion smoke {uuid4().hex[:12]}'}, 201)
    path = f"/api/v1/projects/{project['id']}"
    deleted = False

    def upload(key, content):
        boundary = f'upload-{uuid4().hex}'
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="authorization_mode"\r\n\r\nowner_upload\r\n',
                 f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\n{key}\r\n',
                 f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke.vtt"\r\nContent-Type: text/vtt\r\n\r\n{content}\r\n',
                 f'--{boundary}--\r\n']
        return request(path+'/sources/uploads', 'POST', ''.join(parts).encode(), 202, f'multipart/form-data; boundary={boundary}')[0]

    def wait_job(job):
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            current, _ = request(path+f"/jobs/{job['id']}")
            if current['status'] in {'succeeded', 'failed', 'cancelled'}:
                return current
            time.sleep(0.25)
        raise RuntimeError('Worker did not complete the job within 60 seconds')

    def wait_cleanup(ticket):
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            current, _ = request(path+f'/cleanup/{ticket}')
            if current['status'] == 'completed':
                return
            if current['status'] == 'failed':
                raise RuntimeError('Retained file cleanup failed')
            time.sleep(0.25)
        raise RuntimeError('Retained file cleanup did not complete within 60 seconds')

    try:
        content = 'WEBVTT\n\n00:00.000 --> 00:05.000\nFastAPI create_app() exposes GET /health for service availability.\n'
        result = upload('smoke-upload-'+uuid4().hex, content)
        key = 'repeat-upload-'+uuid4().hex
        first = upload(key, content)
        assert upload(key, content)['source']['id'] == first['source']['id']
        assert wait_job(result['job'])['status'] == 'succeeded'
        assert wait_job(first['job'])['status'] == 'succeeded'
        source_path = path+f"/sources/{result['source']['id']}"
        answer, _ = request(path+'/questions', 'POST', {'question': 'What does GET /health report?'})
        assert answer['citations'] and not answer['abstained']
        reprocess, _ = request(source_path+'/reprocess', 'POST', {'idempotency_key': 'smoke-reprocess-'+uuid4().hex}, 202)
        assert reprocess['job']['generation'] == 2
        assert wait_job(reprocess['job'])['status'] == 'succeeded'
        ready, _ = request(source_path)
        assert ready['active_generation'] == 2 and ready['segment_count'] == 1
        malformed = upload('invalid-upload-'+uuid4().hex, 'This is text but contains no valid cues.')
        failed = wait_job(malformed['job'])
        assert failed['status'] == 'failed' and failed['failure_code'] == 'invalid_transcript'
        retried, _ = request(path+f"/sources/{malformed['source']['id']}/retry", 'POST', {'idempotency_key': 'smoke-retry-'+uuid4().hex}, 202)
        assert wait_job(retried['job'])['status'] == 'failed'
        with urlopen(frontend+f"/projects/{project['id']}", timeout=15) as response:
            html = response.read(2_000_000)
            assert b'Source management' in html and b'smoke.vtt' in html
        ticket, _ = request(source_path, 'DELETE', expected=202)
        request(source_path, expected=404)
        wait_cleanup(ticket['id'])
        _, headers = request(path, 'DELETE', expected=204)
        deleted = True
        request(path, expected=404)
        wait_cleanup(headers['X-Cleanup-ID'])
        print('PASS: actual worker, durable upload/outbox, idempotency, indexing/citations, reprocessing, actionable failure/retry, frontend and complete file cleanup.')
    finally:
        if not deleted:
            _, headers = request(path, 'DELETE', expected=204)
            wait_cleanup(headers['X-Cleanup-ID'])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Do not emit exception objects that may include request headers or credentials.
        print(f'FAIL: ingestion smoke check ({type(error).__name__}); inspect safe job/service status.', file=sys.stderr)
        sys.exit(1)
