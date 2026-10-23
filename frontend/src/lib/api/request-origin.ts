import "server-only";
import { ApiError } from "@/lib/api/errors";

export function requireSameOrigin(request: Request): void {
  // Next standalone canonicalizes URL to its container name. Use browser-facing
  // Host, never forwarded headers or a client-supplied upstream URL.
  const host = request.headers.get("host") ?? new URL(request.url).host;
  if (/[\s/@\\]/.test(host)) throw new ApiError({ status: 403 });
  let origin: string;
  try { origin = new URL(`${new URL(request.url).protocol}//${host}`).origin; }
  catch { throw new ApiError({ status: 403 }); }
  if (request.headers.get("origin") !== origin) throw new ApiError({ status: 403 });
}
