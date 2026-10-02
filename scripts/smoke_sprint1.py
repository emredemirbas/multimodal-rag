"""Exercise the local Compose stack using only a disposable test project."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class SmokeFailure(RuntimeError):
    pass


def run() -> None:
    token = os.getenv("DEVELOPMENT_AUTH_TOKEN", "")
    if len(token) < 16:
        raise SmokeFailure("Set DEVELOPMENT_AUTH_TOKEN before running the smoke check.")
    api = f"http://127.0.0.1:{int(os.getenv('API_PORT', '8000'))}"
    frontend = f"http://127.0.0.1:{int(os.getenv('FRONTEND_PORT', '3000'))}"

    def request(
        origin: str,
        path: str,
        *,
        method: str = "GET",
        body: dict | None = None,
        expected: int = 200,
        authenticated: bool = True,
    ) -> bytes:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        http_request = Request(origin + path, data=data, headers=headers, method=method)
        try:
            with urlopen(http_request, timeout=15) as response:
                status = response.status
                result = response.read(2_000_000)
        except HTTPError as exc:
            status = exc.code
            result = exc.read(2_000_000)
        except (URLError, TimeoutError):
            raise SmokeFailure(f"Could not reach {origin}.") from None
        if status != expected:
            raise SmokeFailure(f"{method} {path}: expected {expected}, got {status}.")
        return result

    def api_json(path: str, **kwargs) -> dict:
        return json.loads(request(api, path, **kwargs))

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise SmokeFailure(message)

    require(api_json("/health/live")["status"] == "ok", "API liveness failed.")
    require(api_json("/health/ready")["status"] == "ok", "API readiness failed.")
    health = json.loads(request(frontend, "/api/health", authenticated=False))
    require(health["status"] == "ok", "Frontend health failed.")
    request(api, "/api/v1/projects", expected=401, authenticated=False)

    suffix = uuid4().hex
    title = f"Sprint 1 smoke {suffix}"
    created = api_json(
        "/api/v1/projects", method="POST", body={"title": title}, expected=201
    )
    project_path = f"/api/v1/projects/{created['id']}"
    deleted = False
    try:
        require(api_json(project_path)["title"] == title, "Project detail mismatch.")
        html = request(frontend, f"/projects/{created['id']}", authenticated=False)
        require(title.encode() in html, "Frontend did not render the API-backed project.")
        renamed_title = f"Renamed {title}"
        renamed = api_json(
            project_path, method="PATCH", body={"title": f"  {renamed_title}  "}
        )
        require(renamed["title"] == renamed_title, "Project rename failed.")
        require(
            api_json(project_path + "/archive", method="POST")["status"] == "archived",
            "Project archive failed.",
        )
        active = api_json("/api/v1/projects")["items"]
        archived = api_json("/api/v1/projects?status=archived")["items"]
        require(all(item["id"] != created["id"] for item in active), "Active filter failed.")
        require(any(item["id"] == created["id"] for item in archived), "Archive filter failed.")
        require(
            api_json(project_path + "/restore", method="POST")["status"] == "active",
            "Project restore failed.",
        )
        source = api_json(
            project_path + "/sources/transcripts",
            method="POST",
            expected=201,
            body={
                "filename": "smoke.vtt",
                "content": "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nThe health endpoint reports service availability.\n",
                "authorization_mode": "owner_upload",
                "idempotency_key": f"smoke-{suffix}",
            },
        )["source"]
        answer = api_json(
            project_path + "/questions",
            method="POST",
            body={"question": "Which endpoint reports service health?"},
        )
        require(not answer["abstained"] and bool(answer["citations"]), "Cited answer failed.")
        request(api, project_path, method="DELETE", expected=204)
        deleted = True
        request(api, project_path, expected=404)
        request(api, project_path + f"/sources/{source['id']}", expected=404)
    finally:
        if not deleted:
            request(api, project_path, method="DELETE", expected=204)
    print("PASS: Compose health, authentication, frontend rendering, project lifecycle, cited answer, and deletion.")


if __name__ == "__main__":
    try:
        run()
    except (SmokeFailure, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
