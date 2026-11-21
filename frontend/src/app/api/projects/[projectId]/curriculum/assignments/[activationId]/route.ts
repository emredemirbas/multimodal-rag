import { readAssignmentActivation } from "@/lib/api/activations";
import { curriculumProxyError } from "@/lib/api/curriculum-proxy";
export async function GET(_request: Request, { params }: { params: Promise<{ projectId: string; activationId: string }> }) {
  try { const { projectId, activationId } = await params; return await readAssignmentActivation(projectId, activationId); }
  catch (error) { return curriculumProxyError(error, "assignment_activation_not_found"); }
}
