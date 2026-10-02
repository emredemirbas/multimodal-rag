const DEFAULT_ERROR_CODE = "request_failed";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;

  constructor(options: {
    status: number;
    code?: string;
    message?: string;
    requestId?: string | null;
    cause?: unknown;
  }) {
    super(options.message ?? "The API request failed", { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code ?? DEFAULT_ERROR_CODE;
    this.requestId = options.requestId ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let payload: unknown;

  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  const code =
    isRecord(payload) && typeof payload.code === "string"
      ? payload.code.slice(0, 80)
      : DEFAULT_ERROR_CODE;

  return new ApiError({
    status: response.status,
    code,
    requestId: response.headers.get("x-request-id"),
  });
}

export function publicErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Something went wrong. Please try again.";
  }

  const sourceErrors: Record<string, string> = {
    upload_too_large: "Choose a non-empty transcript file of at most 2 MB.",
    unsupported_file: "Only text .srt and .vtt files are supported. Audio/video processing is not yet available.",
    invalid_encoding: "Save the transcript as UTF-8, then upload it again.",
    rights_required: "Select the ownership, authorization or license statement that applies to this source.",
    provider_not_configured: "YouTube metadata requires a server-side Data API key. You can upload transcripts without a key.",
    unsupported_url: "Enter a supported HTTPS YouTube video or playlist URL.",
    invalid_state: "Processing state changed. Refresh the sources and try again.",
    idempotency_conflict: "This request key was used for different input. Select the file again to start a new upload.",
    project_archived: "Restore the project before adding sources.",
    source_limit: "This project has reached its current limit of 200 sources.",
    retry_limit: "Retry limit reached. Correct the problem and upload a new source.",
  };
  if (sourceErrors[error.code]) return sourceErrors[error.code];

  if (error.status === 401 || error.status === 403) {
    return "Your session could not be verified. Please refresh and try again.";
  }
  if (error.status === 404) {
    return "The project could not be found.";
  }
  if (error.status === 409) {
    return "The project changed while you were editing it. Refresh and try again.";
  }
  if (error.status === 422) {
    return "The project information was not accepted. Check the form and try again.";
  }
  if (error.status === 504 || error.code === "request_timeout") {
    return "The service took too long to respond. Please try again.";
  }
  if (error.status >= 500) {
    return "The project service is temporarily unavailable. Please try again.";
  }

  return "The request could not be completed. Please try again.";
}

export function errorReference(error: unknown): string | null {
  if (!(error instanceof ApiError) || !error.requestId) {
    return null;
  }
  return error.requestId;
}
