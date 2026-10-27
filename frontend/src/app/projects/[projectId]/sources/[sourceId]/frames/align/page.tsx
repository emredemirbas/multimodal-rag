import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { AlignmentForm, AlignmentViewer } from "@/components/sources/timeline-alignment";
import { ApiErrorState } from "@/components/ui/api-state";
import { alignmentHref, parseAlignmentQuery, type TimelineAlignment } from "@/lib/api/alignment-contracts";
import { getAlignment } from "@/lib/api/alignment";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { listSources } from "@/lib/api/sources";
import type { SourceItem } from "@/lib/api/source-contracts";
import type { VisualGallery } from "@/lib/api/visual-contracts";
import { getVisualGallery } from "@/lib/api/visuals";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata = { title: "Frame and transcript timeline" };

export default async function AlignmentPage({ params, searchParams }: {
  params: Promise<{ projectId: string; sourceId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ projectId, sourceId }, parameters] = await Promise.all([params, searchParams]);
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(sourceId)) notFound();
  let query;
  try { query = parseAlignmentQuery(parameters); }
  catch { notFound(); }
  let data: { kind: "selection"; gallery: VisualGallery; sources: SourceItem[] } | { kind: "alignment"; view: TimelineAlignment };
  try {
    if (!query) {
      const [gallery, sources] = await Promise.all([getVisualGallery(projectId, sourceId), listSources(projectId)]);
      data = { kind: "selection", gallery, sources };
    } else data = { kind: "alignment", view: await getAlignment(projectId, sourceId, query) };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <ApiErrorState title="Timeline comparison could not load" message={publicErrorMessage(error)}
      retryHref={alignmentHref(projectId, sourceId, query ?? undefined)} />;
  }
  if (data.kind === "selection") {
    if (!data.gallery.origin) return <section className="panel stack" role="status"><h1>No complete gallery yet</h1>
      <p>Finish video processing before comparing published frame and transcript evidence.</p><Link href={`/projects/${projectId}`}>Back to project</Link></section>;
    return <AlignmentForm projectId={projectId} sourceId={sourceId} sources={data.sources} />;
  }
  const view = data.view;
  // Redirect outside the error catch: Next redirects are control-flow exceptions.
  // Subsequent reloads pin both accepted published generations, not mutable latest.
  if (query!.visual_generation === undefined) redirect(alignmentHref(projectId, sourceId, { ...query!,
    visual_generation: view.gallery.generation!, transcript_generation: view.transcript.generation }));
  return <AlignmentViewer projectId={projectId} view={view} />;
}
