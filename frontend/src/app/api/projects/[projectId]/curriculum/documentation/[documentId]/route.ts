import { readDocumentation, deleteDocumentation, curriculumProxyError } from "@/lib/api/curriculum-proxy";

type Context = { params: Promise<{ projectId: string; documentId: string }> };
export async function GET(_request: Request, { params }: Context) {
  try { const { projectId, documentId } = await params; return await readDocumentation(projectId, documentId); }
  catch (error) { return curriculumProxyError(error, "documentation_not_found"); }
}
export async function DELETE(request: Request, { params }: Context) {
  try { const { projectId, documentId } = await params; return await deleteDocumentation(request, projectId, documentId); }
  catch (error) { return curriculumProxyError(error, "documentation_not_found"); }
}
