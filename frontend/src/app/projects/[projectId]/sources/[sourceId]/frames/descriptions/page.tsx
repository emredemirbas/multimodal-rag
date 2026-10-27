import { notFound } from "next/navigation";
import { FrameDescriptions } from "@/components/sources/frame-descriptions";
import { ApiErrorState } from "@/components/ui/api-state";
import { getDescriptions } from "@/lib/api/descriptions";
import { descriptionHref, type DescriptionView } from "@/lib/api/description-contracts";
import type { VisualGallery } from "@/lib/api/visual-contracts";
import { getVisualGallery } from "@/lib/api/visuals";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError,publicErrorMessage } from "@/lib/api/errors";
export const dynamic="force-dynamic";
export const revalidate=0;
export const metadata={title:"Local frame descriptions"};
export default async function DescriptionsPage({params}:{params:Promise<{projectId:string;sourceId:string}>}) {
  const {projectId,sourceId}=await params;
  if(!UUID_PATTERN.test(projectId)||!UUID_PATTERN.test(sourceId)) notFound();
  let gallery:VisualGallery,view:DescriptionView;
  try {
    [gallery,view]=await Promise.all([getVisualGallery(projectId,sourceId),getDescriptions(projectId,sourceId)]);
    if(view.origin && (view.gallery_generation!==gallery.generation || view.items.length!==gallery.items.length
      || view.items.some((item,index)=>item.frame_id.toLowerCase()!==gallery.items[index].id.toLowerCase()))) throw new ApiError({status:409});
  } catch(error) {
    if(error instanceof ApiError && error.status===404) notFound();
    return <ApiErrorState title="Frame descriptions could not load" message={publicErrorMessage(error)} retryHref={descriptionHref(projectId,sourceId)}/>;
  }
  return <FrameDescriptions projectId={projectId} gallery={gallery} view={view} requestKey={crypto.randomUUID()}/>;
}
