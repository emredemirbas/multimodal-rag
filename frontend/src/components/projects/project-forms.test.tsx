import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createProjectAction, renameProjectAction } from "@/app/actions/projects";
import { ProjectCreateForm } from "@/components/projects/project-create-form";
import { ProjectRenameForm } from "@/components/projects/project-rename-form";
import type { ProjectActionState } from "@/lib/action-state";

vi.mock("@/app/actions/projects", () => ({
  createProjectAction: vi.fn(),
  renameProjectAction: vi.fn(),
}));

const projectId = "12345678-1234-4234-8234-123456789abc";
const attemptedTitle = "Attempted project title";

function failure(validation: boolean, version = 1): ProjectActionState {
  return {
    status: "error",
    message: validation ? "Check the project name and try again." : "The project service is temporarily unavailable. Please try again.",
    fieldErrors: validation ? { title: "Project names must be 120 characters or fewer." } : {},
    reference: validation ? null : "public-request-reference",
    version,
  };
}

function renderForm(kind: "create" | "rename") {
  return render(kind === "create"
    ? <ProjectCreateForm />
    : <ProjectRenameForm projectId={projectId} title="Original project" />);
}

describe("project title drafts", () => {
  beforeEach(() => { vi.resetAllMocks(); });

  it.each([
    ["create", "validation"],
    ["create", "service"],
    ["rename", "validation"],
    ["rename", "service"],
  ] as const)("preserves the %s draft after a returned %s error", async (kind, errorKind) => {
    const action = kind === "create" ? vi.mocked(createProjectAction) : vi.mocked(renameProjectAction);
    const error = failure(errorKind === "validation");
    const draft = errorKind === "validation" ? "x".repeat(121) : attemptedTitle;
    action.mockResolvedValueOnce(error);
    renderForm(kind);
    const input = screen.getByLabelText("Project name");
    fireEvent.change(input, { target: { value: draft } });
    await act(async () => { fireEvent.submit(input.closest("form")!); });
    expect(action).toHaveBeenCalledTimes(1);
    expect(action.mock.calls[0][1].get("title")).toBe(draft);
    expect(screen.getByRole("alert")).toHaveTextContent(error.message);
    expect(input).toHaveValue(draft);
    expect(input).toHaveAttribute("aria-invalid", errorKind === "validation" ? "true" : "false");
    if (errorKind === "validation") expect(input).toHaveAccessibleDescription(/120 characters or fewer/);
    else expect(screen.getByRole("alert")).toHaveTextContent("public-request-reference");
  });

  it.each(["create", "rename"] as const)("locks the %s draft and announces pending state until an error returns", async (kind) => {
    const action = kind === "create" ? vi.mocked(createProjectAction) : vi.mocked(renameProjectAction);
    let complete!: (state: ProjectActionState) => void;
    action.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    renderForm(kind);
    const input = screen.getByLabelText("Project name");
    const form = input.closest("form")!;
    fireEvent.change(input, { target: { value: attemptedTitle } });
    act(() => { fireEvent.submit(form); });
    try {
      expect(form).toHaveAttribute("aria-busy", "true");
      expect(input).toBeDisabled();
      expect(input).toHaveValue(attemptedTitle);
      expect(screen.getByRole("button", { name: kind === "create" ? "Creating project…" : "Saving…" })).toBeDisabled();
      expect(action.mock.calls[0][1].get("title")).toBe(attemptedTitle);
    } finally {
      // Settle even a red pending assertion so React cannot entangle the next test.
      await act(async () => { complete(failure(false)); });
    }
    expect(form).toHaveAttribute("aria-busy", "false");
    expect(input).toBeEnabled();
    expect(input).toHaveValue(attemptedTitle);
    expect(screen.getByRole("button", { name: kind === "create" ? "Create project" : "Save name" })).toBeEnabled();
  });

  it.each(["create", "rename"] as const)("submits the corrected %s draft after a validation error", async (kind) => {
    const action = kind === "create" ? vi.mocked(createProjectAction) : vi.mocked(renameProjectAction);
    action.mockResolvedValueOnce(failure(true)).mockResolvedValueOnce(failure(false, 2));
    renderForm(kind);
    const input = screen.getByLabelText("Project name");
    const original = "x".repeat(121);
    fireEvent.change(input, { target: { value: original } });
    await act(async () => { fireEvent.submit(input.closest("form")!); });
    expect(input).toHaveValue(original);
    fireEvent.change(input, { target: { value: "Corrected project title" } });
    await act(async () => { fireEvent.submit(input.closest("form")!); });
    expect(action).toHaveBeenCalledTimes(2);
    expect(action.mock.calls[1][0].version).toBe(1);
    expect(action.mock.calls[1][1].get("title")).toBe("Corrected project title");
    if (kind === "rename") expect(action.mock.calls[1][1].get("projectId")).toBe(projectId);
    expect(input).toHaveValue("Corrected project title");
    expect(input).toHaveAttribute("aria-invalid", "false");
    expect(screen.getByRole("alert")).toHaveTextContent(failure(false).message);
  });

  it("shows the server-accepted canonical title after a successful rename", async () => {
    vi.mocked(renameProjectAction).mockResolvedValueOnce({
      status: "success", message: "Project name updated.", fieldErrors: {}, reference: null,
      version: 1, acceptedTitle: "Canonical project",
    });
    renderForm("rename");
    const input = screen.getByLabelText("Project name");
    fireEvent.change(input, { target: { value: "  Canonical project  " } });
    await act(async () => { fireEvent.submit(input.closest("form")!); });
    expect(vi.mocked(renameProjectAction).mock.calls[0][1].get("title")).toBe("  Canonical project  ");
    expect(input).toHaveValue("Canonical project");
    expect(screen.getByRole("status")).toHaveTextContent("Project name updated.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("preserves an unsaved or failed rename draft through same-project prop refreshes", async () => {
    vi.mocked(renameProjectAction).mockResolvedValueOnce(failure(false));
    const { rerender } = render(<ProjectRenameForm key={projectId} projectId={projectId} title="Original project" />);
    const input = screen.getByLabelText("Project name");
    fireEvent.change(input, { target: { value: attemptedTitle } });
    rerender(<ProjectRenameForm key={projectId} projectId={projectId} title="Refreshed project name" />);
    expect(input).toHaveValue(attemptedTitle);
    await act(async () => { fireEvent.submit(input.closest("form")!); });
    rerender(<ProjectRenameForm key={projectId} projectId={projectId} title="Another refreshed name" />);
    expect(input).toHaveValue(attemptedTitle);
    expect(screen.getByRole("alert")).toHaveTextContent(failure(false).message);
  });

  it("updates a pristine rename title when the same project's saved title refreshes", () => {
    const { rerender } = render(<ProjectRenameForm key={projectId} projectId={projectId} title="Original project" />);
    const input = screen.getByLabelText("Project name");
    expect(input).toHaveValue("Original project");
    rerender(<ProjectRenameForm key={projectId} projectId={projectId} title="Refreshed project name" />);
    expect(input).toHaveValue("Refreshed project name");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not carry a rename draft or error into another project when keyed by project identity", async () => {
    vi.mocked(renameProjectAction).mockResolvedValue(failure(false));
    const { rerender } = render(<ProjectRenameForm key={projectId} projectId={projectId} title="Original project" />);
    const input = screen.getByLabelText("Project name");
    fireEvent.change(input, { target: { value: attemptedTitle } });
    await act(async () => { fireEvent.submit(input.closest("form")!); });
    const otherProjectId = "22345678-1234-4234-8234-123456789abc";
    rerender(<ProjectRenameForm key={otherProjectId} projectId={otherProjectId} title="Other project" />);
    const otherInput = screen.getByLabelText("Project name");
    expect(otherInput).toHaveValue("Other project");
    expect(otherInput).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.change(otherInput, { target: { value: "Other project renamed" } });
    await act(async () => { fireEvent.submit(otherInput.closest("form")!); });
    const second = vi.mocked(renameProjectAction).mock.calls[1][1];
    expect(second.get("projectId")).toBe(otherProjectId);
    expect(second.get("title")).toBe("Other project renamed");
  });
});
