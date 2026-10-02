import { describe, expect, it } from "vitest";
import { consumeChatStream } from "@/lib/chat-stream";

const id = "12345678-1234-1234-1234-123456789abc";
export const turn = { id, sequence: 1, question: "health?", source_ids: [], created_at: "2026-10-02T00:00:00Z",
  response: { answer: "No evidence found.", abstained: true, citations: [], provider: "local-deterministic", model: "test" } };

function stream(text: string, split = false) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({ start(controller) {
    if (split) for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    else controller.enqueue(bytes);
    controller.close();
  } });
}
describe("validated SSE delivery", () => {
  it("handles split frames and UTF-8 without trusting partial content as a final turn", async () => {
    let text = "";
    const result = await consumeChatStream(stream(`event: start\ndata: {}\n\nevent: delta\ndata: {"text":"öğren"}\n\nevent: complete\ndata: ${JSON.stringify(turn)}\n\n`, true), (chunk) => text += chunk);
    expect(text).toBe("öğren"); expect(result.id).toBe(id);
  });
  it("rejects incomplete, malformed, failed and oversized streams", async () => {
    await expect(consumeChatStream(stream('event: delta\ndata: {"text":"partial"}\n\n'), () => {})).rejects.toThrow("Incomplete");
    await expect(consumeChatStream(stream('event: error\ndata: {"code":"unavailable"}\n\n'), () => {})).rejects.toThrow();
    await expect(consumeChatStream(stream('event: delta\ndata: {"text":42}\n\n'), () => {})).rejects.toThrow();
    await expect(consumeChatStream(stream("x".repeat(128_001)), () => {})).rejects.toThrow("limit");
  });
  it("rejects a forged citation, invalid interval and unsupported final shape", async () => {
    const invalid = { ...turn, response: { ...turn.response, abstained: false, citations: [{ segment_id: "wrong-project-id" }] } };
    await expect(consumeChatStream(stream(`event: complete\ndata: ${JSON.stringify(invalid)}\n\n`), () => {})).rejects.toThrow();
  });
});
