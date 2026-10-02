export const PROJECT_STATUSES = ["active", "archived"] as const;

export type ProjectStatus = (typeof PROJECT_STATUSES)[number];
export type ProjectListStatus = ProjectStatus | "all";

export interface Project {
  id: string;
  tenant_id: string;
  title: string;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface ProjectList {
  items: Project[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function isProjectStatus(value: unknown): value is ProjectStatus {
  return value === "active" || value === "archived";
}

export function parseProject(value: unknown): Project {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    typeof value.tenant_id !== "string" ||
    typeof value.title !== "string" ||
    !isProjectStatus(value.status) ||
    !isIsoDate(value.created_at) ||
    !isIsoDate(value.updated_at) ||
    (value.archived_at !== null && !isIsoDate(value.archived_at))
  ) {
    throw new TypeError("Project response did not match the API contract");
  }

  return {
    id: value.id,
    tenant_id: value.tenant_id,
    title: value.title,
    status: value.status,
    created_at: value.created_at,
    updated_at: value.updated_at,
    archived_at: value.archived_at,
  };
}

export function parseProjectList(value: unknown): ProjectList {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new TypeError("Project list response did not match the API contract");
  }

  return { items: value.items.map(parseProject) };
}
