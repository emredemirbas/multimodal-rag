import "server-only";
import { NextResponse } from "next/server";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/source-contracts";

export function validateChatIds(...values: string[]): void {
  if (values.some((value) => !UUID_PATTERN.test(value))) throw new ApiError({ status: 404 });
}
export function chatProxyError(error: unknown): NextResponse {
  return NextResponse.json({ message: publicErrorMessage(error) }, {
    status: error instanceof ApiError ? error.status : 502, headers: { "Cache-Control": "no-store" },
  });
}
export async function chatRequestBody(request: Request): Promise<string> {
  // Server credentials must not turn a cross-origin request into an authorized write.
  const host = request.headers.get("host") ?? new URL(request.url).host;
  // Next's standalone server canonicalizes request.url to its container hostname.
  // The browser-facing Host is authoritative for same-origin, not that internal URL.
  if (/[\s/@\\]/.test(host)) throw new ApiError({ status: 403 });
  let expectedOrigin: string;
  try { expectedOrigin = new URL(`${new URL(request.url).protocol}//${host}`).origin; }
  catch { throw new ApiError({ status: 403 }); }
  if (request.headers.get("origin") !== expectedOrigin) throw new ApiError({ status: 403 });
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
