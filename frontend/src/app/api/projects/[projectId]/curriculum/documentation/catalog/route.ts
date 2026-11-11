import { readDocumentationCatalog, curriculumProxyError } from "@/lib/api/curriculum-proxy";

type Context = { params: Promise<{ projectId: string }> };
export async function GET(_request: Request, { params }: Context) {
  try { const { projectId } = await params; return await readDocumentationCatalog(projectId); }
  catch (error) { return curriculumProxyError(error); }
}
