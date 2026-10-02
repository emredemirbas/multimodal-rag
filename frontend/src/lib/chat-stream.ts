import { parseTurn, type ChatTurn } from "@/lib/api/chat-contracts";

export async function consumeChatStream(body: ReadableStream<Uint8Array>, onDelta: (text: string) => void): Promise<ChatTurn> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "", bytes = 0, answerLength = 0;
  let complete: ChatTurn | null = null;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > 128_000) throw new Error("Stream limit exceeded");
      buffer += decoder.decode(chunk.value, { stream: true });
      if (buffer.length > 64_000) throw new Error("Stream frame limit exceeded");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = frame.split("\n").find((line) => line.startsWith("event: "))?.slice(7);
        const data = JSON.parse(frame.split("\n").find((line) => line.startsWith("data: "))?.slice(6) ?? "null");
        if (complete) throw new Error("Unexpected frame after completion");
        if (event === "delta") {
          if (!data || typeof data.text !== "string") throw new Error("Invalid stream delta");
          answerLength += data.text.length;
          if (answerLength > 12_000) throw new Error("Answer limit exceeded");
          onDelta(data.text);
        } else if (event === "complete") {
          complete = parseTurn(data);
        } else if (event === "error") {
          throw new Error("The persisted response is no longer available");
        } else if (event !== "start") {
          throw new Error("Invalid stream event");
        }
      }
    }
    if (!complete || buffer.trim() || decoder.decode()) throw new Error("Incomplete answer delivery");
    return complete;
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
