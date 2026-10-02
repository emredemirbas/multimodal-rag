import { requestEventStream } from "@/lib/api/client";
import { conversationPath } from "@/lib/api/chat";
import { chatProxyError, chatRequestBody, validateChatIds } from "@/lib/api/chat-proxy";

export async function POST(request: Request, { params }: { params: Promise<{ projectId: string; conversationId: string }> }) {
  try {
    const { projectId, conversationId } = await params;
    validateChatIds(projectId, conversationId);
    const body = await chatRequestBody(request);
    const upstream = await requestEventStream(`${conversationPath(projectId)}/${conversationId}/messages`, body, request.signal);
    return new Response(upstream.body, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-store", "X-Accel-Buffering": "no" } });
  } catch (error) { return chatProxyError(error); }
}
