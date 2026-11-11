import { beforeEach, describe, expect, it, vi } from "vitest";
import { getProject, requestJson } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { authorizeLearningProject, getLearningContext, listContextDocuments, listLearningSources } from "@/lib/api/curriculum";

vi.mock("@/lib/api/client", () => ({ getProject: vi.fn(), requestJson: vi.fn() }));
const projectId = "10000000-0000-0000-0000-000000000001", contextId = "20000000-0000-0000-0000-000000000001", sourceId = "30000000-0000-0000-0000-000000000001";
const scope = { tenant_id: "local-test", project_id: projectId };
const project = { id: projectId, tenant_id: scope.tenant_id, title: "Synthetic", status: "active" as const, created_at: "2026-11-11T10:00:00Z", updated_at: "2026-11-11T10:00:00Z", archived_at: null };
const learner = { experience: "intermediate", difficulty: "beginner", language: "tr", available_minutes: 60, allow_prerequisites: false, allow_extensions: false, allow_external_documentation: true };
function context() {
  const pin = { ...scope, source_id: sourceId, generation: 1, processing_version: "transcript-chunks-v1:g1" };
  return { ...scope, id: contextId, created_at: "2026-11-11T10:00:00Z", request: { ...scope, learner, selected_sources: [pin] }, tutorial_snapshots: [{ pin, segments: [{ segment_id: "40000000-0000-0000-0000-000000000001", source_id: sourceId, source_filename: "synthetic.vtt", start_ms: 0, end_ms: 1000, text: "Private tutorial evidence", modality: "transcript", processing_version: pin.processing_version, generation: 1 }] }] };
}
beforeEach(() => { vi.mocked(getProject).mockReset().mockResolvedValue(project); vi.mocked(requestJson).mockReset(); });
describe("authorized curriculum server readers", () => {
  it("rechecks the authoritative project tenant before every read", async () => {
    vi.mocked(getProject).mockResolvedValue({ ...project, tenant_id: "other" });
    await expect(getLearningContext(scope, contextId)).rejects.toMatchObject({ code: "invalid_api_response" });
    expect(requestJson).not.toHaveBeenCalled();
    vi.mocked(getProject).mockResolvedValue({ ...project, id: sourceId });
    await expect(authorizeLearningProject(projectId)).rejects.toMatchObject({ code: "invalid_api_response" });
    await expect(authorizeLearningProject("../other")).rejects.toMatchObject({ status: 404 });
  });
  it("distinguishes a missing project from a missing dependent resource", async () => {
    vi.mocked(getProject).mockRejectedValue(new ApiError({ status: 404 }));
    await expect(getLearningContext(scope, contextId)).rejects.toMatchObject({ status: 404, code: "project_not_found" });
  });
  it("loads a pinned context without returning copied tutorial text", async () => {
    vi.mocked(requestJson).mockResolvedValue(context());
    const result = await getLearningContext(scope, contextId);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/curriculum/contexts/${contextId}`);
    expect(result.selected_sources[0].source_filename).toBe("synthetic.vtt");
    expect(JSON.stringify(result)).not.toContain("Private tutorial evidence");
    vi.mocked(requestJson).mockResolvedValue({ ...context(), id: sourceId });
    await expect(getLearningContext(scope, contextId)).rejects.toMatchObject({ status: 502, code: "invalid_api_response" });
  });
  it("accepts an empty current context document list without inventing a snapshot", async () => {
    vi.mocked(requestJson).mockResolvedValue([]);
    expect(await listContextDocuments(scope, contextId)).toEqual([]);
    expect(requestJson).toHaveBeenCalledWith(`/api/v1/projects/${projectId}/curriculum/contexts/${contextId}/documentation`);
  });
  it("checks every source's raw tenant/project before using current version pins", async () => {
    const source = { ...scope, id: sourceId, filename: "synthetic.vtt", status: "ready", generation: 1, active_generation: 1, processing_version: "transcript-chunks-v1:g1", segment_count: 1, provider: "upload", job: null, failure_code: null };
    vi.mocked(requestJson).mockResolvedValue({ items: [source] });
    expect((await listLearningSources(scope))[0].processing_version).toBe(source.processing_version);
    for (const changed of [{ ...source, tenant_id: "other" }, { ...source, project_id: contextId }, { ...source, tenant_id: undefined }]) {
      vi.mocked(requestJson).mockResolvedValue({ items: [changed] });
      await expect(listLearningSources(scope)).rejects.toMatchObject({ status: 502, code: "invalid_api_response" });
    }
  });
});
