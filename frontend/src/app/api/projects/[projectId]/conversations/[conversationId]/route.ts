import { NextResponse } from "next/server";
import { getHistory } from "@/lib/api/chat";
import { chatProxyError, validateChatIds } from "@/lib/api/chat-proxy";

export async function GET(_request: Request, { params }: { params: Promise<{ projectId: string; conversationId: string }> }) {
  try {
    const { projectId, conversationId } = await params;
    validateChatIds(projectId, conversationId);
    return NextResponse.json(await getHistory(projectId, conversationId), { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return chatProxyError(error); }
}
