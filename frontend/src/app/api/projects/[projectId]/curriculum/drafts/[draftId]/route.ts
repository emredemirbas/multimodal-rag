import { readDraft, replaceDraft, deleteDraft } from "@/lib/api/drafts";
import { curriculumProxyError } from "@/lib/api/curriculum-proxy";
type Context = { params: Promise<{ projectId: string; draftId: string }> };
export async function GET(_request: Request, { params }: Context) {
  try { const { projectId, draftId } = await params; return await readDraft(projectId, draftId); }
  catch (error) { return curriculumProxyError(error, "curriculum_draft_not_found"); }
}
export async function PUT(request: Request, { params }: Context) {
  try { const { projectId, draftId } = await params; return await replaceDraft(request, projectId, draftId); }
  catch (error) { return curriculumProxyError(error, "curriculum_draft_not_found"); }
}
export async function DELETE(request: Request, { params }: Context) {
  try { const { projectId, draftId } = await params; return await deleteDraft(request, projectId, draftId); }
  catch (error) { return curriculumProxyError(error, "curriculum_draft_not_found"); }
}
