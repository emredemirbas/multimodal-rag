import { notFound } from "next/navigation";
import { TranscriptViewer } from "@/components/sources/transcript-viewer";
import { ApiErrorState } from "@/components/ui/api-state";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/source-contracts";
import { parseTranscriptQuery, transcriptHref } from "@/lib/api/transcript-contracts";
import { getTranscript } from "@/lib/api/transcripts";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata = { title: "Tutorial transcript" };

export default async function TranscriptPage({ params, searchParams }: {
  params: Promise<{ projectId: string; sourceId: string }>;
  searchParams: Promise<{ generation?: string | string[]; page?: string | string[] }>;
}) {
  const [{ projectId, sourceId }, parameters] = await Promise.all([params, searchParams]);
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(sourceId)) notFound();
  let query;
  try { query = parseTranscriptQuery(parameters); }
  catch { notFound(); }
  let transcript;
  try { transcript = await getTranscript(projectId, sourceId, query); }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <ApiErrorState title="Transcript could not load" message={publicErrorMessage(error)}
      retryHref={transcriptHref(projectId, sourceId, query.generation, query.page)} reference={errorReference(error)} />;
  }
  return <TranscriptViewer projectId={projectId} transcript={transcript} />;
}
