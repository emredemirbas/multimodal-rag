import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SavedContextWorkspace } from "./saved-context-workspace";
import { context, contextId, deferred, documentFixture, excerptId, json, policy, projectId } from "./test-fixtures";
import type { DocumentView } from "@/lib/api/curriculum-contracts";
afterEach(() => vi.unstubAllGlobals());
function show(documents: DocumentView[] = [], archived = false) { return <SavedContextWorkspace projectId={projectId} context={context} archived={archived} catalog={[policy]} initialDocuments={documents} />; }
function approve() {
  fireEvent.change(screen.getByLabelText("Official page"), { target: { value: policy.id } });
  fireEvent.click(screen.getByLabelText("I approve retrieving and retaining this selected page for this context"));
  fireEvent.submit(screen.getByRole("form", { name: "Approve official documentation" }));
}
function routeFetch(onMutation: (url: string, options: RequestInit) => Response | Promise<Response>, doc = documentFixture()) {
  return vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith(`/contexts/${contextId}`) && options.method === "GET") return Promise.resolve(json(context));
    if (options.method === "GET") return Promise.resolve(json(url.endsWith("/documentation") ? [doc] : doc));
    return Promise.resolve(onMutation(url, options));
  });
}
describe("saved context document approval", () => {
  it("makes no automatic request, starts without a page or consent and keeps generation closed", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); render(show());
    expect(fetch).not.toHaveBeenCalled(); expect(screen.getByLabelText("Official page")).toHaveValue("");
    expect(screen.getByRole("checkbox")).not.toBeChecked(); expect(screen.getByRole("button", { name: "Save document approval" })).toBeDisabled();
    expect(screen.getByText(/Assignment generation is not available yet/)).toBeInTheDocument();
    expect(screen.getByText("No retained documentation or approvals are available.")).toBeInTheDocument();
  });
  it("saves explicit policy-bound consent before a separate capture, showing inert text and retained provenance", async () => {
    const fetch = routeFetch((url) => json(documentFixture(url.endsWith("/capture")))); vi.stubGlobal("fetch", fetch); render(show());
    await act(async () => { approve(); });
    expect(fetch.mock.calls.filter(([, options]) => options.method === "POST")).toHaveLength(1);
    const approval = JSON.parse(fetch.mock.calls[0][1].body); expect(approval).toMatchObject({ catalog_id: policy.id, catalog_sha256: policy.fingerprint, consent: "retrieve_and_retain" });
    expect(screen.getByRole("button", { name: "Capture document" })).toBeEnabled();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    expect(fetch.mock.calls.filter(([, options]) => options.method === "POST")).toHaveLength(2);
    expect(screen.getByText('<script>alert("unsafe")</script>\n@app.get("/")', { normalizer: (text) => text })).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull(); expect(document.querySelector("img")).toBeNull();
    expect(screen.getByRole("link", { name: "Excerpt 1" })).toHaveAttribute("href", `#excerpt-${excerptId}`);
    expect(screen.getByText(/unknown \(unversioned page\)/)).toBeInTheDocument();
    expect(screen.getByText(/HTML bytes: 512/)).toBeInTheDocument();
  });
  it("retains an uncertain approval key and does not capture it after recovery", async () => {
    const fetch = routeFetch(() => json(documentFixture())); let fail = true;
    fetch.mockImplementation(async (url: string, options: RequestInit) => {
      if (options.method === "GET") return json(context);
      if (fail) { fail = false; throw new Error("network"); } return json(documentFixture());
    });
    vi.stubGlobal("fetch", fetch); render(show()); await act(async () => { approve(); });
    expect(screen.getByRole("button", { name: "Check approval delivery" })).toBeEnabled();
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    const posts = fetch.mock.calls.filter(([, options]) => options.method === "POST");
    expect(posts).toHaveLength(2); expect(JSON.parse(posts[0][1].body).idempotency_key).toBe(JSON.parse(posts[1][1].body).idempotency_key);
    expect(posts.some(([url]) => url.endsWith("/capture"))).toBe(false);
  });
  it("replays an uncertain approval against its originally selected policy after catalog refresh", async () => {
    let first = true; const fetch = routeFetch(() => { if (first) { first = false; throw new Error("network"); } return json(documentFixture()); });
    vi.stubGlobal("fetch", fetch); const view = render(show()); await act(async () => { approve(); });
    view.rerender(<SavedContextWorkspace projectId={projectId} context={context} archived={false} catalog={[{ ...policy, fingerprint: "e".repeat(64), license_text: "Changed policy notice" }]} initialDocuments={[]} />);
    expect(screen.queryByText("Changed policy notice")).toBeNull();
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    const posts = fetch.mock.calls.filter(([, options]) => options.method === "POST");
    expect(JSON.parse(posts[1][1].body)).toEqual(JSON.parse(posts[0][1].body));
    expect(screen.getByRole("button", { name: "Capture document" })).toBeInTheDocument();
  });
  it.each(["uncertain", "failed"])("uses the correct command identity for %s capture recovery", async (outcome) => {
    let first = true; const keys: string[] = [];
    const fetch = routeFetch((_url, options) => {
      keys.push(JSON.parse(options.body as string).idempotency_key);
      if (first) { first = false; if (outcome === "uncertain") throw new Error("network"); return json({ code: "documentation_fetch_timeout" }, 503); }
      return json(documentFixture(true));
    });
    vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    const button = screen.getByRole("button", { name: outcome === "uncertain" ? "Check capture delivery" : "Retry capture" });
    await act(async () => { fireEvent.click(button); });
    expect(keys).toHaveLength(2); if (outcome === "uncertain") expect(keys[1]).toBe(keys[0]); else expect(keys[1]).not.toBe(keys[0]);
    expect(screen.getByRole("link", { name: "Excerpt 1" })).toBeInTheDocument();
  });
  it("checks capture status with GET requests only and keeps an unknown in-progress request explicit", async () => {
    const active = { ...documentFixture(), status: "capturing" as const };
    const fetch = routeFetch(() => { throw new Error("no writes expected"); }, active); vi.stubGlobal("fetch", fetch); render(show([active]));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check capture status" })); });
    expect(fetch.mock.calls.every(([, options]) => options.method === "GET")).toBe(true);
    expect(screen.getByRole("status")).toHaveTextContent("No new page was retrieved");
    expect(screen.getByRole("button", { name: "Start another capture" })).toBeEnabled();
  });
  it("does not accept a foreign capture receipt and keeps its unchanged delivery command", async () => {
    const keys: string[] = []; let first = true;
    const fetch = routeFetch((_url, options) => { keys.push(JSON.parse(options.body as string).idempotency_key); const receipt = documentFixture(true); if (first) { first = false; return json({ ...receipt, project_id: "72345678-1234-4234-8234-123456789abc" }); } return json(receipt); });
    vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check capture delivery" })); });
    expect(keys[0]).toBe(keys[1]); expect(screen.getByRole("link", { name: "Excerpt 1" })).toBeInTheDocument();
  });
  it("prevents duplicate capture delivery while allowing its explicit deletion", async () => {
    const pending = deferred<Response>(); const fetch = routeFetch(() => pending.promise); vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Capturing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete document" })).toBeEnabled();
    await act(async () => { pending.resolve(json(documentFixture(true))); });
    await waitFor(() => expect(screen.getByRole("article")).toHaveAttribute("aria-busy", "false"));
  });
  it("blocks writes in archived and tutorial-only contexts while keeping read and deletion available", () => {
    const view = render(show([documentFixture()], true));
    expect(screen.getByRole("button", { name: "Capture document" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save document approval" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Check capture status" })).toBeEnabled(); expect(screen.getByRole("button", { name: "Delete document" })).toBeEnabled();
    view.rerender(<SavedContextWorkspace projectId={projectId} context={{ ...context, learner: { ...context.learner, allow_external_documentation: false } }} archived={false} catalog={[policy]} initialDocuments={[]} />);
    expect(screen.queryByRole("form")).toBeNull(); expect(screen.getByText(/This context permits tutorial material only/)).toBeInTheDocument();
  });
  it("blocks new captures when the backend reports archival", async () => {
    const fetch = routeFetch(() => json({ code: "project_archived" }, 409)); vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    expect(screen.getByRole("button", { name: "Check capture delivery" })).toBeDisabled(); expect(screen.getByRole("button", { name: "Save document approval" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Check capture status" })).toBeEnabled();
  });
});
describe("saved documentation deletion fences", () => {
  it("does not restore a deleted document from a late capture or list response", async () => {
    const pending = deferred<Response>(); const listing = deferred<Response>();
    const fetch = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (options.method === "DELETE") return Promise.resolve(new Response(null, { status: 204 }));
      if (url.endsWith("/capture")) return pending.promise;
      if (url.endsWith(`/contexts/${contextId}`)) return Promise.resolve(json(context));
      return listing.promise;
    });
    vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Refresh saved approvals" })); fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    expect(screen.getByRole("group", { name: "Confirm document deletion" })).toHaveTextContent("including its revision history");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Confirm document deletion" })); });
    await act(async () => { pending.resolve(json(documentFixture(true))); listing.resolve(json([documentFixture(true)])); });
    expect(screen.queryByRole("article")).toBeNull(); expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull();
    expect(screen.getByRole("button", { name: "Refresh saved approvals" })).toBeEnabled();
  });
  it("keeps a newly captured result when an older approval-list read completes later", async () => {
    const listing = deferred<Response>();
    const fetch = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (url.endsWith("/capture")) return Promise.resolve(json(documentFixture(true)));
      if (url.endsWith(`/contexts/${contextId}`)) return Promise.resolve(json(context));
      expect(options.method).toBe("GET"); return listing.promise;
    }); vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Refresh saved approvals" })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    await act(async () => { listing.resolve(json([documentFixture()])); });
    expect(screen.getByRole("link", { name: "Excerpt 1" })).toBeInTheDocument();
  });
  it("hides retained copies immediately on context deletion and ignores a late capture", async () => {
    const pending = deferred<Response>(), deletion = deferred<Response>();
    const fetch = routeFetch((url, options) => options.method === "DELETE" ? deletion.promise : pending.promise); vi.stubGlobal("fetch", fetch); render(show([documentFixture()]));
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    fireEvent.click(screen.getByRole("button", { name: "Delete saved context" }));
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Confirm context deletion" })); });
    expect(screen.queryByText("lesson.vtt")).toBeNull(); expect(screen.queryByRole("article")).toBeNull();
    await act(async () => { deletion.resolve(new Response(null, { status: 204 })); pending.resolve(json(documentFixture(true))); });
    expect(screen.getByRole("status")).toHaveTextContent("no longer available"); expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull();
  });
  it("clears a context removed with its source before adopting a document refresh", async () => {
    const fetch = vi.fn().mockImplementation((url: string) => Promise.resolve(url.endsWith(`/contexts/${contextId}`) ? json({ code: "curriculum_context_not_found" }, 404) : json([documentFixture(true)])));
    vi.stubGlobal("fetch", fetch); render(show([documentFixture(true)]));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Refresh saved approvals" })); });
    expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull(); expect(screen.getByRole("status")).toHaveTextContent("no longer available");
  });
  it("clears a source-deleted context when checking an uncertain document deletion", async () => {
    const fetch = vi.fn().mockImplementation((_url: string, options: RequestInit) => options.method === "DELETE" ? Promise.reject(new Error("network")) : Promise.resolve(json({ code: "curriculum_context_not_found" }, 404)));
    vi.stubGlobal("fetch", fetch); render(show([documentFixture(true)]));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Confirm document deletion" })); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check document deletion" })); });
    expect(screen.queryByText("lesson.vtt")).toBeNull(); expect(screen.getByRole("status")).toHaveTextContent("no longer available");
  });
  it("keeps uncertain document deletion hidden until explicit read reconciliation", async () => {
    let missing = false; const fetch = vi.fn().mockImplementation((url: string, options: RequestInit) => {
      if (options.method === "DELETE") return Promise.reject(new Error("network"));
      if (url.endsWith(`/contexts/${contextId}`)) return Promise.resolve(json(context));
      return Promise.resolve(missing ? json({ code: "documentation_not_found" }, 404) : json(documentFixture(true)));
    }); vi.stubGlobal("fetch", fetch); render(show([documentFixture(true)]));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Confirm document deletion" })); });
    expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check document deletion" })); });
    expect(screen.getByRole("link", { name: "Excerpt 1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete document" })); await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Confirm document deletion" })); });
    missing = true; await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check document deletion" })); });
    expect(screen.queryByRole("article")).toBeNull(); expect(screen.getByRole("status")).toHaveTextContent("deletion confirmed");
  });
  it("retains hidden state after uncertain context deletion and confirms a missing context", async () => {
    const fetch = routeFetch(() => { throw new Error("network"); });
    vi.stubGlobal("fetch", fetch); render(show([documentFixture(true)])); fireEvent.click(screen.getByRole("button", { name: "Delete saved context" }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Confirm context deletion" })); });
    expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull();
    fetch.mockResolvedValueOnce(json({ code: "curriculum_context_not_found" }, 404));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check context deletion" })); });
    expect(screen.getByRole("status")).toHaveTextContent("no longer available");
  });
  it("does not adopt a foreign receipt or carry a late response into a different context", async () => {
    const pending = deferred<Response>(); const fetch = routeFetch(() => pending.promise); vi.stubGlobal("fetch", fetch);
    const view = render(<StrictMode>{show([documentFixture()])}</StrictMode>);
    act(() => { fireEvent.click(screen.getByRole("button", { name: "Capture document" })); });
    view.rerender(<StrictMode><SavedContextWorkspace projectId={projectId} context={{ ...context, id: "72345678-1234-4234-8234-123456789abc" }} archived={false} catalog={[policy]} initialDocuments={[]} /></StrictMode>);
    await act(async () => { pending.resolve(json(documentFixture(true))); });
    expect(screen.queryByRole("article")).toBeNull(); expect(screen.queryByRole("link", { name: "Excerpt 1" })).toBeNull();
    expect(within(screen.getByRole("form")).getByRole("checkbox")).not.toBeChecked();
  });
});
