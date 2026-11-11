import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DraftListWorkspace } from "@/components/curriculum/draft-list";
import { ApiErrorState } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import { listDrafts } from "@/lib/api/drafts";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = { title: "Saved assignment drafts" };
export default async function DraftsPage({ params }: { params: Promise<{ projectId: string; contextId: string }> }) {
  const { projectId, contextId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(contextId)) notFound();
  async function load() {
    const project = await getProject(projectId);
    if (project.id.toLowerCase() !== projectId.toLowerCase()) throw new ApiError({ status: 502, code: "invalid_api_response" });
    const scope = { tenant_id: project.tenant_id, project_id: project.id };
    return { project, scope, drafts: await listDrafts(scope, contextId) };
  }
  let loaded: Awaited<ReturnType<typeof load>> | null = null, failure: unknown;
  try { loaded = await load(); } catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); failure = error; }
  if (!loaded) return <ApiErrorState title="Saved drafts could not load" message={publicErrorMessage(failure)} reference={errorReference(failure)} retryHref={`/projects/${projectId}/learning/contexts/${contextId}/drafts`} />;
  const { project, scope, drafts } = loaded;
  return <div className="stack stack--large"><nav aria-label="Breadcrumb"><ol className="breadcrumbs"><li><Link href="/projects">Projects</Link></li><li><Link href={`/projects/${project.id}`}>{project.title}</Link></li><li><Link href={`/projects/${project.id}/learning/contexts/${contextId}`}>Saved selection</Link></li><li aria-current="page">Drafts</li></ol></nav><header><p className="eyebrow">Learning preparation</p><h1>Saved assignment drafts</h1></header><DraftListWorkspace key={`${scope.tenant_id}:${project.id}:${contextId}`} scope={scope} contextId={contextId} initial={drafts} /></div>;
}
