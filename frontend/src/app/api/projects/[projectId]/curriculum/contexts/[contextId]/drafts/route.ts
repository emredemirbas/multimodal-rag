import { readDraftList } from "@/lib/api/drafts";
import { curriculumProxyError } from "@/lib/api/curriculum-proxy";
export async function GET(request: Request, { params }: { params: Promise<{ projectId: string; contextId: string }> }) {
  try { const { projectId, contextId } = await params; return await readDraftList(projectId, contextId, request); }
  catch (error) { return curriculumProxyError(error, "curriculum_context_not_found"); }
}
