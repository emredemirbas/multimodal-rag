import { createHash, webcrypto } from "node:crypto";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { getProject, requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { approveDocumentation, captureDocumentation, createLearningContext, curriculumProxyError, curriculumRequestBody, deleteDocumentation, deleteLearningContext, parseUniqueJson } from "@/lib/api/curriculum-proxy";

vi.mock("@/lib/api/client", () => ({ getProject: vi.fn(), requestJson: vi.fn() }));
const projectId = "10000000-0000-0000-0000-000000000001", contextId = "20000000-0000-0000-0000-000000000001", documentId = "30000000-0000-0000-0000-000000000001";
const scope = { tenant_id: "local-test", project_id: projectId };
const project = { id: projectId, tenant_id: scope.tenant_id, title: "Synthetic", status: "active" as const, created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z", archived_at: null };
const hash = (value: string) => createHash("sha256").update(value).digest("hex");
function policy(title = "FastAPI — First Steps (English)") {
  const item = { id: "fastapi-first-steps-en", title, url: "https://fastapi.tiangolo.com/tutorial/first-steps/", parser_version: "official-document-html-v1", version_policy: "unversioned; detected_version=unknown", license_name: "MIT", license_url: "https://github.com/fastapi/fastapi/blob/master/LICENSE", license_text: "Synthetic MIT notice retained verbatim", attribution: "Synthetic attribution" };
  return { ...item, fingerprint: hash(JSON.stringify(Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))))) };
}
function pending() { return { ...scope, id: documentId, context_id: contextId, approved_by: "40000000-0000-0000-0000-000000000001", approved_at: "2026-11-11T10:00:00Z", consent: "retrieve_and_retain", policy: policy(), status: "pending", failure_code: null, snapshot: null, raw_sha256: null, raw_bytes: null }; }
function captured(text = "Synthetic official plaintext") {
  return { ...pending(), status: "captured", raw_sha256: hash("synthetic html"), raw_bytes: 120,
    snapshot: { ...scope, id: documentId, url: policy().url, retrieved_at: "2026-11-11T10:00:01Z", detected_version: null, content_sha256: hash(text), excerpts: [{ id: "50000000-0000-0000-0000-000000000001", text, content_sha256: hash(text) }] } };
}
const request = (body: string, headers: Record<string, string> = {}) => new Request("http://localhost/api/learning", { method: "POST", body, headers: { Origin: "http://localhost", "Content-Type": "application/json", ...headers } });
const captureBody = () => request('{"idempotency_key":"capture-document-001"}');
beforeAll(() => { vi.stubGlobal("crypto", webcrypto); });
beforeEach(() => { vi.mocked(getProject).mockReset().mockResolvedValue(project); vi.mocked(requestJson).mockReset(); });
describe("same-origin bounded original JSON boundary", () => {
  it("rejects cross-origin/missing origins and unsupported media types before upstream requests", async () => {
    const cases: Record<string, string>[] = [{ Origin: "https://attacker.example" }, { Origin: "" }, { "Content-Type": "text/plain" }];
    for (const headers of cases) await expect(curriculumRequestBody(request("{}", headers))).rejects.toMatchObject({ status: headers["Content-Type"] ? 415 : 403 });
    expect(requestJson).not.toHaveBeenCalled();
  });
  it.each(['{"x":1,"x":2}', '{"x":1,"\\u0078":2}', '{"learner":{"allow_extensions":false,"allow_extensions":true}}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,}', '{"x":"\\u0000"} trailing']) ("rejects duplicate or nonstandard JSON %s", async (body) => {
    await expect(curriculumRequestBody(request(body))).rejects.toMatchObject({ status: 422 });
  });
  it("bounds actual UTF-8 bytes and rejects invalid UTF-8 without truncation", async () => {
    expect(await curriculumRequestBody(request('{"quoted":"\\\"x\\\"","nested":[1,true,null]}'))).toEqual({ quoted: '"x"', nested: [1, true, null] });
    await expect(curriculumRequestBody(request(JSON.stringify({ text: "ü".repeat(8200) })))).rejects.toMatchObject({ status: 413 });
    await expect(curriculumRequestBody(new Request("http://localhost/api/learning", { method: "POST", body: new Uint8Array([0xff]), headers: { Origin: "http://localhost", "Content-Type": "application/json" } }))).rejects.toMatchObject({ status: 422 });
    expect(() => parseUniqueJson("[".repeat(34) + "0" + "]".repeat(34))).toThrow();
  });
  it("rejects unknown command fields before using server credentials", async () => {
    await expect(createLearningContext(request('{"tenant_id":"foreign"}'), projectId)).rejects.toMatchObject({ status: 422 });
    await expect(approveDocumentation(request('{"idempotency_key":"approve-test","catalog_id":"fastapi-first-steps-en","catalog_sha256":"' + "0".repeat(64) + '","consent":"retrieve_and_retain","url":"http://127.0.0.1"}'), projectId, contextId)).rejects.toMatchObject({ status: 422 });
    expect(getProject).not.toHaveBeenCalled(); expect(requestJson).not.toHaveBeenCalled();
  });
});
describe("immutable scoped documentation receipts", () => {
  it("allows old same-key approval replay after current catalog policy changed", async () => {
    const original = { ...pending(), policy: policy("Original approved catalog title") };
    vi.mocked(requestJson).mockResolvedValue(original);
    const body = { idempotency_key: "approve-original-001", catalog_id: original.policy.id, catalog_sha256: original.policy.fingerprint, consent: "retrieve_and_retain" };
    const result = await approveDocumentation(request(JSON.stringify(body)), projectId, contextId);
    expect(result.status).toBe(201); expect(await result.json()).toMatchObject({ policy: original.policy });
    expect(requestJson).toHaveBeenCalledExactlyOnceWith(`/api/v1/projects/${projectId}/curriculum/contexts/${contextId}/documentation`, { method: "POST", body: JSON.stringify(body) });
  });
  it("does not accept changed policy or foreign context in approval receipts", async () => {
    const body = { idempotency_key: "approve-original-001", catalog_id: policy().id, catalog_sha256: policy().fingerprint, consent: "retrieve_and_retain" };
    for (const changed of [{ ...pending(), policy: policy("Different approved policy") }, { ...pending(), context_id: documentId }]) {
      vi.mocked(requestJson).mockResolvedValue(changed);
      await expect(approveDocumentation(request(JSON.stringify(body)), projectId, contextId)).rejects.toMatchObject({ status: 502, code: "invalid_api_response" });
    }
  });
  it("captures separately with a narrowly longer delivery timeout and validates identity", async () => {
    vi.mocked(requestJson).mockResolvedValueOnce(pending()).mockResolvedValueOnce(captured());
    const result = await captureDocumentation(captureBody(), projectId, documentId);
    expect(result.status).toBe(200); expect((await result.json()).status).toBe("captured");
    expect(requestJson).toHaveBeenLastCalledWith(`/api/v1/projects/${projectId}/curriculum/documentation/${documentId}/capture`, { method: "POST", body: '{"idempotency_key":"capture-document-001"}' }, undefined, { timeoutMs: 25_000 });
    expect(result.headers.get("Cache-Control")).toBe("private, no-store");
  });
  it("rejects changed captured text, retrieval date and raw provenance on replay", async () => {
    const original = captured();
    const changes = [captured("Valid new hash but changed immutable content"), { ...captured(), snapshot: { ...original.snapshot, retrieved_at: "2026-11-11T10:00:02Z" } }, { ...captured(), raw_sha256: "a".repeat(64) }, { ...captured(), raw_bytes: 121 }];
    for (const changed of changes) {
      vi.mocked(requestJson).mockReset().mockResolvedValueOnce(original).mockResolvedValueOnce(changed);
      await expect(captureDocumentation(captureBody(), projectId, documentId)).rejects.toMatchObject({ status: 502, code: "invalid_api_response" });
    }
    vi.mocked(requestJson).mockReset().mockResolvedValueOnce(original).mockResolvedValueOnce(original);
    expect((await captureDocumentation(captureBody(), projectId, documentId)).status).toBe(200);
  });
  it("keeps deletion same-origin and requires an actual no-content receipt", async () => {
    vi.mocked(requestJson).mockResolvedValue(null);
    const deletion = new Request("http://localhost/api/learning", { method: "DELETE", headers: { Origin: "http://localhost" } });
    expect((await deleteDocumentation(deletion, projectId, documentId)).status).toBe(204);
    expect(requestJson).toHaveBeenLastCalledWith(`/api/v1/projects/${projectId}/curriculum/documentation/${documentId}`, { method: "DELETE" }, undefined, { expectedStatus: 204 });
    expect((await deleteLearningContext(deletion, projectId, contextId)).status).toBe(204);
    await expect(deleteDocumentation(new Request("http://localhost/api/learning", { method: "DELETE" }), projectId, documentId)).rejects.toMatchObject({ status: 403 });
  });
  it("exposes only fixed recovery messages and distinguishes target loss from project loss", async () => {
    const safe = curriculumProxyError(new ApiError({ status: 503, code: "documentation_fetch_timeout", message: "private fetched content" }));
    expect(await safe.json()).toMatchObject({ code: "documentation_fetch_timeout" });
    const unknown = curriculumProxyError(new ApiError({ status: 503, code: "secret token", message: "private" }));
    expect(JSON.stringify(await unknown.json())).not.toMatch(/secret|private/);
    expect((await curriculumProxyError(new ApiError({ status: 404 }), "documentation_not_found").json()).code).toBe("documentation_not_found");
    expect((await curriculumProxyError(new ApiError({ status: 404, code: "project_not_found" }), "documentation_not_found").json()).code).toBe("project_not_found");
  });
});
