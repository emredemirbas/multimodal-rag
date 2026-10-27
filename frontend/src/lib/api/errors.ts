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
    unsupported_file: "This transcript form accepts only text .srt and .vtt files. WAV and supported MP4 require their separate operator-enabled experimental forms.",
    invalid_encoding: "Save the transcript as UTF-8, then upload it again.",
    rights_required: "Select the ownership, authorization or license statement that applies to this source.",
    provider_not_configured: "YouTube metadata requires a server-side Data API key. You can upload transcripts without a key.",
    unsupported_url: "Enter a supported HTTPS YouTube video or playlist URL.",
    invalid_state: "Processing state changed. Refresh the sources and try again.",
    idempotency_conflict: "This request key was used for different input. Select the file again to start a new upload.",
    project_archived: "Restore the project before adding sources.",
    source_limit: "This project has reached its current limit of 200 sources.",
    retry_limit: "Retry limit reached. Correct the problem and upload a new source.",
    playlist_item_busy: "Wait for or cancel this video's current transcript processing before uploading its replacement.",
    audio_upload_disabled: "Local WAV upload is disabled. Explicit local ASR setup and operator opt-in are required; use an authorized SRT/VTT transcript meanwhile.",
    invalid_audio_type: "Choose a WAV file. Video, compressed audio and URL downloads are not supported.",
    audio_too_large: "Choose a non-empty WAV file of at most 20 MB.",
    audio_duration_limit: "The WAV must be at most 10 minutes long.",
    unsupported_wav_encoding: "Export the WAV as 16-bit PCM, 16 kHz, mono, then select it again.",
    invalid_wav: "The WAV structure is invalid or incomplete. Export it again.",
    invalid_asr_language: "Choose automatic, English or Turkish speech recognition.",
    invalid_audio_form: "Select one WAV file, ownership, speech language and temporary-retention acknowledgement; optionally select one current playlist lesson.",
    audio_upload_timeout: "Upload delivery timed out. It may already be queued; refresh sources or resend the unchanged file with the same request key.",
    audio_reupload_required: "The original audio is retired. Transcribing again requires a new authorized upload.",
    video_upload_disabled: "Local MP4 upload is disabled. Explicit local-visual setup and operator opt-in are required; transcripts remain available.",
    video_upload_busy: "Another video delivery is in progress. Retry the unchanged file and request key shortly.",
    invalid_video_type: "Choose one supported MP4: H.264/avc1, yuv420p, at most 1080p/60 fps. Audio is not transcribed.",
    invalid_video_input: "The MP4 container or filename is invalid. Use an authorized supported MP4 of at most 100 MB.",
    video_too_large: "Choose a non-empty MP4 file of at most 100 MB.",
    invalid_video_form: "Select one MP4, ownership, OCR language and temporary-original/permitted-frames retention acknowledgement.",
    invalid_visual_language: "Choose English, Turkish or experimental combined English/Turkish OCR.",
    video_upload_timeout: "Upload delivery timed out. It may already be queued; refresh sources or resend the unchanged file with the same request key.",
    video_reupload_required: "The original video is retired. Extracting again requires a new authorized MP4 upload.",
    visual_initiator_required: "The original video initiator must retry this processing workflow.",
    alignment_not_ready: "Wait for a complete retained gallery and a successfully published transcript, then retry the comparison.",
    invalid_alignment: "Choose a transcript from the same recording, confirm the pairing and use a whole-millisecond offset between −600000 and +600000.",
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
