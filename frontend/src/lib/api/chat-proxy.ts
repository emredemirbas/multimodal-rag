import "server-only";
import { NextResponse } from "next/server";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/source-contracts";
import { requireSameOrigin } from "@/lib/api/request-origin";

export function validateChatIds(...values: string[]): void {
  if (values.some((value) => !UUID_PATTERN.test(value))) throw new ApiError({ status: 404 });
}
export function chatProxyError(error: unknown): NextResponse {
  const safeCodes = new Set(['local_model_unavailable', 'local_model_not_installed', 'local_model_busy', 'invalid_model_answer',
    'local_embeddings_unavailable', 'local_embeddings_not_installed', 'local_embeddings_busy', 'embedding_model_changed',
    'invalid_embeddings', 'embedding_input_limit', 'request_timeout', 'project_archived', 'idempotency_conflict', 'message_too_large']);
  const code = error instanceof ApiError && safeCodes.has(error.code) ? error.code : 'request_failed';
  return NextResponse.json({ code, message: publicErrorMessage(error) }, {
    status: error instanceof ApiError ? error.status : 502, headers: { "Cache-Control": "no-store" },
  });
}
export async function chatRequestBody(request: Request): Promise<string> {
  // Server credentials must not turn a cross-origin request into an authorized write.
  requireSameOrigin(request);
  if (!request.headers.get("content-type")?.startsWith("application/json")) throw new ApiError({ status: 415 });
  const reader = request.body?.getReader();
  if (!reader) throw new ApiError({ status: 422 });
  let content = "", bytes = 0;
  const decoder = new TextDecoder("utf-8", { fatal: true });
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > 16_384) throw new ApiError({ status: 413, code: "message_too_large" });
      content += decoder.decode(chunk.value, { stream: true });
    }
    content += decoder.decode();
    JSON.parse(content);
    return content;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError({ status: 422 });
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
