import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { requestJson } from "@/lib/api/client";

// Capture can legally exceed the ordinary eight-second request window. Exercise
// real transport cancellation rather than just checking an options object.
describe("bounded server request windows and deletion receipts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubEnv("API_INTERNAL_URL", "http://api.test:8000");
    vi.stubEnv("DEVELOPMENT_AUTH_TOKEN", "synthetic-server-only-token");
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

  it("allows the capture window while ordinary calls still time out at eight seconds", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: URL, init: RequestInit) => new Promise<Response>((resolve, reject) => {
      const timer = setTimeout(() => resolve(Response.json({ ok: true })), 12_000);
      init.signal!.addEventListener("abort", () => { clearTimeout(timer); reject(Object.assign(new Error("Aborted"), { name: "AbortError" })); });
    })));
    const ordinary = expect(requestJson("/ordinary")).rejects.toMatchObject({ status: 504, code: "request_timeout" });
    const capture = requestJson("/capture", { method: "POST", body: "{}" }, undefined, { timeoutMs: 25_000 });
    await vi.advanceTimersByTimeAsync(12_001);
    await ordinary;
    await expect(capture).resolves.toEqual({ ok: true });
  });

  it("does not accept a successful JSON-null response as confirmation of deletion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(null)));
    await expect(requestJson("/delete", { method: "DELETE" }, undefined, { expectedStatus: 204 })).rejects.toMatchObject({ status: 502 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(requestJson("/delete", { method: "DELETE" }, undefined, { expectedStatus: 204 })).resolves.toBeNull();
  });
});
