"use client";

import { useActionState, useEffect } from "react";
import { retryCleanupAction } from "@/app/actions/sources";
import { SubmitButton } from "@/components/ui/submit-button";
import type { AudioRetention } from "@/lib/api/provenance-contracts";
import { INITIAL_SOURCE_ACTION } from "@/lib/source-action-state";

const MESSAGES: Record<AudioRetention["status"], string> = {
  temporary: "Original audio is temporary and eligible for processing until its expiry. It is not a retained transcript artifact.",
  expired: "Original audio processing eligibility has expired. Physical deletion is not confirmed; the scheduler must retire and clean it up.",
  cleanup_pending: "Original audio is retired and no longer eligible for processing. Physical deletion is pending.",
  cleanup_failed: "Original audio cleanup failed. Physical deletion is not confirmed. Retry when storage is available.",
  deleted: "Original audio deletion confirmed.",
};

export function AudioRetentionStatus({ projectId, retention, onRefresh }: {
  projectId: string; retention: AudioRetention; onRefresh: () => Promise<void>;
}) {
  const [state, action] = useActionState(retryCleanupAction, INITIAL_SOURCE_ACTION);
  useEffect(() => { if (state.status === "success") void onRefresh(); }, [state, onRefresh]);
  return <section className="stack" aria-label="Original audio retention">
    <p role="status">{MESSAGES[retention.status]}</p>
    {retention.status === "temporary" ? <p className="field-hint">Processing eligibility expires: <time dateTime={retention.processing_expires_at}>{retention.processing_expires_at}</time>. Scheduler or storage outages can delay physical deletion.</p> : null}
    {retention.deleted_at ? <p className="field-hint">Deletion confirmed: <time dateTime={retention.deleted_at}>{retention.deleted_at}</time></p> : null}
    <p className="field-hint">A derived transcript, if created, is retained until its source or project is deleted. Once the original is retired, transcribing again requires a new authorized upload.</p>
    {state.status === "error" ? <p role="alert">{state.message}</p> : null}
    {retention.status === "cleanup_failed" && retention.cleanup_id ? <form action={action}>
      <input type="hidden" name="projectId" value={projectId} />
      <input type="hidden" name="cleanupId" value={retention.cleanup_id} />
      <SubmitButton className="button button--secondary" pendingLabel="Retrying audio cleanup…">Retry original audio cleanup</SubmitButton>
    </form> : null}
  </section>;
}
