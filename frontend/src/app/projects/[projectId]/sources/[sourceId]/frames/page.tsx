import { notFound } from "next/navigation";
import { VisualGallery } from "@/components/sources/visual-gallery";
import { ApiErrorState } from "@/components/ui/api-state";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { galleryHref } from "@/lib/api/visual-contracts";
import { getVisualGallery } from "@/lib/api/visuals";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata = { title: "Selected tutorial frames" };
export default async function FramesPage({ params }: { params: Promise<{ projectId: string; sourceId: string }> }) {
  const { projectId, sourceId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(sourceId)) notFound();
  let gallery;
  try { gallery = await getVisualGallery(projectId, sourceId); }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    return <ApiErrorState title="Selected frames could not load" message={publicErrorMessage(error)} retryHref={galleryHref(projectId, sourceId)} />;
  }
  return <VisualGallery projectId={projectId} gallery={gallery} />;
}
