import { createLearningContext, curriculumProxyError } from "@/lib/api/curriculum-proxy";

type Context = { params: Promise<{ projectId: string }> };
export async function POST(request: Request, { params }: Context) {
  try { const { projectId } = await params; return await createLearningContext(request, projectId); }
  catch (error) { return curriculumProxyError(error); }
}
