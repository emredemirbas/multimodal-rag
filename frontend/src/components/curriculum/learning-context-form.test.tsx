import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LearningContextForm } from "./learning-context-form";
import { context, deferred, json, projectId, source, sourceId } from "./test-fixtures";
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });
function show(sources = [source], archived = false) { return <LearningContextForm tenantId="local" projectId={projectId} sources={sources} archived={archived} />; }
function fill() {
  fireEvent.click(screen.getByLabelText(/lesson.vtt/));
  fireEvent.change(screen.getByLabelText("Programming experience"), { target: { value: "intermediate" } });
  fireEvent.change(screen.getByLabelText("Desired difficulty"), { target: { value: "beginner" } });
  fireEvent.change(screen.getByLabelText("Output language"), { target: { value: "en" } });
  fireEvent.change(screen.getByLabelText("Available effort in minutes"), { target: { value: "60" } });
}
function accepted(options: RequestInit) { const body = JSON.parse(options.body as string); return json({ ...context, learner: body.learner, selected_sources: body.selected_sources.map((pin: object) => ({ ...pin, source_filename: "lesson.vtt" })) }); }
describe("learning context selection", () => {
  it("requires explicit preferences, leaves all permissions unchecked and never starts network work on mount", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); render(show());
    expect(screen.getByLabelText("Programming experience")).toHaveValue("");
    expect(screen.getByLabelText("Desired difficulty")).toHaveValue("");
    expect(screen.getByLabelText("Output language")).toHaveValue("");
    expect(screen.getByLabelText("Available effort in minutes")).toHaveValue(null);
    expect(screen.getByRole("button", { name: "Save context" })).toBeDisabled();
    for (const checkbox of screen.getAllByRole("checkbox")) expect(checkbox).not.toBeChecked();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("submits exact source pins, explicit preferences, and routes to a bookmarkable receipt", async () => {
    const fetch = vi.fn().mockImplementation(async (_url, options) => accepted(options)); vi.stubGlobal("fetch", fetch); render(show()); fill();
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    expect(fetch).toHaveBeenCalledOnce(); const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body.selected_sources).toEqual([{ source_id: sourceId, generation: 1, processing_version: "transcript-v2:g1" }]);
    expect(body.learner).toEqual({ ...context.learner, allow_external_documentation: false });
    expect(push).toHaveBeenCalledWith(`/projects/${projectId}/learning/contexts/${context.id}`);
    expect(screen.getByRole("link", { name: "Open saved context" })).toHaveAttribute("href", `/projects/${projectId}/learning/contexts/${context.id}`);
  });
  it.each(["new generation", "removed source"])("keeps an uncertain command frozen through %s refresh", async (change) => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error("network")).mockImplementation(async (_url, options) => accepted(options));
    vi.stubGlobal("fetch", fetch); const view = render(show()); fill();
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    expect(screen.getByRole("button", { name: "Check context delivery" })).toBeEnabled();
    view.rerender(show(change === "new generation" ? [{ ...source, generation: 2, active_generation: 2, processing_version: "transcript-v2:g2" }] : []));
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual(JSON.parse(fetch.mock.calls[0][1].body));
    expect(push).toHaveBeenCalledOnce();
  });
  it("starts a new key after an explicit preference edit and prevents duplicate pending delivery", async () => {
    const pending = deferred<Response>();
    const fetch = vi.fn().mockRejectedValueOnce(new Error("network")).mockReturnValueOnce(pending.promise); vi.stubGlobal("fetch", fetch); render(show()); fill();
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    fireEvent.change(screen.getByLabelText("Available effort in minutes"), { target: { value: "90" } });
    act(() => { fireEvent.submit(screen.getByRole("form")); fireEvent.submit(screen.getByRole("form")); });
    expect(fetch).toHaveBeenCalledTimes(2); expect(screen.getByRole("form")).toHaveAttribute("aria-busy", "true");
    const first = JSON.parse(fetch.mock.calls[0][1].body), second = JSON.parse(fetch.mock.calls[1][1].body);
    expect(first.idempotency_key).not.toBe(second.idempotency_key); expect(second.learner.available_minutes).toBe(90);
    await act(async () => { pending.resolve(accepted(fetch.mock.calls[1][1])); });
    await waitFor(() => expect(push).toHaveBeenCalledOnce());
  });
  it("rejects unmatched receipts while retaining the same command for delivery checks", async () => {
    const fetch = vi.fn().mockResolvedValue(json(context)); vi.stubGlobal("fetch", fetch); render(show()); fill();
    await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    expect(push).not.toHaveBeenCalled(); expect(screen.getByRole("alert")).toHaveTextContent("could not be confirmed");
    expect(screen.getByLabelText("Available effort in minutes")).toHaveValue(60);
  });
  it("works under StrictMode and blocks archived writes", async () => {
    const fetch = vi.fn().mockImplementation(async (_url, options) => accepted(options)); vi.stubGlobal("fetch", fetch);
    const view = render(<StrictMode>{show()}</StrictMode>); fill(); await act(async () => { fireEvent.submit(screen.getByRole("form")); });
    expect(push).toHaveBeenCalledOnce(); view.rerender(<StrictMode>{show([source], true)}</StrictMode>);
    expect(screen.getByRole("button", { name: "Save context" })).toBeDisabled();
  });
  it("does not allow a 21st selected source or unpublished metadata", () => {
    const sources = Array.from({ length: 21 }, (_, index) => ({ ...source, id: `22345678-1234-4234-8234-${index.toString(16).padStart(12, "0")}`, filename: `lesson-${index}.vtt` }));
    render(show([...sources, { ...source, id: "72345678-1234-4234-8234-123456789abc", filename: "unpublished.vtt", processing_version: undefined }]));
    for (const checkbox of screen.getAllByRole("checkbox").slice(0, 20)) fireEvent.click(checkbox);
    expect(screen.getByLabelText(/lesson-20.vtt/)).toBeDisabled(); expect(screen.queryByLabelText(/unpublished.vtt/)).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("maximum of 20");
  });
});
