import "server-only";

import {
  parseProject,
  parseProjectList,
  type Project,
  type ProjectList,
  type ProjectListStatus,
} from "@/lib/api/contracts";
import { ApiError, apiErrorFromResponse } from "@/lib/api/errors";

const REQUEST_TIMEOUT_MS = 8_000;

interface ApiConfiguration {
  baseUrl: URL;
  token: string;
}

function configuration(): ApiConfiguration {
  const rawBaseUrl = process.env.API_INTERNAL_URL;
  const token = process.env.DEVELOPMENT_AUTH_TOKEN;

  if (!rawBaseUrl || !token) {
    throw new ApiError({
      status: 503,
      code: "frontend_not_configured",
      message: "The server-side API connection is not configured",
    });
  }

  let baseUrl: URL;
  try {
    baseUrl = new URL(rawBaseUrl.endsWith("/") ? rawBaseUrl : `${rawBaseUrl}/`);
  } catch (cause) {
    throw new ApiError({
      status: 503,
      code: "frontend_not_configured",
      message: "API_INTERNAL_URL is invalid",
      cause,
    });
  }

  if (baseUrl.protocol !== "http:" && baseUrl.protocol !== "https:") {
    throw new ApiError({
      status: 503,
      code: "frontend_not_configured",
      message: "API_INTERNAL_URL must use HTTP or HTTPS",
    });
  }

  return { baseUrl, token };
}

async function requestJson(
  path: string,
  init: Omit<RequestInit, "cache" | "credentials"> = {},
): Promise<unknown> {
  const { baseUrl, token } = configuration();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(new URL(path.replace(/^\//, ""), baseUrl), {
      ...init,
      cache: "no-store",
      credentials: "omit",
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      throw await apiErrorFromResponse(response);
    }
    if (response.status === 204) {
      return null;
    }

    try {
      return await response.json();
    } catch (cause) {
      throw new ApiError({
        status: 502,
        code: "invalid_api_response",
        message: "The API returned invalid JSON",
        requestId: response.headers.get("x-request-id"),
        cause,
      });
    }
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError({
        status: 504,
        code: "request_timeout",
        message: "The API request timed out",
        cause: error,
      });
    }
    throw new ApiError({
      status: 503,
      code: "upstream_unavailable",
      message: "The API could not be reached",
      cause: error,
    });
  } finally {
    clearTimeout(timeout);
  }
}

function serializeTitle(title: string): string {
  return JSON.stringify({ title });
}

export async function listProjects(status: ProjectListStatus): Promise<ProjectList> {
  const payload = await requestJson(
    `/api/v1/projects?status=${encodeURIComponent(status)}`,
  );
  try {
    return parseProjectList(payload);
  } catch (cause) {
    throw new ApiError({
      status: 502,
      code: "invalid_api_response",
      message: "The API returned an invalid project list",
      cause,
    });
  }
}

export async function getProject(projectId: string): Promise<Project> {
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}`);
  try {
    return parseProject(payload);
  } catch (cause) {
    throw new ApiError({
      status: 502,
      code: "invalid_api_response",
      message: "The API returned an invalid project",
      cause,
    });
  }
}

export async function createProject(title: string): Promise<Project> {
  const payload = await requestJson("/api/v1/projects", {
    method: "POST",
    body: serializeTitle(title),
  });
  try {
    return parseProject(payload);
  } catch (cause) {
    throw new ApiError({
      status: 502,
      code: "invalid_api_response",
      message: "The API returned an invalid project",
      cause,
    });
  }
}

export async function renameProject(projectId: string, title: string): Promise<Project> {
  const payload = await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    body: serializeTitle(title),
  });
  try {
    return parseProject(payload);
  } catch (cause) {
    throw new ApiError({
      status: 502,
      code: "invalid_api_response",
      message: "The API returned an invalid project",
      cause,
    });
  }
}

export async function archiveProject(projectId: string): Promise<Project> {
  const payload = await requestJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/archive`,
    { method: "POST" },
  );
  try {
    return parseProject(payload);
  } catch (cause) {
    throw new ApiError({
      status: 502,
      code: "invalid_api_response",
      message: "The API returned an invalid project",
      cause,
    });
  }
}

export async function restoreProject(projectId: string): Promise<Project> {
  const payload = await requestJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/restore`,
    { method: "POST" },
  );
  try {
    return parseProject(payload);
  } catch (cause) {
    throw new ApiError({
      status: 502,
      code: "invalid_api_response",
      message: "The API returned an invalid project",
      cause,
    });
  }
}

export async function deleteProject(projectId: string): Promise<void> {
  await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}
