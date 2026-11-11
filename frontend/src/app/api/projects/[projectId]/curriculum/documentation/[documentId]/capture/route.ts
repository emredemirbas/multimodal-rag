import { captureDocumentation, curriculumProxyError } from "@/lib/api/curriculum-proxy";

type Context = { params: Promise<{ projectId: string; documentId: string }> };
export async function POST(request: Request, { params }: Context) {
  try { const { projectId, documentId } = await params; return await captureDocumentation(request, projectId, documentId); }
  catch (error) { return curriculumProxyError(error, "documentation_not_found"); }
}
