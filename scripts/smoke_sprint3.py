"""Exercise actual ingestion, persisted SSE/BFF, provenance and scoped deletion."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    api = f"http://127.0.0.1:{os.getenv('API_PORT', '8000')}"
    web = f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '3000')}"
    auth = {"Authorization": "Bearer " + os.environ["DEVELOPMENT_AUTH_TOKEN"]}

    def request(path, method="GET", body=None, expected=200, *, frontend=False, headers=None):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        selected = {"Content-Type": "application/json", **({"Origin": web} if frontend else auth), **(headers or {})}
        try:
            with urlopen(Request((web if frontend else api)+path, data=data, method=method, headers=selected), timeout=15) as response:
                content, status, response_headers = response.read(3_000_000), response.status, response.headers
        except HTTPError as error:
            content, status, response_headers = error.read(100_000), error.code, error.headers
        assert status == expected, f"Expected status {expected}, received {status}"
        return (json.loads(content) if content else None), response_headers

    def stream(path, body, *, disconnect=False):
        with urlopen(Request(web+path, data=json.dumps(body).encode(), method="POST",
                     headers={"Content-Type":"application/json", "Origin":web}), timeout=15) as response:
            assert response.headers["Content-Type"].startswith("text/event-stream")
            first = response.readline(16_000)
            assert first == b"event: start\n"
            if disconnect:
                return
            content = first + response.read(128_000)
            complete = content.split(b"event: complete\ndata: ")[1].split(b"\n\n")[0]
            assert b"event: delta" in content
            return json.loads(complete)

    def wait_job(path, job):
        for _ in range(120):
            current, _ = request(path+"/jobs/"+job)
            if current["status"] == "succeeded": return
            assert current["status"] not in {"failed", "cancelled"}
            time.sleep(.25)
        raise RuntimeError("Test-owned job did not complete")

    def wait_cleanup(path, ticket):
        for _ in range(120):
            current, _ = request(path+"/cleanup/"+ticket)
            if current["status"] == "completed": return
            assert current["status"] != "failed"
            time.sleep(.25)
        raise RuntimeError("Test-owned cleanup did not complete")

    project, _ = request("/api/v1/projects", "POST", {"title":"Chat smoke "+uuid4().hex[:12]}, 201)
    path = "/api/v1/projects/"+project["id"]
    web_path = "/api/projects/"+project["id"]
    deleted = False
    try:
        boundary = "transcript-"+uuid4().hex
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="authorization_mode"\r\n\r\nowner_upload\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\nsmoke-{uuid4().hex}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chat.vtt"\r\nContent-Type: text/vtt\r\n\r\n'
                'WEBVTT\n\n00:01.250 --> 00:05.500\nGET /health reports service availability.\n'
                f'\r\n--{boundary}--\r\n').encode()
        source, _ = request(path+"/sources/uploads", "POST", data, 202, headers={"Content-Type":"multipart/form-data; boundary="+boundary})
        wait_job(path, source["job"]["id"])
        conversation, _ = request(web_path+"/conversations", "POST", {"idempotency_key":"conversation-"+uuid4().hex}, 201, frontend=True)
        message_path = web_path+"/conversations/"+conversation["id"]+"/messages"
        body = {"question":"What is GET /health?", "source_ids":[source["source"]["id"]], "idempotency_key":"message-"+uuid4().hex}
        stream(message_path, body, disconnect=True)
        saved, _ = request(web_path+"/conversations/"+conversation["id"], frontend=True)
        assert len(saved["turns"]) == 1
        turn = stream(message_path, body)
        assert turn["id"] == saved["turns"][0]["id"] and not turn["response"]["abstained"]
        request(message_path, "POST", {**body, "question":"Different input"}, 409, frontend=True)
        request(message_path, "POST", body, 403, frontend=True, headers={"Origin":"https://attacker.example"})
        citation = turn["response"]["citations"][0]
        evidence_path = path+"/evidence/"+citation["segment_id"]
        evidence, _ = request(evidence_path)
        assert evidence["start_ms"] == 1250 and evidence["end_ms"] == 5500 and evidence["generation"] == 1
        with urlopen(web+"/projects/"+project["id"]+"/evidence/"+citation["segment_id"], timeout=15) as response:
            html = response.read(2_000_000)
            assert b"00:01.250" in html and b"GET /health" in html
        with urlopen(web+"/projects/"+project["id"], timeout=15) as response:
            assert b"Chat with tutorial evidence" in response.read(2_000_000)
        reprocessed, _ = request(path+"/sources/"+source["source"]["id"]+"/reprocess", "POST", {"idempotency_key":"reprocess-"+uuid4().hex}, 202)
        wait_job(path, reprocessed["job"]["id"])
        old, _ = request(evidence_path)
        assert old == evidence
        newer = stream(message_path, {**body, "idempotency_key":"message-"+uuid4().hex})
        assert newer["response"]["citations"][0]["generation"] == 2
        assert newer["response"]["citations"][0]["segment_id"] != citation["segment_id"]
        limitation = stream(message_path, {"question":"How does Kubernetes ingress handle TLS?", "idempotency_key":"message-"+uuid4().hex})
        assert limitation["response"]["abstained"] and not limitation["response"]["citations"]
        cleanup, _ = request(path+"/sources/"+source["source"]["id"], "DELETE", expected=202)
        request(evidence_path, expected=404)
        saved, _ = request(web_path+"/conversations/"+conversation["id"], frontend=True)
        assert len(saved["turns"]) == 1 and saved["turns"][0]["response"]["abstained"]
        wait_cleanup(path, cleanup["id"])
        _, headers = request(path, "DELETE", expected=204)
        deleted = True
        request(path+"/conversations/"+conversation["id"], expected=404)
        wait_cleanup(path, headers["X-Cleanup-ID"])
        print("PASS: actual ingestion, same-origin credential-safe BFF/SSE, disconnected delivery replay, history, versioned evidence, abstention and full source/project cleanup.")
    finally:
        if not deleted:
            _, headers = request(path, "DELETE", expected=204)
            wait_cleanup(path, headers["X-Cleanup-ID"])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"FAIL: chat smoke ({type(error).__name__}); inspect safe service status.") from None
