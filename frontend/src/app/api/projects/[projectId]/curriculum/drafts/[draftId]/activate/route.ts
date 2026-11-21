import { activateAssignment } from "@/lib/api/activations";
import { curriculumProxyError } from "@/lib/api/curriculum-proxy";
export async function POST(request: Request, { params }: { params: Promise<{ projectId: string; draftId: string }> }) {
  try { const { projectId, draftId } = await params; return await activateAssignment(request, projectId, draftId); }
  catch (error) { return curriculumProxyError(error, "curriculum_draft_not_found"); }
}
