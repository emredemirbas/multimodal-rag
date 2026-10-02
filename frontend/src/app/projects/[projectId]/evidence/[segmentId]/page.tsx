import Link from "next/link";
import { notFound } from "next/navigation";
import { requestJson } from "@/lib/api/client";
import { parseEvidence, timestamp } from "@/lib/api/chat-contracts";
import { UUID_PATTERN } from "@/lib/api/source-contracts";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";
import { ApiErrorState } from "@/components/ui/api-state";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function EvidencePage({ params }: { params: Promise<{ projectId: string; segmentId: string }> }) {
  const { projectId, segmentId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(segmentId)) notFound();
  let evidence;
  try { evidence = parseEvidence(await requestJson(`/api/v1/projects/${projectId}/evidence/${segmentId}`)); }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <ApiErrorState message={publicErrorMessage(error)} retryHref={`/projects/${projectId}/evidence/${segmentId}`} />;
  }
  return <article className="panel stack" aria-labelledby="evidence-title">
    <Link href={`/projects/${projectId}`}>Back to project</Link>
    <p className="eyebrow">Tutorial evidence</p>
    <h1 id="evidence-title">{evidence.source_filename}</h1>
    <p>{timestamp(evidence.start_ms)}–{timestamp(evidence.end_ms)} · {evidence.modality} · generation {evidence.generation}</p>
    <blockquote className="evidence-text">{evidence.text}</blockquote>
    <p className="muted">Processing version: {evidence.processing_version}</p>
    <p>This is retained tutorial evidence, not an external documentation citation. No playable video was uploaded; timestamps identify the original tutorial interval.</p>
  </article>;
}
