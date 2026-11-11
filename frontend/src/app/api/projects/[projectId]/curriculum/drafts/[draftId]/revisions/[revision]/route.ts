import { readDraft } from "@/lib/api/drafts";
import { curriculumProxyError } from "@/lib/api/curriculum-proxy";
import { ApiError } from "@/lib/api/errors";
export async function GET(_request: Request, { params }: { params: Promise<{ projectId: string; draftId: string; revision: string }> }) {
  try { const { projectId, draftId, revision } = await params;
    if (!/^[1-9][0-9]{0,9}$/.test(revision)) throw new ApiError({ status: 404 });
    return await readDraft(projectId, draftId, Number(revision));
  } catch (error) { return curriculumProxyError(error, "curriculum_draft_not_found"); }
}
