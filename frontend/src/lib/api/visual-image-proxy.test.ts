import { afterEach, describe, expect, it, vi } from "vitest";
import { requestPng } from "@/lib/api/client";
import { GET } from "@/app/api/projects/[projectId]/frames/[frameId]/image/route";
import { projectId, visualFixture } from "../../../test-support/visual-fixture";

// Transport-only fixture; native PNG integrity is checked by the API tests.
const png = new Uint8Array([137,80,78,71,13,10,26,10,0]);
const frameId = visualFixture().items[0].id;
function configure() {
  vi.stubEnv("API_INTERNAL_URL", "http://api.test:8000");
  vi.stubEnv("DEVELOPMENT_AUTH_TOKEN", "private-test-token");
}
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.useRealTimers(); });
describe("private PNG proxy", () => {
  it("forwards server credentials only upstream and disables redirects/caching", async () => {
    configure();
    const fetch = vi.fn().mockResolvedValue(new Response(png, { headers: { "Content-Type": "image/png", "Content-Length": "9" } }));
    vi.stubGlobal("fetch", fetch);
    const response = await GET(new Request("http://localhost/frame"), { params: Promise.resolve({ projectId, frameId }) });
    expect(response.status).toBe(200); expect(new Uint8Array(await response.arrayBuffer())).toEqual(png);
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(response.headers.get("cross-origin-resource-policy")).toBe("same-origin");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.has("authorization")).toBe(false);
    expect(fetch.mock.calls[0][1]).toMatchObject({ redirect: "error", cache: "no-store", credentials: "omit", headers: { Authorization: "Bearer private-test-token" } });
  });
  it.each(["mime", "signature", "oversize", "short"])("rejects %s payloads with safe empty error bodies", async (kind) => {
    configure();
    const data = kind === "signature" ? new Uint8Array(9) : kind === "oversize" ? new Uint8Array(600001) : png;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(data, { headers: { "Content-Type": kind === "mime" ? "image/svg+xml" : "image/png", "Content-Length": kind === "short" ? "10" : String(data.length) } })));
    const response = await GET(new Request("http://localhost/frame"), { params: Promise.resolve({ projectId, frameId }) });
    expect(response.status).toBe(502); expect(await response.text()).toBe("");
  });
  it("rejects actual streamed overflow despite a false short header", async () => {
    configure();
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(600001)); controller.close(); } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, { headers: { "Content-Type": "image/png", "Content-Length": "9" } })));
    await expect(requestPng("/private.png")).rejects.toMatchObject({ status: 502 });
  });
  it("rejects malformed IDs and cross-site image embedding before forwarding", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const invalid = await GET(new Request("http://localhost/frame"), { params: Promise.resolve({ projectId: "../foreign", frameId }) });
    const crossSite = await GET(new Request("http://localhost/frame", { headers: { "sec-fetch-site": "cross-site" } }), { params: Promise.resolve({ projectId, frameId }) });
    expect(invalid.status).toBe(404); expect(crossSite.status).toBe(403); expect(fetch).not.toHaveBeenCalled();
  });
  it("bounds an unfinished upstream read", async () => {
    configure(); vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(new Error("PRIVATE_TIMEOUT_DETAIL")));
    })));
    const promise = requestPng("/private.png");
    const assertion = expect(promise).rejects.toMatchObject({ status: 504 });
    await vi.advanceTimersByTimeAsync(8001); await assertion;
  });
});
