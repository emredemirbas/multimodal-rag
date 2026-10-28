"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { parseConversation, parseHistory, timestamp, type AnswerMode, type RetrievalMode, type ChatTurn, type Conversation, type History } from "@/lib/api/chat-contracts";
import { ApiError, apiErrorFromResponse } from "@/lib/api/errors";
import type { SourceItem } from "@/lib/api/source-contracts";
import { consumeChatStream } from "@/lib/chat-stream";
import { retainedFrameHref } from "@/lib/api/visual-contracts";

interface Props {
  projectId: string; sources: SourceItem[]; initialConversations: Conversation[];
  initialHistory: History | null; archived: boolean; initialError?: string;
  answerMode?: AnswerMode;
  retrievalMode?: RetrievalMode;
}

export function ChatWorkspace({ projectId, sources, initialConversations, initialHistory, archived, initialError = "", answerMode = "extractive", retrievalMode = 'deterministic-hash-and-lexical' }: Props) {
  const [conversations, setConversations] = useState(initialConversations);
  const [conversation, setConversation] = useState<Conversation | null>(initialHistory?.conversation ?? null);
  const [turns, setTurns] = useState<ChatTurn[]>(initialHistory?.turns ?? []);
  const [question, setQuestion] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [pending, setPending] = useState(false);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState(initialError);
  const [status, setStatus] = useState("");
  const requestKey = useRef("");
  const conversationKey = useRef("");
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const questionInput = useRef<HTMLTextAreaElement>(null);
  const wasPending = useRef(false);
  const path = `/api/projects/${projectId}/conversations`;
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (!pending && wasPending.current) questionInput.current?.focus();
    wasPending.current = pending;
  }, [pending]);

  async function history(id: string) {
    if (busy.current) return;
    busy.current = true;
    setPending(true); setError(""); setStatus("Loading saved conversation…");
    const active = new AbortController(); controller.current = active;
    try {
      const response = await fetch(`${path}/${id}`, { cache: "no-store", signal: AbortSignal.any([active.signal, AbortSignal.timeout(10_000)]) });
      if (!response.ok) throw new Error("History unavailable");
      const saved = parseHistory(await response.json());
      if (saved.conversation.project_id !== projectId || saved.conversation.id !== id) throw new Error("Invalid conversation scope");
      // A failed switch must not discard an uncertain message's replay key.
      if (saved.conversation.id !== conversation?.id) requestKey.current = "";
      setConversation(saved.conversation); setTurns(saved.turns); setPartial("");
      setStatus("Saved conversation loaded.");
    } catch { setError("History could not be loaded. Try again or reload the workspace."); }
    finally { busy.current = false; setPending(false); controller.current = null; }
  }

  function newConversation() {
    if (busy.current) return;
    setConversation(null); setTurns([]); setPartial(""); setError(""); setStatus("New conversation. Each question should be self-contained.");
    requestKey.current = ""; conversationKey.current = "";
    questionInput.current?.focus();
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy.current || archived || question.trim().length < 2) return;
    busy.current = true;
    const active = new AbortController(); controller.current = active;
    const signal = AbortSignal.any([active.signal, AbortSignal.timeout(30_000)]);
    setPending(true); setPartial(""); setError(""); setStatus("Finding evidence and delivering the saved answer…");
    requestKey.current ||= crypto.randomUUID();
    try {
      let current = conversation;
      if (!current) {
        conversationKey.current ||= crypto.randomUUID();
        const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "Tutorial questions", idempotency_key: conversationKey.current }), signal });
        if (!response.ok) throw new Error("Conversation unavailable");
        current = parseConversation(await response.json());
        if (current.project_id !== projectId) throw new Error("Invalid conversation scope");
        setConversation(current);
        setConversations((previous) => [current!, ...previous.filter((item) => item.id !== current!.id)]);
      }
      const response = await fetch(`${path}/${current.id}/messages`, {
        method: "POST", headers: { "Content-Type": "application/json", "Accept": "text/event-stream" }, signal,
        body: JSON.stringify({ question: question.trim(), source_ids: sourceId ? [sourceId] : [], idempotency_key: requestKey.current }),
      });
      if (!response.ok) throw await apiErrorFromResponse(response);
      if (!response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) throw new Error("Answer unavailable");
      const turn = await consumeChatStream(response.body, (chunk) => setPartial((previous) => previous + chunk));
      setTurns((previous) => [...previous.filter((item) => item.id !== turn.id), turn].sort((left, right) => left.sequence - right.sequence));
      setQuestion(""); setPartial(""); requestKey.current = "";
      setStatus(turn.response.abstained ? "No supporting evidence was found. The limitation was saved." : "Answer saved with inspectable source citations.");
    } catch (failure) {
      setPartial("");
      const modelErrors: Record<string, string> = {
        local_embeddings_unavailable: "Local semantic search is unavailable or timed out. Start local-ai, free resources and retry this unchanged question.",
        local_embeddings_not_installed: "Explicitly download qwen3-embedding:0.6b in local-ai, then retry this unchanged question.",
        local_embeddings_busy: "Local semantic search is busy. Retry this unchanged question shortly.",
        embedding_model_changed: "The embedding model changed. Restore the approved model before searching this index.",
        invalid_embeddings: "The embedding response could not be validated. No unvalidated evidence is displayed; retry shortly.",
        embedding_input_limit: "The local model rejected this input. Shorten the question, then send it again.",
        local_model_unavailable: "The local model is unavailable or timed out. Start the local-ai service, free resources and retry this unchanged question.",
        local_model_not_installed: "The local model is not installed. Explicitly download qwen3:4b in the local-ai service, then retry this unchanged question.",
        local_model_busy: "The local model is answering another question. Retry this unchanged question shortly.",
        invalid_model_answer: "The local model answer could not be validated. Retry this unchanged question; no unvalidated answer is displayed.",
      };
      setError(failure instanceof ApiError && modelErrors[failure.code] ? modelErrors[failure.code] : active.signal.aborted ? "Delivery stopped. The answer may already be saved. Reload history or resend this unchanged question to replay it." :
        "Delivery could not finish. The answer may already be saved. Reload history or resend this unchanged question; it will not create a duplicate turn.");
      setStatus("");
    } finally {
      busy.current = false; setPending(false); controller.current = null;
      questionInput.current?.focus();
    }
  }

  return <div className="stack">
    <p className="muted">{answerMode === "ollama" ? "Local Ollama answer mode: Qwen3 4B runs on your computer, with no paid/cloud provider." :
      answerMode === "extractive" ? "Offline extractive baseline: answers quote indexed evidence, not a connected language model." :
      "Answer configuration could not be verified. Reload the workspace before relying on the configured model."} Each question is self-contained; saved history is not model context.</p>
    <p className="muted">{retrievalMode === 'local-semantic-and-lexical' ? 'Local semantic search: Qwen3 Embedding 0.6B + exact project-filtered vectors and full-text search. The experimental relevance guard can miss valid questions; inspect citations.' :
      retrievalMode === 'deterministic-hash-and-lexical' ? 'Retrieval still uses the deterministic hash/lexical baseline, not a learned semantic model.' : 'Retrieval configuration could not be verified. Reload the workspace.'}</p>
    {sources.some((source) => source.reindex_required) ? <p role="status">Some sources require reindexing for the current search mode and are excluded. Use transcript reindex/reprocess controls below (or reupload validation-only transcripts). Retained-video OCR currently requires an operator-created index job. Then reload this workspace; saved citations remain inspectable.</p> : null}
    <div className="chat-controls">
      <label htmlFor="conversation-choice">Saved conversation</label>
      <select id="conversation-choice" value={conversation?.id ?? ""} disabled={pending} onChange={(event) => {
        if (event.target.value) void history(event.target.value); else newConversation();
      }}>
        <option value="">New conversation</option>
        {conversations.map((item, index) => <option key={item.id} value={item.id}>{item.title} · {index + 1}</option>)}
      </select>
      <button type="button" className="button button--secondary" onClick={newConversation} disabled={pending}>New conversation</button>
      <button type="button" className="button button--secondary" onClick={() => conversation && void history(conversation.id)} disabled={pending || !conversation}>Reload history</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <p role="status" aria-live="polite">{status}</p>
    {turns.length === 0 ? <p>No saved messages yet. Ask about indexed evidence to see timestamped citations.</p> :
      <ol className="chat-turns" aria-label="Conversation history">{turns.map((turn) => <li key={turn.id} className="chat-turn">
        <h3>You</h3><p className="evidence-text">{turn.question}</p>
        <h3>{turn.response.abstained ? "Evidence limitation" : "Tutorial evidence"}</h3>
        <p className="evidence-text">{turn.response.answer}</p>
        <p className="muted">{turn.response.provider} · {turn.response.model}</p>
        {turn.response.citations.length ? <ol aria-label={`Citations for question ${turn.sequence}`}>
          {turn.response.citations.map((citation) => <li key={citation.segment_id}>
            <Link className="citation-link" prefetch={false} href={`/projects/${projectId}/evidence/${citation.segment_id}`}>
              {citation.source_filename} · {timestamp(citation.start_ms)}{citation.start_ms !== citation.end_ms ? `–${timestamp(citation.end_ms)}` : " (frame)"} · generation {citation.generation}
            </Link>
            {citation.asr_origin ? <p className="field-hint">Automatically transcribed · not human-reviewed. Speech, code identifiers and timestamps may be wrong; inspect this evidence.</p> : null}
            {citation.visual_origin && citation.frame_id ? <p className="field-hint">{citation.visual_origin.description ? "Automatic visual evidence · OCR / image-model descriptions, not verified facts." : "Automatic frame OCR · not human-reviewed."} <Link prefetch={false} href={retainedFrameHref(projectId, citation.source_id, citation.frame_id)}>Inspect supporting frame</Link></p> : null}
          </li>)}
        </ol> : null}
      </li>)}</ol>}
    {pending && partial ? <div aria-label="Answer delivery in progress"><p className="evidence-text">{partial}</p><p>Delivery in progress; citations appear after validation completes.</p></div> : null}
    {archived ? <p>Restore this project to ask new questions. Saved evidence remains available.</p> : <form onSubmit={(event) => void send(event)} className="stack">
      <div className="form-field"><label htmlFor="chat-source">Source filter</label>
        <select id="chat-source" disabled={pending} value={sourceId} onChange={(event) => { setSourceId(event.target.value); requestKey.current = ""; }}>
          <option value="">All indexed sources in this project</option>
          {sources.filter((source) => source.active_generation !== null && !source.reindex_required).map((source) => <option value={source.id} key={source.id}>{source.filename}</option>)}
        </select>
      </div>
      <div className="form-field"><label htmlFor="chat-question">Question about the tutorial</label>
        <textarea ref={questionInput} id="chat-question" required minLength={2} maxLength={2000} rows={3} value={question} disabled={pending}
          aria-describedby="chat-question-help" onChange={(event) => { setQuestion(event.target.value); requestKey.current = ""; }} />
        <p id="chat-question-help" className="muted">Up to 2,000 characters. Unsupported questions receive a limitation, not invented tutorial content.</p>
      </div>
      <div className="chat-controls"><button type="submit" className="button" disabled={pending || question.trim().length < 2}>Ask with evidence</button>
        {pending ? <button type="button" className="button button--secondary" onClick={() => controller.current?.abort()}>Stop delivery</button> : null}
      </div>
    </form>}
  </div>;
}
