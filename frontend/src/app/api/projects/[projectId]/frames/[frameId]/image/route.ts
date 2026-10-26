import { requestPng } from "@/lib/api/client";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
const headers = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Cross-Origin-Resource-Policy": "same-origin" };
export async function GET(request: Request, { params }: { params: Promise<{ projectId: string; frameId: string }> }) {
  const { projectId, frameId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(frameId)) return new Response(null, { status: 404, headers });
  if (request.headers.get("sec-fetch-site") === "cross-site") return new Response(null, { status: 403, headers });
  try {
    const bytes = await requestPng(`/api/v1/projects/${projectId}/frames/${frameId}/image`);
    return new Response(bytes.buffer, { headers: { ...headers, "Content-Type": "image/png" } });
  } catch (error) {
    return new Response(null, { status: error instanceof ApiError && error.status === 404 ? 404 : 502, headers });
  }
}
