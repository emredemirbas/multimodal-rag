import { describe, expect, it, vi } from "vitest";
vi.mock("server-only", () => ({}));
import { chatProxyError, chatRequestBody, validateChatIds } from "@/lib/api/chat-proxy";
import { ApiError } from '@/lib/api/errors';

describe("server-owned chat proxy", () => {
  it("rejects malformed paths, missing origin and cross-origin writes", async () => {
    expect(() => validateChatIds("../another-project")).toThrow();
    await expect(chatRequestBody(new Request("http://localhost/api/chat", { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } }))).rejects.toMatchObject({ status: 403 });
    await expect(chatRequestBody(new Request("http://localhost/api/chat", { method: "POST", body: "{}", headers: { "Origin": "https://attacker.example", "Content-Type": "application/json" } }))).rejects.toMatchObject({ status: 403 });
  });
  it("bounds streamed input before JSON parsing and accepts same-origin JSON", async () => {
    const make = (body: string) => new Request("http://localhost/api/chat", { method: "POST", body, headers: { "Origin": "http://localhost", "Content-Type": "application/json" } });
    expect(await chatRequestBody(make('{"question":"health?"}'))).toContain("health");
    await expect(chatRequestBody(make("x".repeat(16_385)))).rejects.toMatchObject({ status: 413 });
    await expect(chatRequestBody(make("not-json"))).rejects.toMatchObject({ status: 422 });
  });
  it("uses the browser-facing Host when Next canonicalizes its internal URL", async () => {
    const make = (origin: string) => new Request("http://0.0.0.0:3000/api/chat", { method: "POST", body: "{}",
      headers: { "Host": "localhost:3000", "Origin": origin, "Content-Type": "application/json" } });
    expect(await chatRequestBody(make("http://localhost:3000"))).toBe("{}");
    await expect(chatRequestBody(make("http://attacker.example"))).rejects.toMatchObject({ status: 403 });
  });
  it('preserves only allowlisted recovery codes without leaking raw errors', async () => {
    const local = chatProxyError(new ApiError({status:503,code:'local_embeddings_not_installed',message:'private input'}));
    expect(local.status).toBe(503);
    expect(await local.json()).toMatchObject({code:'local_embeddings_not_installed'});
    const unsafe = chatProxyError(new ApiError({status:503,code:'private model input',message:'secret'}));
    const payload = await unsafe.json();
    expect(payload.code).toBe('request_failed');
    expect(JSON.stringify(payload)).not.toMatch(/private|secret/);
  });
});
