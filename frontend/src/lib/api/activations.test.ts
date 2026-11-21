import { webcrypto } from "node:crypto";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { context, projectId, documentId } from "@/components/curriculum/test-fixtures";
import { draftFixture, draftId, rawContextFixture } from "@/components/curriculum/draft-fixtures";
import { getProject, requestJson } from "./client";
import { ApiError } from "./errors";
import { activateAssignment, getAssignmentActivation, getDraftActivation, readAssignmentActivation, readDraftActivation } from "./activations";
import { POST } from "@/app/api/projects/[projectId]/curriculum/drafts/[draftId]/activate/route";
import { GET as readStateRoute } from "@/app/api/projects/[projectId]/curriculum/drafts/[draftId]/activation/route";
import { GET as readExactRoute } from "@/app/api/projects/[projectId]/curriculum/assignments/[activationId]/route";

vi.mock("./client", () => ({ getProject: vi.fn(), requestJson: vi.fn() }));
const scope = { tenant_id: context.tenant_id, project_id: projectId };
const project = { ...scope, id: projectId, title: "Synthetic project", status: "active" as const, created_at: context.created_at, updated_at: context.created_at, archived_at: null };
const root = `/api/v1/projects/${projectId}/curriculum`;
const activationId = "92345678-1234-4234-8234-123456789abc";
const actorId = "a2345678-1234-4234-8234-123456789abc";
const receipt = (revision = 1) => ({ ...scope, id: activationId, draft_id: draftId, context_id: context.id, revision, activated_at: "2026-11-21T09:00:00Z", activated_by: actorId, draft: draftFixture(revision) });
const command = () => ({ idempotency_key: "activate-revision-001", expected_revision: 1, consent: "activate_reviewed_revision" });
const request = (body: unknown = command(), origin = "http://localhost") => new Request("http://localhost/api/activate", { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: typeof body === "string" ? body : JSON.stringify(body) });
const target = () => ({ params: Promise.resolve({ projectId, draftId }) });
beforeAll(() => { vi.stubGlobal("crypto", webcrypto); });
beforeEach(() => {
  vi.mocked(getProject).mockReset().mockResolvedValue(project);
  vi.mocked(requestJson).mockReset().mockImplementation(async (path) => {
    if (path === root + `/contexts/${context.id}`) return rawContextFixture();
    if (path === root + `/drafts/${draftId}` || path === root + `/drafts/${draftId}/revisions/1`) return draftFixture();
    if (path === root + `/drafts/${draftId}/activation`) return { activation: receipt() };
    if (path === root + `/drafts/${draftId}/activate` || path === root + `/assignments/${activationId}`) return receipt();
    throw new Error("Unexpected path");
  });
});

