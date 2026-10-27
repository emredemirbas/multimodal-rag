"use client";
import { useActionState, useEffect } from 'react';
import { retryCleanupAction } from '@/app/actions/sources';
import { SubmitButton } from '@/components/ui/submit-button';
import type { VideoRetention } from '@/lib/api/provenance-contracts';
import { INITIAL_SOURCE_ACTION } from '@/lib/source-action-state';

const MESSAGES: Record<VideoRetention['status'], string> = {
  temporary: 'Original video is temporary and eligible for extraction until its expiry. It is not a retained frame artifact.',
  expired: 'Original video processing eligibility has expired. Physical deletion is not confirmed; the scheduler must retire and clean it up.',
  cleanup_pending: 'Original video is retired and no longer eligible for extraction. Physical deletion is pending.',
  cleanup_failed: 'Original video cleanup failed. Physical deletion is not confirmed. Retry when storage is available.',
  deleted: 'Original video deletion confirmed.',
};
export function VideoRetentionStatus({ projectId, retention, onRefresh }: { projectId: string; retention: VideoRetention; onRefresh: () => Promise<void> }) {
  const [state, action] = useActionState(retryCleanupAction, INITIAL_SOURCE_ACTION);
  useEffect(() => { if (state.status === 'success') void onRefresh(); }, [state, onRefresh]);
  return <section className="stack" aria-label="Original video retention">
    <p role="status">{MESSAGES[retention.status]}</p>
    {retention.status === 'temporary' ? <p className="field-hint">Processing eligibility expires: <time dateTime={retention.processing_expires_at}>{retention.processing_expires_at}</time>. Scheduler or storage outages can delay physical deletion.</p> : null}
    {retention.deleted_at ? <p className="field-hint">Deletion confirmed: <time dateTime={retention.deleted_at}>{retention.deleted_at}</time></p> : null}
    <p className="field-hint">Permitted selected frames and literal OCR, if created, remain until the source or project is deleted. Extracting a retired original again requires a new authorized MP4. Retrying derived work does not rerun native extraction.</p>
    {state.status === 'error' ? <p role="alert">{state.message}</p> : null}
    {retention.status === 'cleanup_failed' && retention.cleanup_id ? <form action={action}>
      <input type="hidden" name="projectId" value={projectId} /><input type="hidden" name="cleanupId" value={retention.cleanup_id} />
      <SubmitButton className="button button--secondary" pendingLabel="Retrying video cleanup…">Retry original video cleanup</SubmitButton>
    </form> : null}
  </section>;
}
