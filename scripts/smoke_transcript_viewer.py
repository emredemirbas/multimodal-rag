"""Actual worker + version-pinned API/production SSR. Own projects only; no answers."""
import json
import os
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    api = f"http://127.0.0.1:{os.getenv('API_PORT', '8000')}"
    web = f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '3000')}"
    auth = {"Authorization": "Bearer " + os.environ["DEVELOPMENT_AUTH_TOKEN"]}

    def request(path, method="GET", body=None, expected=200, headers=None):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        try:
            with urlopen(Request(api + path, data=data, method=method, headers={"Content-Type": "application/json", **auth, **(headers or {})}), timeout=10) as response:
                content, status, receipt = response.read(3_000_000), response.status, response.headers
        except HTTPError as error:
            content, status, receipt = error.read(100_000), error.code, error.headers
        assert status == expected, f"Expected {expected}, received {status}"
        return json.loads(content) if content else None, receipt

    def html(path):
        with urlopen(web + path, timeout=15) as response:
            return re.sub(r"<!--.*?-->", "", response.read(3_000_000).decode())

    def wait(path, successful, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current, _ = request(path)
            if current["status"] == successful:
                return current
            assert current["status"] not in {"failed", "cancelled"}
            time.sleep(.5)
        raise RuntimeError("Owned test work did not finish within its bound")

    project, _ = request("/api/v1/projects", "POST", {"title": "Transcript viewer smoke " + uuid4().hex[:12]}, 201)
    path = "/api/v1/projects/" + project["id"]
    web_project = "/projects/" + project["id"]
    deleted = False
    try:
        def timestamp(ms):
            seconds, fraction = divmod(ms, 1000)
            return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}.{fraction:03d}"
        content = "WEBVTT\n\n" + "\n\n".join(
            f"{timestamp(i * 15_000 + 1250)} --> {timestamp(i * 15_000 + 5500)}\n"
            f"Viewer segment {i}. GET /health reports service availability."
            + (' &lt;img src=x onerror="alert(1)"&gt;' if i == 51 else "")
            for i in range(53))
        boundary = "viewer-" + uuid4().hex
        data = (f'--{boundary}\r\nContent-Disposition: form-data; name="authorization_mode"\r\n\r\nowner_upload\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="idempotency_key"\r\n\r\nviewer-{uuid4().hex}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="viewer.vtt"\r\nContent-Type: text/vtt\r\n\r\n'
                f'{content}\r\n--{boundary}--\r\n').encode()
        uploaded, _ = request(path + "/sources/uploads", "POST", data, 202, {"Content-Type": "multipart/form-data; boundary=" + boundary})
        source = uploaded["source"]["id"]
        wait(path + "/jobs/" + uploaded["job"]["id"], "succeeded")
        transcript_path = path + "/sources/" + source + "/transcript"
        viewer = web_project + "/sources/" + source + "/transcript"
        first, private_headers = request(transcript_path)
        assert private_headers["Cache-Control"] == "no-store"
        assert first["generation"] == 1 and first["total_segments"] == 53 and len(first["items"]) == 50
        second, _ = request(transcript_path + "?generation=1&page=2")
        assert len(second["items"]) == 3 and second["items"][0]["start_ms"] == 751_250
        assert len({segment["segment_id"] for segment in first["items"] + second["items"]}) == 53
        request(transcript_path + "?page=2", expected=422)
        request(transcript_path + "?generation=1&page=3", expected=404)
        assert "Read transcript" in html(web_project)
        page_one = html(viewer + "?generation=1&page=1")
        assert "00:01.250" in page_one and "Next page" in page_one and "generation=1&amp;page=2" in page_one
        page_two = html(viewer + "?generation=1&page=2")
        assert "Page 2 of 2" in page_two and "Previous page" in page_two and "&lt;img src=x" in page_two
        assert "<img src=x" not in page_two
        segment = second["items"][0]
        assert segment["text"] in html(web_project + "/evidence/" + segment["segment_id"])
        reprocessed, _ = request(path + "/sources/" + source + "/reprocess", "POST", {"idempotency_key": "viewer-reprocess-" + uuid4().hex}, 202)
        wait(path + "/jobs/" + reprocessed["job"]["id"], "succeeded")
        old, _ = request(transcript_path + "?generation=1&page=2")
        assert old["items"] == second["items"] and old["active_generation"] == 2
        newest, _ = request(transcript_path)
        assert newest["generation"] == 2 and newest["items"][0]["segment_id"] != first["items"][0]["segment_id"]
        assert "older published generation" in html(viewer + "?generation=1&page=2")
        request(path + "/archive", "POST")
        assert request(transcript_path + "?generation=1&page=2")[0]["items"] == second["items"]
        request(path + "/restore", "POST")
        cleanup, _ = request(path + "/sources/" + source, "DELETE", expected=202)
        request(transcript_path + "?generation=1&page=2", expected=404)
        wait(path + "/cleanup/" + cleanup["id"], "completed", timeout=60)
        _, receipt = request(path, "DELETE", expected=204)
        deleted = True
        wait(path + "/cleanup/" + receipt["X-Cleanup-ID"], "completed", timeout=60)
        request(transcript_path, expected=404)
        print("PASS: actual worker, 53 published segments, pinned API/SSR pagination, safe text, stable evidence, reprocessing, archive and owned-data cleanup. No answer generation.")
    finally:
        if not deleted:
            _, receipt = request(path, "DELETE", expected=204)
            wait(path + "/cleanup/" + receipt["X-Cleanup-ID"], "completed", timeout=60)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"FAIL: transcript viewer smoke ({type(error).__name__}); inspect safe service status.") from None