describe("authorized assignment activation BFF", () => {
  it("requires exact reviewed evidence and returns a private 201 version receipt", async () => {
    const response = await activateAssignment(request(), projectId, draftId);
    expect(response.status).toBe(201); expect(await response.json()).toEqual(receipt());
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(response.headers.get("Cross-Origin-Resource-Policy")).toBe("same-origin");
    expect(requestJson).toHaveBeenCalledWith(root + `/drafts/${draftId}/revisions/1`);
    expect(requestJson).not.toHaveBeenCalledWith(root + `/drafts/${draftId}`);
    expect(requestJson).toHaveBeenCalledWith(root + `/drafts/${draftId}/activate`, { method: "POST", body: JSON.stringify(command()) });
  });
  it("replays the pinned old version after newer edits and project archive", async () => {
    vi.mocked(getProject).mockResolvedValue({ ...project, status: "archived", archived_at: "2026-11-21T12:00:00Z" });
    vi.mocked(requestJson).mockImplementation(async (path) => {
      if (path.endsWith(`/contexts/${context.id}`)) return rawContextFixture();
      if (path.endsWith(`/drafts/${draftId}`)) return draftFixture(3);
      if (path.endsWith("/revisions/1")) return draftFixture();
      if (path.endsWith("/activate")) return receipt();
      throw new Error("Unexpected path");
    });
    const response = await activateAssignment(request(), projectId, draftId);
    expect((await response.json()).revision).toBe(1);
    expect(requestJson).not.toHaveBeenCalledWith(root + `/drafts/${draftId}`);
  });
  it("rejects an altered activation narrative even if its evidence and metadata match", async () => {
    const altered = receipt(); altered.draft.assignment.draft.title = "Changed after review";
    vi.mocked(requestJson).mockImplementation(async (path) => path.endsWith("/activate") ? altered : path.includes("/contexts/") ? rawContextFixture() : draftFixture());
    await expect(activateAssignment(request(), projectId, draftId)).rejects.toMatchObject({ status: 502, code: "invalid_api_response" });
  });
  it("refuses substituted retained tutorial text before issuing a write", async () => {
    const altered = draftFixture(); altered.assignment.tutorial_evidence[0].text = "Changed authoritative text";
    vi.mocked(requestJson).mockImplementation(async (path) => path.includes("/contexts/") ? rawContextFixture() : altered);
    await expect(activateAssignment(request(), projectId, draftId)).rejects.toMatchObject({ status: 502 });
    expect(vi.mocked(requestJson).mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
  it("preserves backend revision/key conflicts and does not invent a successful retry", async () => {
    for (const code of ["draft_revision_conflict", "idempotency_conflict"]) {
      vi.mocked(requestJson).mockImplementation(async (path) => {
        if (path.endsWith("/activate")) throw new ApiError({ status: 409, code });
        return path.includes("/contexts/") ? rawContextFixture() : draftFixture();
      });
      await expect(activateAssignment(request(), projectId, draftId)).rejects.toMatchObject({ status: 409, code });
    }
  });
  it("checks same origin, explicit consent, duplicate keys, byte limit and browser scope before authorization", async () => {
    await expect(activateAssignment(request(command(), "https://attacker.example"), projectId, draftId)).rejects.toMatchObject({ status: 403 });
    await expect(activateAssignment(request('{"consent":"activate_reviewed_revision","consent":true}'), projectId, draftId)).rejects.toMatchObject({ status: 422 });
    await expect(activateAssignment(request({ ...command(), private: "ü".repeat(9000) }), projectId, draftId)).rejects.toMatchObject({ status: 413 });
    await expect(activateAssignment(request({ ...command(), tenant_id: "foreign" }), projectId, draftId)).rejects.toMatchObject({ status: 422, code: "invalid_assignment_activation" });
    await expect(activateAssignment(request({ ...command(), consent: true }), projectId, draftId)).rejects.toMatchObject({ status: 422, code: "invalid_assignment_activation" });
    expect(getProject).not.toHaveBeenCalled(); expect(requestJson).not.toHaveBeenCalled();
  });
  it("checks project authorization and scoped identifiers before returning exact versions", async () => {
    expect((await getAssignmentActivation(scope, activationId)).activation).toEqual(receipt());
    vi.mocked(getProject).mockResolvedValue({ ...project, tenant_id: "foreign" });
    await expect(getAssignmentActivation(scope, activationId)).rejects.toMatchObject({ status: 502 });
    vi.mocked(requestJson).mockClear();
    await expect(getAssignmentActivation(scope, "../private")).rejects.toMatchObject({ status: 404 });
    expect(requestJson).not.toHaveBeenCalled();
  });
  it.each(["id", "scope", "revision", "context", "text"])("rejects a substituted exact version %s", async (kind) => {
    const altered = receipt();
    if (kind === "id") altered.id = documentId;
    if (kind === "scope") altered.project_id = documentId;
    if (kind === "revision") altered.revision = 2;
    if (kind === "context") altered.context_id = documentId;
    if (kind === "text") altered.draft.assignment.tutorial_evidence[0].text = "Substituted text";
    vi.mocked(requestJson).mockImplementation(async (path) => path.includes("/contexts/") ? rawContextFixture() : altered);
    await expect(getAssignmentActivation(scope, activationId)).rejects.toMatchObject({ status: 502, code: "invalid_api_response" });
  });
  it("allows absent activation only for a still-available authorized draft", async () => {
    vi.mocked(requestJson).mockImplementation(async (path) => path.endsWith("/activation") ? { activation: null } : path.includes("/contexts/") ? rawContextFixture() : draftFixture());
    expect(await getDraftActivation(scope, draftId)).toBeNull();
    expect(await (await readDraftActivation(projectId, draftId)).json()).toEqual({ activation: null });
    vi.mocked(requestJson).mockImplementation(async () => { throw new ApiError({ status: 404 }); });
    await expect(getDraftActivation(scope, draftId)).rejects.toMatchObject({ status: 404 });
  });
  it("reads the previously active immutable revision while a newer draft remains editable", async () => {
    vi.mocked(requestJson).mockImplementation(async (path) => path.endsWith("/activation") ? { activation: receipt() } : path.includes("/contexts/") ? rawContextFixture() : draftFixture(3));
    expect(await getDraftActivation(scope, draftId)).toEqual(receipt());
  });
  it("rejects foreign/future state and unexpected null-state fields", async () => {
    for (const value of [{ activation: { ...receipt(), draft_id: documentId } }, { activation: receipt(2) }, { activation: null, leaked: "private" }]) {
      vi.mocked(requestJson).mockImplementation(async (path) => path.endsWith("/activation") ? value : path.includes("/contexts/") ? rawContextFixture() : draftFixture());
      await expect(getDraftActivation(scope, draftId)).rejects.toMatchObject({ status: 502 });
    }
  });
  it("routes all reads privately and maps write failures to safe response bodies", async () => {
    const state = await readStateRoute(new Request("http://localhost/api/state"), target());
    expect(state.status).toBe(200); expect(await state.json()).toEqual({ activation: receipt() });
    const exact = await readExactRoute(new Request("http://localhost/api/exact"), { params: Promise.resolve({ projectId, activationId }) });
    expect(exact.status).toBe(200); expect(await exact.json()).toEqual(receipt());
    expect((await readAssignmentActivation(projectId, activationId)).headers.get("Cache-Control")).toBe("private, no-store");
    vi.mocked(requestJson).mockRejectedValue(new ApiError({ status: 409, code: "idempotency_conflict", message: "private server details" }));
    const failed = await POST(request(), target());
    const failure = await failed.json();
    expect(failed.status).toBe(409); expect(failure).toMatchObject({ code: "idempotency_conflict" });
    expect(JSON.stringify(failure)).not.toContain("private server details");
  });
  it("reports deleted exact versions without exposing server details", async () => {
    vi.mocked(requestJson).mockRejectedValue(new ApiError({ status: 404, message: "private deletion details" }));
    const response = await readExactRoute(new Request("http://localhost/api/exact"), { params: Promise.resolve({ projectId, activationId }) });
    const body = await response.json();
    expect(response.status).toBe(404); expect(body.code).toBe("assignment_activation_not_found");
    expect(JSON.stringify(body)).not.toContain("private deletion details");
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });
});
