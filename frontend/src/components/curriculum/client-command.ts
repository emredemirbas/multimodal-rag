export class LearningRequestError extends Error {
  constructor(readonly status: number, readonly code: string) { super(code); }
}

export async function learningRequest(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    method, cache: "no-store", credentials: "same-origin", redirect: "error",
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30_000)]) : AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    let code = "request_failed";
    try { const value: unknown = await response.json();
      if (value && typeof value === "object" && "code" in value && typeof value.code === "string") code = value.code;
    } catch {}
    throw new LearningRequestError(response.status, code);
  }
  return response.status === 204 ? null : response.json();
}

export function learningError(error: unknown): string {
  if (!(error instanceof LearningRequestError)) return "Delivery could not be confirmed. Check delivery before starting a different request.";
  const messages: Record<string, string> = {
    invalid_curriculum_draft: "The draft was not accepted. Check its fields, effort and evidence references.",
    draft_revision_conflict: "A newer draft revision exists. Keep your edits or explicitly discard them to load the latest revision.",
    curriculum_draft_not_found: "The assignment draft is no longer available. A selected source, context or document may have been removed.",
    project_archived: "This project is archived. Restore it before saving or capturing new material.",
    curriculum_source_unavailable: "A selected source changed or has no published text. Refresh the page and choose its current published version.",
    curriculum_evidence_too_large: "The selected text exceeds the saved context limit. Choose fewer sources.",
    documentation_not_enabled: "This saved context does not permit external documentation. Create a new context to change that choice.",
    documentation_policy_changed: "This catalog policy changed. Refresh the page, select the current entry and approve it again.",
    documentation_capture_in_progress: "A capture is already in progress. Check its status. If interrupted, check delivery again after about a minute.",
    documentation_capture_lost: "This capture expired or lost permission. Check the saved context and document before explicitly starting another capture.",
    documentation_limit: "This context has reached its document limit. Delete an approval before adding another.",
    idempotency_conflict: "This request key was already used for different input. Check the saved result before starting another request.",
  };
  if (messages[error.code]) return messages[error.code];
  if (error.status === 401 || error.status === 403) return "Your session could not be verified. Refresh the page and try again.";
  if (error.status === 404) return "The saved context or document is no longer available.";
  if (error.status === 422) return "The request was not accepted. Check the selected material and preferences.";
  if (error.status === 409) return "The saved state changed. Check its status before trying again.";
  return "Delivery could not be confirmed. Check delivery before starting a different request.";
}

export function isCaptureFailure(error: unknown): error is LearningRequestError {
  return error instanceof LearningRequestError && ["documentation_fetch_timeout", "documentation_fetch_unavailable", "documentation_fetch_invalid", "documentation_fetch_not_allowed", "documentation_fetch_busy", "documentation_capture_lost"].includes(error.code);
}
