import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DraftEditor } from "@/components/curriculum/draft-editor";
import { ApiErrorState } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import { getDraft } from "@/lib/api/drafts";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = { title: "Review assignment draft" };
export default async function DraftPage({ params }: { params: Promise<{ projectId: string; draftId: string }> }) {
  const { projectId, draftId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(draftId)) notFound();
  async function load() {
    const project = await getProject(projectId);
    if (project.id.toLowerCase() !== projectId.toLowerCase()) throw new ApiError({ status: 502, code: "invalid_api_response" });
    const loaded = await getDraft({ tenant_id: project.tenant_id, project_id: project.id }, draftId);
    return { project, ...loaded };
  }
  let loaded: Awaited<ReturnType<typeof load>> | null = null, failure: unknown;
  try { loaded = await load(); } catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); failure = error; }
  if (!loaded) return <ApiErrorState title="Assignment draft could not load" message={publicErrorMessage(failure)} reference={errorReference(failure)} retryHref={`/projects/${projectId}/learning/drafts/${draftId}`} />;
  const { project, result, context } = loaded;
  return <div className="stack stack--large"><nav aria-label="Breadcrumb"><ol className="breadcrumbs"><li><Link href="/projects">Projects</Link></li><li><Link href={`/projects/${project.id}`}>{project.title}</Link></li><li><Link href={`/projects/${project.id}/learning/contexts/${context.id}`}>Saved selection</Link></li><li><Link href={`/projects/${project.id}/learning/contexts/${context.id}/drafts`}>Drafts</Link></li><li aria-current="page">Review draft</li></ol></nav><header><p className="eyebrow">Learning preparation</p><h1>Review assignment draft</h1><p>Inspect the evidence and save wording changes as a new revision. Activation is not available yet.</p></header><DraftEditor initial={result} context={context} archived={project.status === "archived"} /></div>;
}
