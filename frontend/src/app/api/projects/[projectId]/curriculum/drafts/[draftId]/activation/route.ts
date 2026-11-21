import { readDraftActivation } from "@/lib/api/activations";
import { curriculumProxyError } from "@/lib/api/curriculum-proxy";
export async function GET(_request: Request, { params }: { params: Promise<{ projectId: string; draftId: string }> }) {
  try { const { projectId, draftId } = await params; return await readDraftActivation(projectId, draftId); }
  catch (error) { return curriculumProxyError(error, "curriculum_draft_not_found"); }
}
