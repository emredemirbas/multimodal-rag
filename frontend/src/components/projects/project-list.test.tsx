import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProjectList } from "@/components/projects/project-list";
import type { Project } from "@/lib/api/contracts";

const ACTIVE_PROJECT: Project = {
  id: "e6071280-749a-4aa1-8156-d525789c6a8f",
  tenant_id: "tenant-a",
  title: "FastAPI fundamentals",
  status: "active",
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-21T10:00:00Z",
  archived_at: null,
};

describe("ProjectList", () => {
  it("explains the next action when the active list is empty", () => {
    render(<ProjectList projects={[]} status="active" />);

    expect(screen.getByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
    expect(screen.getByText(/create a private project/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a project" })).toHaveAttribute(
      "href",
      "#create-project",
    );
  });

  it("renders project names, textual statuses, and named navigation links", () => {
    const archived: Project = {
      ...ACTIVE_PROJECT,
      id: "61d032b7-ea97-4c56-b0fc-dbf7a8a40494",
      title: "Pydantic models",
      status: "archived",
      archived_at: "2026-09-21T11:00:00Z",
    };

    render(<ProjectList projects={[ACTIVE_PROJECT, archived]} status="all" />);

    expect(screen.getByRole("link", { name: "FastAPI fundamentals" })).toHaveAttribute(
      "href",
      `/projects/${ACTIVE_PROJECT.id}`,
    );
    expect(screen.getByLabelText("Status: active")).toHaveTextContent("Active");
    expect(screen.getByLabelText("Status: archived")).toHaveTextContent("Archived");
    expect(screen.getByRole("link", { name: "Open Pydantic models" })).toHaveAttribute(
      "href",
      `/projects/${archived.id}`,
    );
  });
});
