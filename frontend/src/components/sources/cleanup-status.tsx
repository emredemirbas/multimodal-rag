"use client";

import { useActionState, useCallback, useEffect, useState } from "react";

import { retryCleanupAction } from "@/app/actions/sources";
import { SubmitButton } from "@/components/ui/submit-button";
import { parseCleanup, type CleanupTicket } from "@/lib/api/source-contracts";
import { INITIAL_SOURCE_ACTION } from "@/lib/source-action-state";

export function CleanupStatus({ initialTicket }: { initialTicket: CleanupTicket }) {
  const [ticket, setTicket] = useState(initialTicket);
  const [error, setError] = useState("");
  const [state, action] = useActionState(retryCleanupAction, INITIAL_SOURCE_ACTION);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(`/api/projects/${initialTicket.project_id}/cleanup/${initialTicket.id}`, { cache: "no-store", signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(10_000)]) : AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error();
      const updated = parseCleanup(await response.json());
      if (!signal?.aborted) { setTicket(updated); setError(""); }
    } catch { if (!signal?.aborted) setError("File cleanup status is unavailable. Refresh to reconnect."); }
  }, [initialTicket.project_id, initialTicket.id]);
  const working = ticket.status === "pending" || ticket.status === "running";
  useEffect(() => {
    if (!working) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setInterval> | undefined;
    function visibility() {
      clearInterval(timer);
      if (!document.hidden) timer = setInterval(() => { void refresh(controller.signal); }, 5_000);
    }
    visibility();
    document.addEventListener("visibilitychange", visibility);
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [working, refresh]);
  useEffect(() => {
    if (state.status === "success") {
      const timer = setTimeout(() => { void refresh(); }, 0);
      return () => clearTimeout(timer);
    }
  }, [state, refresh]);
  return <div className="stack">
    <p role="status">{ticket.status === "completed" ? "Retained file cleanup completed." : ticket.status === "failed" ? "Retained file cleanup needs attention. Retry when storage is available." : "Records removed; retained file cleanup is in progress."}</p>
    {error || state.status === "error" ? <p role="alert">{error || state.message}</p> : null}
    <button type="button" className="button button--secondary" onClick={() => { void refresh(); }}>Refresh cleanup status</button>
    {ticket.status === "failed" ? <form action={action}>
      <input type="hidden" name="projectId" value={ticket.project_id} />
      <input type="hidden" name="cleanupId" value={ticket.id} />
      <SubmitButton className="button button--secondary" pendingLabel="Retrying…">Retry file cleanup</SubmitButton>
    </form> : null}
  </div>;
}
