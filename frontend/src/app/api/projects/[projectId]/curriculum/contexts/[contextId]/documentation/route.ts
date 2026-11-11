import { readContextDocuments, approveDocumentation, curriculumProxyError } from "@/lib/api/curriculum-proxy";

type Context = { params: Promise<{ projectId: string; contextId: string }> };
export async function GET(_request: Request, { params }: Context) {
  try { const { projectId, contextId } = await params; return await readContextDocuments(projectId, contextId); }
  catch (error) { return curriculumProxyError(error, "curriculum_context_not_found"); }
}
export async function POST(request: Request, { params }: Context) {
  try { const { projectId, contextId } = await params; return await approveDocumentation(request, projectId, contextId); }
  catch (error) { return curriculumProxyError(error, "curriculum_context_not_found"); }
}
