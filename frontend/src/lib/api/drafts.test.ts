import { createHash, webcrypto } from "node:crypto";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { getProject, requestJson } from "./client";
import { ApiError } from "./errors";
import { deleteDraft, getDraft, listDrafts, readDraftList, replaceDraft } from "./drafts";
import { draftContent } from "./draft-contracts";
import { context, projectId, documentId, documentFixture } from "@/components/curriculum/test-fixtures";
import { draftFixture, draftId, rawContextFixture } from "@/components/curriculum/draft-fixtures";
vi.mock("./client", () => ({ getProject: vi.fn(), requestJson: vi.fn() }));
const scope = { tenant_id: context.tenant_id, project_id: projectId };
const project = { ...scope, id: projectId, title: "Synthetic project", status: "active" as const, created_at: context.created_at, updated_at: context.created_at, archived_at: null };
const root = `/api/v1/projects/${projectId}/curriculum`;
const request = (body: unknown, origin = "http://localhost") => new Request("http://localhost/api/draft", { method: "PUT", headers: { Origin: origin, "Content-Type": "application/json" }, body: typeof body === "string" ? body : JSON.stringify(body) });
beforeAll(() => { vi.stubGlobal("crypto", webcrypto); });
beforeEach(() => {
  vi.mocked(getProject).mockReset().mockResolvedValue(project);
  vi.mocked(requestJson).mockReset().mockImplementation(async (path) => { if (path === root + `/contexts/${context.id}`) return rawContextFixture(); if (path === root + `/drafts/${draftId}`) return draftFixture(); throw new Error("Unexpected path"); });
});
describe("authorized draft BFF", () => {
  it("checks project, context pins and authoritative tutorial text before returning a draft", async () => {
    expect((await getDraft(scope, draftId)).result).toEqual(draftFixture());
    vi.mocked(getProject).mockResolvedValue({ ...project, tenant_id: "foreign" });
    await expect(getDraft(scope, draftId)).rejects.toMatchObject({ status: 502 });
  });
  it("rejects substituted evidence text even when its identifiers and pins match", async () => {
    const bad = draftFixture(); bad.assignment.tutorial_evidence[0].text = "Changed untrusted text";
    vi.mocked(requestJson).mockImplementation(async (path) => path.includes("/drafts/") ? bad : rawContextFixture());
    await expect(getDraft(scope, draftId)).rejects.toMatchObject({ code: "invalid_api_response" });
  });
  it("replays an accepted old command without preflight revision replacement", async () => {
    const body = { idempotency_key: "saved-replace-001", expected_revision: 1, content: draftContent(draftFixture()), documentation_ids: [] };
    vi.mocked(requestJson).mockImplementation(async (path, init) => path.includes("/drafts/") ? draftFixture(init?.method === "PUT" ? 2 : 3) : rawContextFixture());
    const response = await replaceDraft(request(body), projectId, draftId);
    expect(response.status).toBe(200); expect((await response.json()).revision).toBe(2);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(requestJson).toHaveBeenCalledWith(root + `/drafts/${draftId}`, { method: "PUT", body: JSON.stringify(body) });
  });
  it("rejects mismatched saved content or revision after an uncertain write", async () => {
    const body = { idempotency_key: "saved-replace-001", expected_revision: 1, content: { ...draftContent(draftFixture()), title: "Changed title" }, documentation_ids: [] };
    vi.mocked(requestJson).mockImplementation(async (path, init) => path.includes("/drafts/") ? draftFixture(init?.method === "PUT" ? 2 : 1) : rawContextFixture());
    await expect(replaceDraft(request(body), projectId, draftId)).rejects.toMatchObject({ status: 502 });
  });
  it("keeps writes same-origin, bounded, unambiguous and free of client scope", async () => {
    await expect(replaceDraft(request({}, "https://attacker.example"), projectId, draftId)).rejects.toMatchObject({ status: 403 });
    await expect(replaceDraft(request('{"x":1,"x":2}'), projectId, draftId)).rejects.toMatchObject({ status: 422 });
    await expect(replaceDraft(request({ private: "ü".repeat(140_000) }), projectId, draftId)).rejects.toMatchObject({ status: 413 });
    await expect(replaceDraft(request({ tenant_id: "foreign" }), projectId, draftId)).rejects.toMatchObject({ status: 422 });
    expect(getProject).not.toHaveBeenCalled(); expect(requestJson).not.toHaveBeenCalled();
  });
  it("accepts a draft body larger than the ordinary context limit", async () => {
    const value = draftFixture(); value.assignment.draft.constraints = Array.from({length: 5}, () => "ü".repeat(3000));
    const body = { idempotency_key: "larger-draft-key", expected_revision: 1, content: draftContent(value), documentation_ids: [] };
    vi.mocked(requestJson).mockImplementation(async (path, init) => path.includes("/drafts/") ? { ...value, revision: init?.method === "PUT" ? 2 : 1 } : rawContextFixture());
    expect((await replaceDraft(request(body), projectId, draftId)).status).toBe(200);
  });
  it("checks discovery cursors and foreign context responses", async () => {
    vi.mocked(requestJson).mockResolvedValue({ items: [], next_after: null });
    expect(await listDrafts(scope, context.id, documentId)).toEqual({ items: [], next_after: null });
    expect(requestJson).toHaveBeenLastCalledWith(root + `/contexts/${context.id}/drafts?after=${documentId}`);
    for (const query of ['after=', 'after=../private', 'after=' + documentId + '&after=' + draftId, 'url=https://attacker.example']) {
      await expect(readDraftList(projectId, context.id, new Request('http://localhost/api/drafts?' + query))).rejects.toBeInstanceOf(ApiError);
    }
  });

  it("verifies retained selected documents including uncited dependencies and rejects altered projections", async () => {
    const full = documentFixture(true), value = draftFixture();
    const hash = (value: string) => createHash("sha256").update(value).digest("hex");
    const {fingerprint: _fingerprint, ...policy} = full.policy; void _fingerprint;
    full.policy.fingerprint = hash(JSON.stringify(Object.fromEntries(Object.entries(policy).sort(([a],[b]) => a.localeCompare(b)))));
    full.snapshot!.excerpts[0].content_sha256 = hash(full.snapshot!.excerpts[0].text);
    full.snapshot!.content_sha256 = hash(full.snapshot!.excerpts.map((item) => item.text).join(""));
    value.documentation_ids = [documentId];
    vi.mocked(requestJson).mockImplementation(async (path) => path.endsWith(`/documentation/${documentId}`) ? full : path.includes('/drafts/') ? value : rawContextFixture());
    expect((await getDraft(scope,draftId)).result.documentation_ids).toEqual([documentId]);
    value.assignment.draft.requirements[0].documentation_excerpt_ids = [full.snapshot!.excerpts[0].id];
    value.assignment.documentation_snapshots = [structuredClone(full.snapshot!)];
    expect((await getDraft(scope,draftId)).result.assignment.documentation_snapshots).toEqual([full.snapshot]);
    value.assignment.documentation_snapshots[0].excerpts[0].text = 'Altered retained quotation';
    await expect(getDraft(scope,draftId)).rejects.toMatchObject({status:502});
  });
  it("requires real no-content deletion and never exposes credentials to browser payloads", async () => {
    vi.mocked(requestJson).mockResolvedValue(null);
    const result = await deleteDraft(new Request('http://localhost/api/draft', {method: 'DELETE', headers:{Origin:'http://localhost'}}), projectId, draftId);
    expect(result.status).toBe(204);
    expect(requestJson).toHaveBeenLastCalledWith(root + `/drafts/${draftId}`, { method: "DELETE" }, undefined, { expectedStatus: 204 });
    await expect(deleteDraft(new Request('http://localhost/api/draft', {method:'DELETE'}), projectId, draftId)).rejects.toMatchObject({ status: 403 });
  });
});
