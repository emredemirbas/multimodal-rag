import { beforeEach, describe, expect, it, vi } from "vitest";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createProject, renameProject } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { INITIAL_PROJECT_ACTION_STATE } from "@/lib/action-state";
import { createProjectAction, renameProjectAction } from "@/app/actions/projects";

const { redirectSignal } = vi.hoisted(() => ({ redirectSignal: new Error("test-only redirect") }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn(() => { throw redirectSignal; }) }));
vi.mock("@/lib/api/client", () => ({
  createProject: vi.fn(), renameProject: vi.fn(), archiveProject: vi.fn(),
  restoreProject: vi.fn(), deleteProject: vi.fn(),
}));

const projectId = "12345678-1234-4234-9234-123456789abc";
const saved = { id: projectId, title: "Canonical saved title", status: "active" as const,
  tenant_id: "test-tenant", archived_at: null,
  created_at: "2026-10-28T00:00:00Z", updated_at: "2026-10-28T00:00:00Z" };
function form(title: string) {
  const data = new FormData();
  data.set("projectId", projectId); data.set("title", title);
  return data;
}

beforeEach(() => vi.clearAllMocks());
describe("project name actions", () => {
  it("returns the canonical accepted rename title, not an optimistic submitted value", async () => {
    vi.mocked(renameProject).mockResolvedValueOnce(saved);
    const result = await renameProjectAction(INITIAL_PROJECT_ACTION_STATE, form("  Submitted draft  "));
    expect(renameProject).toHaveBeenCalledWith(projectId, "Submitted draft");
    expect(result).toEqual({ ...INITIAL_PROJECT_ACTION_STATE, status: "success", message: "Project name updated.",
      version: 1, acceptedTitle: saved.title });
    expect(revalidatePath).toHaveBeenCalledWith("/projects");
    expect(revalidatePath).toHaveBeenCalledWith(`/projects/${projectId}`);
  });
  it.each([createProjectAction, renameProjectAction])("keeps validation errors without pretending a name was accepted", async (action) => {
    const result = await action(INITIAL_PROJECT_ACTION_STATE, form("   "));
    expect(result.status).toBe("error");
    expect(result.fieldErrors.title).toBe("Enter a project name.");
    expect(result).not.toHaveProperty("acceptedTitle");
    expect(createProject).not.toHaveBeenCalled(); expect(renameProject).not.toHaveBeenCalled();
    expect(revalidatePath).not.toHaveBeenCalled(); expect(redirect).not.toHaveBeenCalled();
  });
  it("returns safe API errors and references without an accepted rename", async () => {
    vi.mocked(renameProject).mockRejectedValueOnce(new ApiError({ status: 503,
      message: "private upstream detail", requestId: "test-request-reference" }));
    const result = await renameProjectAction(INITIAL_PROJECT_ACTION_STATE, form("Attempted title"));
    expect(result.status).toBe("error");
    expect(result.reference).toBe("test-request-reference");
    expect(result).not.toHaveProperty("acceptedTitle");
    expect(JSON.stringify(result)).not.toContain("private upstream");
    expect(revalidatePath).not.toHaveBeenCalled();
  });
  it("rejects a rename receipt for another project without returning its title", async () => {
    vi.mocked(renameProject).mockResolvedValueOnce({ ...saved, id: "22345678-1234-4234-9234-123456789abc",
      title: "Foreign private project title" });
    const result = await renameProjectAction(INITIAL_PROJECT_ACTION_STATE, form("Attempted title"));
    expect(result.status).toBe("error");
    expect(result).not.toHaveProperty("acceptedTitle");
    expect(JSON.stringify(result)).not.toContain("Foreign private");
    expect(revalidatePath).not.toHaveBeenCalled();
  });
  it("still lets successful project creation redirect through the framework", async () => {
    vi.mocked(createProject).mockResolvedValueOnce(saved);
    await expect(createProjectAction(INITIAL_PROJECT_ACTION_STATE, form("  New project  "))).rejects.toBe(redirectSignal);
    expect(createProject).toHaveBeenCalledWith("New project");
    expect(revalidatePath).toHaveBeenCalledWith("/projects");
    expect(redirect).toHaveBeenCalledWith(`/projects/${projectId}?notice=created`);
  });
  it("warns about uncertain creation without promising idempotent project retry", async () => {
    vi.mocked(createProject).mockRejectedValueOnce(new ApiError({ status: 504,
      code: "request_timeout", message: "private network detail" }));
    const result = await createProjectAction(INITIAL_PROJECT_ACTION_STATE, form("Attempted project"));
    expect(result.status).toBe("error");
    expect(result.message).toContain("refresh the projects list before trying again");
    expect(result.message).toContain("creation may already have completed");
    expect(JSON.stringify(result)).not.toContain("private network");
    expect(redirect).not.toHaveBeenCalled();
  });
});
