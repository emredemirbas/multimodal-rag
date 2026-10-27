import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatWorkspace } from "@/components/chat/chat-workspace";
import type { ChatTurn, Conversation } from "@/lib/api/chat-contracts";
import { asrOrigin } from "../../../test-support/media-fixture";
import { visualFixture } from "../../../test-support/visual-fixture";

const project = "12345678-1234-1234-1234-123456789abc";
const conversation: Conversation = { id: "12345678-1234-1234-1234-123456789abd", project_id: project, title: "Tutorial questions", created_at: "2026-10-02T00:00:00Z" };
const turn: ChatTurn = { id: "12345678-1234-1234-1234-123456789abe", sequence: 1, question: "What is health?", source_ids: [], created_at: conversation.created_at,
  response: { answer: "Quoted health evidence <script>alert(1)</script>", abstained: false, provider: "local-deterministic", model: "extractive",
    citations: [{ segment_id: "12345678-1234-1234-1234-123456789abf", source_id: "12345678-1234-1234-1234-123456789ac0", source_filename: "tutorial.vtt", start_ms: 1000, end_ms: 5000, generation: 1, processing_version: "parser-v1", modality: "transcript" }] } };
function response() {
  return new Response(new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode(`event: start\ndata: {}\n\nevent: delta\ndata: {"text":"Quoted evidence"}\n\nevent: complete\ndata: ${JSON.stringify(turn)}\n\n`)); controller.close();
  } }), { headers: { "Content-Type": "text/event-stream" } });
}
afterEach(() => vi.unstubAllGlobals());
describe("project chat", () => {
  it("retains stable visual evidence and supporting-frame links in saved history", () => {
    const gallery = visualFixture(), citation = turn.response.citations[0];
    const visual = { ...turn, response: { ...turn.response, citations: [{ ...citation, modality: "frame", start_ms: 0, end_ms: 0,
      generation: 3, processing_version: "visual-ocr-chunks-v1:g3", visual_origin: gallery.origin, frame_id: gallery.items[0].id }] } };
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [visual] }} archived />);
    expect(screen.getByText(/Automatic frame OCR · not human-reviewed/)).toBeVisible();
    expect(screen.getByRole("link", { name: /00:00 \(frame\)/ })).toHaveAttribute("href", `/projects/${project}/evidence/${citation.segment_id}`);
    expect(screen.getByRole("link", { name: "Inspect supporting frame" })).toHaveAttribute("href", `/projects/${project}/sources/${citation.source_id}/frames#frame-${gallery.items[0].id}`);
  });
  it("labels automatic evidence in saved history without changing its stable citation link", () => {
    const generated = { ...turn, response: { ...turn.response, citations: [{ ...turn.response.citations[0], asr_origin: asrOrigin }] } };
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [generated] }} archived />);
    expect(screen.getByText(/Automatically transcribed · not human-reviewed/)).toBeVisible();
    expect(screen.getByRole("link", { name: /tutorial.vtt/ })).toHaveAttribute("href", `/projects/${project}/evidence/${turn.response.citations[0].segment_id}`);
  });
  it("labels local generation and keeps the retrieval limitation visible", () => {
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[]} initialHistory={null} archived={false} answerMode="ollama" />);
    expect(screen.getByText(/Local Ollama answer mode/)).toHaveTextContent("no paid/cloud provider");
    expect(screen.getByText(/Retrieval still uses/)).toHaveTextContent("deterministic hash/lexical baseline");
    expect(screen.queryByText(/Offline extractive baseline/)).not.toBeInTheDocument();
  });
  it('labels semantic retrieval and excludes incompatible indexes without hiding saved citations', () => {
    const old = { id: project, filename: 'old.vtt', status: 'ready', generation: 1, active_generation: 1, segment_count: 1, provider: 'upload', failure_code: null, job: null, reindex_required: true };
    render(<ChatWorkspace projectId={project} sources={[old]} initialConversations={[conversation]} initialHistory={{conversation,turns:[turn]}} archived={false} answerMode='ollama' retrievalMode='local-semantic-and-lexical' />);
    expect(screen.getByText(/Local semantic search:/)).toHaveTextContent('Qwen3 Embedding 0.6B');
    expect(screen.getByText(/Some sources require reindexing/)).toBeVisible();
    expect(screen.queryByRole('option', {name:'old.vtt'})).not.toBeInTheDocument();
    expect(screen.getByRole('link', {name:/tutorial.vtt/})).toBeVisible();
    expect(screen.queryByText(/Retrieval still uses/)).not.toBeInTheDocument();
  });
  it("offers actionable local-model recovery while retaining the same retry key", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({code:"local_model_not_installed"}),{status:503,headers:{"Content-Type":"application/json"}})).mockResolvedValueOnce(response());
    vi.stubGlobal("fetch", fetcher);
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{conversation,turns:[]}} archived={false} answerMode="ollama" />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "What is health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Explicitly download qwen3:4b");
    const key = JSON.parse(fetcher.mock.calls[0][1].body).idempotency_key;
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    await screen.findByText(turn.response.answer);
    expect(JSON.parse(fetcher.mock.calls[1][1].body).idempotency_key).toBe(key);
  });
  it("has labelled empty states and honestly identifies the offline provider", () => {
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[]} initialHistory={null} archived={false} />);
    expect(screen.getByLabelText("Question about the tutorial")).toHaveAttribute("maxlength", "2000");
    expect(screen.getByLabelText("Source filter")).toBeVisible();
    expect(screen.getByText(/Offline extractive baseline/)).toBeVisible();
    expect(screen.getByText(/No saved messages yet/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Ask with evidence" })).toBeDisabled();
  });
  it("streams a validated answer, escapes evidence and links to the exact source version", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));
    const { container } = render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]}
      initialHistory={{ conversation, turns: [] }} archived={false} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "What is health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    expect(await screen.findByText(turn.response.answer)).toBeVisible();
    expect(screen.getByRole("link", { name: /tutorial.vtt.*00:01–00:05.*generation 1/ })).toHaveAttribute("href", `/projects/${project}/evidence/${turn.response.citations[0].segment_id}`);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue("");
    await waitFor(() => expect(screen.getByLabelText("Question about the tutorial")).toHaveFocus());
  });
  it("retries an unchanged failed delivery with the same key, without claiming it was not saved", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce(response());
    vi.stubGlobal("fetch", fetcher);
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [] }} archived={false} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "What is health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("may already be saved");
    const firstKey = JSON.parse(fetcher.mock.calls[0][1].body).idempotency_key;
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    await screen.findByText(turn.response.answer);
    expect(JSON.parse(fetcher.mock.calls[1][1].body).idempotency_key).toBe(firstKey);
  });
  it("stops delivery, preserves the draft and offers history recovery", async () => {
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new Error("aborted"))))));
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [] }} archived={false} />);
    fireEvent.change(screen.getByLabelText("Question about the tutorial"), { target: { value: "health?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    fireEvent.click(await screen.findByRole("button", { name: "Stop delivery" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Delivery stopped"));
    expect(screen.getByLabelText("Question about the tutorial")).toHaveValue("health?");
    expect(screen.getByRole("button", { name: "Reload history" })).toBeEnabled();
  });
  it("shows persisted limitations and prevents new questions in archived projects", () => {
    const abstained = { ...turn, response: { ...turn.response, answer: "No supporting evidence", abstained: true, citations: [] } };
    render(<ChatWorkspace projectId={project} sources={[]} initialConversations={[conversation]} initialHistory={{ conversation, turns: [abstained] }} archived />);
    expect(screen.getByRole("heading", { name: "Evidence limitation" })).toBeVisible();
    expect(screen.queryByLabelText("Question about the tutorial")).not.toBeInTheDocument();
  });
});
