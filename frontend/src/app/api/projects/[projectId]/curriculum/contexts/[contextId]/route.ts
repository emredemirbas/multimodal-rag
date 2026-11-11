import { readLearningContext, deleteLearningContext, curriculumProxyError } from "@/lib/api/curriculum-proxy";

type Context = { params: Promise<{ projectId: string; contextId: string }> };
export async function GET(_request: Request, { params }: Context) {
  try { const { projectId, contextId } = await params; return await readLearningContext(projectId, contextId); }
  catch (error) { return curriculumProxyError(error, "curriculum_context_not_found"); }
}
export async function DELETE(request: Request, { params }: Context) {
  try { const { projectId, contextId } = await params; return await deleteLearningContext(request, projectId, contextId); }
  catch (error) { return curriculumProxyError(error, "curriculum_context_not_found"); }
}
