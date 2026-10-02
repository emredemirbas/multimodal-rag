import { NextResponse } from "next/server";
import { requestJson } from "@/lib/api/client";
import { conversationPath, listConversations } from "@/lib/api/chat";
import { parseConversation } from "@/lib/api/chat-contracts";
import { chatProxyError, chatRequestBody, validateChatIds } from "@/lib/api/chat-proxy";

type Context = { params: Promise<{ projectId: string }> };
export async function GET(_request: Request, { params }: Context) {
  try {
    const { projectId } = await params;
    validateChatIds(projectId);
    return NextResponse.json({ items: await listConversations(projectId) }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return chatProxyError(error); }
}
export async function POST(request: Request, { params }: Context) {
  try {
    const { projectId } = await params;
    validateChatIds(projectId);
    const body = await chatRequestBody(request);
    const conversation = parseConversation(await requestJson(conversationPath(projectId), { method: "POST", body }));
    return NextResponse.json(conversation, { status: 201, headers: { "Cache-Control": "no-store" } });
  } catch (error) { return chatProxyError(error); }
}
