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

export async function requestEventStream(path: string, body: string, signal: AbortSignal): Promise<Response> {
  const { baseUrl, token } = configuration();
  let response: Response;
  try {
    response = await fetch(new URL(path.replace(/^\//, ""), baseUrl), {
      method: "POST", body, cache: "no-store", credentials: "omit",
      headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json", "Accept": "text/event-stream", "X-Request-ID": crypto.randomUUID() },
      signal: AbortSignal.any([signal, AbortSignal.timeout(30_000)]),
    });
  } catch {
    throw new ApiError({ status: 503, code: "stream_unavailable" });
  }
  if (!response.ok) throw await apiErrorFromResponse(response);
  if (!response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) {
    await response.body?.cancel();
    throw new ApiError({ status: 502, code: "invalid_api_response" });
  }
  return response;
}

export async function requestJson(
  path: string,
  init: Omit<RequestInit, "cache" | "credentials"> = {},
  onHeaders?: (headers: Headers) => void,
): Promise<unknown> {
  const { baseUrl, token } = configuration();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (init.body !== undefined && !(init.body instanceof FormData)) {
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
    onHeaders?.(response.headers);
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

export async function requestPng(path: string): Promise<Uint8Array<ArrayBuffer>> {
  const { baseUrl, token } = configuration();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const response = await fetch(new URL(path.replace(/^\//, ""), baseUrl), { cache: "no-store", credentials: "omit", redirect: "error",
      headers: { "Authorization": `Bearer ${token}`, "Accept": "image/png", "X-Request-ID": crypto.randomUUID() }, signal: controller.signal });
    if (!response.ok) throw await apiErrorFromResponse(response);
    const length = response.headers.get("content-length");
    if (response.headers.get("content-type") !== "image/png" || !response.body
        || (length !== null && (!/^[0-9]{1,6}$/.test(length) || Number(length) > 600000 || Number(length) < 1))) {
      await response.body?.cancel(); throw new ApiError({ status: 502, code: "invalid_api_response" });
    }
    reader = response.body.getReader();
    const chunks: Uint8Array[] = []; let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 600000) throw new ApiError({ status: 502, code: "invalid_api_response" });
      chunks.push(value);
    }
    const result = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; }
    if (size < 8 || (length !== null && size !== Number(length))
        || ![137,80,78,71,13,10,26,10].every((byte, index) => result[index] === byte)) throw new ApiError({ status: 502, code: "invalid_api_response" });
    return result;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError({ status: controller.signal.aborted ? 504 : 503, code: "upstream_unavailable" });
  } finally {
    controller.abort(); clearTimeout(timeout);
    if (reader) { try { await reader.cancel(); } catch {} reader.releaseLock(); }
  }
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

export async function deleteProject(projectId: string): Promise<string | null> {
  let cleanupId: string | null = null;
  await requestJson(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  }, (headers) => { cleanupId = headers.get("x-cleanup-id"); });
  return cleanupId;
}
