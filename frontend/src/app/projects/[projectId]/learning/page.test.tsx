import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LearningPage from "@/app/projects/[projectId]/learning/page";
import ContextPage from "@/app/projects/[projectId]/learning/contexts/[contextId]/page";
import { getProject } from "@/lib/api/client";
import { getDocumentationCatalog, getLearningContext, listContextDocuments, listLearningSources } from "@/lib/api/curriculum";
import { ApiError } from "@/lib/api/errors";
import type { SavedLearningContext } from "@/lib/api/curriculum-contracts";

vi.mock("@/lib/api/client", () => ({ getProject: vi.fn() }));
vi.mock("@/lib/api/curriculum", () => ({ getDocumentationCatalog: vi.fn(), getLearningContext: vi.fn(), listContextDocuments: vi.fn(), listLearningSources: vi.fn() }));
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("not-found"); } }));
vi.mock("@/components/curriculum/learning-context-form", () => ({ LearningContextForm: ({ tenantId }: { tenantId: string }) => <p>Form for {tenantId}</p> }));
vi.mock("@/components/curriculum/saved-context-workspace", () => ({ SavedContextWorkspace: ({ context }: { context: SavedLearningContext }) => <p>Saved generation {context.selected_sources[0].generation}</p> }));

const projectId = "11111111-1111-4111-8111-111111111111", contextId = "22222222-2222-4222-8222-222222222222";
const project = { id: projectId, tenant_id: "synthetic-tenant", title: "Synthetic project", status: "active" as const,
  created_at: "2026-11-11T00:00:00Z", updated_at: "2026-11-11T00:00:00Z", archived_at: null };
const context: SavedLearningContext = { id: contextId, tenant_id: project.tenant_id, project_id: projectId, created_at: project.created_at,
  learner: { experience: "intermediate", difficulty: "beginner", language: "tr", available_minutes: 60,
    allow_prerequisites: false, allow_extensions: false, allow_external_documentation: true },
  selected_sources: [{ source_id: "33333333-3333-4333-8333-333333333333", generation: 1, processing_version: "synthetic-v1:g1", source_filename: "owned.vtt" }] };
const start = (id = projectId) => LearningPage({ params: Promise.resolve({ projectId: id }) });
const saved = (id = contextId) => ContextPage({ params: Promise.resolve({ projectId, contextId: id }) });

describe("scoped learner pages", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getProject).mockResolvedValue(project);
    vi.mocked(listLearningSources).mockResolvedValue([]);
    vi.mocked(getLearningContext).mockResolvedValue(context);
    vi.mocked(getDocumentationCatalog).mockResolvedValue([]);
    vi.mocked(listContextDocuments).mockResolvedValue([]);
  });

  it("rejects malformed IDs before any authenticated read", async () => {
    await expect(start("../private")).rejects.toThrow("not-found");
    await expect(saved("../private")).rejects.toThrow("not-found");
    expect(getProject).not.toHaveBeenCalled();
  });

  it("binds source selection to the validated server tenant and project", async () => {
    render(await start());
    expect(listLearningSources).toHaveBeenCalledWith({ tenant_id: project.tenant_id, project_id: projectId });
    expect(screen.getByText("Form for synthetic-tenant")).toBeVisible();
  });

  it("refuses a project receipt for another ID before loading private material", async () => {
    vi.mocked(getProject).mockResolvedValue({ ...project, id: contextId });
    render(await start());
    expect(listLearningSources).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.queryByText(/Form for/)).toBeNull();
  });

  it("loads a bookmarked immutable context without requiring current source generations", async () => {
    render(await saved());
    const scope = { tenant_id: project.tenant_id, project_id: projectId };
    expect(getLearningContext).toHaveBeenCalledWith(scope, contextId);
    expect(listContextDocuments).toHaveBeenCalledWith(scope, contextId);
    expect(listLearningSources).not.toHaveBeenCalled();
    expect(screen.getByText("Saved generation 1")).toBeVisible();
    expect(screen.getByText(/Bookmark this page/)).toBeVisible();
  });

  it("handles deleted dependencies as missing and never renders partial saved data on service failure", async () => {
    vi.mocked(listContextDocuments).mockRejectedValue(new ApiError({ status: 404 }));
    await expect(saved()).rejects.toThrow("not-found");
    vi.mocked(listContextDocuments).mockRejectedValue(new ApiError({ status: 503, message: "PRIVATE_TEXT" }));
    render(await saved());
    expect(screen.queryByText("Saved generation 1")).toBeNull();
    expect(screen.queryByText("PRIVATE_TEXT")).toBeNull();
    expect(screen.getByRole("link", { name: "Retry" })).toHaveAttribute("href", `/projects/${projectId}/learning/contexts/${contextId}`);
  });
});
