import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DraftEditor } from "@/components/curriculum/draft-editor";
import { ApiErrorState } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import { getAssignmentActivation } from "@/lib/api/activations";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = { title: "Activated assignment version" };

export default async function AssignmentPage({ params }: { params: Promise<{ projectId: string; activationId: string }> }) {
  const { projectId, activationId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(activationId)) notFound();
  async function load() {
    const project = await getProject(projectId);
    if (project.id.toLowerCase() !== projectId.toLowerCase()) throw new ApiError({ status: 502, code: "invalid_api_response" });
    const loaded = await getAssignmentActivation({ tenant_id: project.tenant_id, project_id: project.id }, activationId);
    return { project, ...loaded };
  }
  let loaded: Awaited<ReturnType<typeof load>> | null = null, failure: unknown;
  try { loaded = await load(); } catch (error) { if (error instanceof ApiError && error.status === 404) notFound(); failure = error; }
  if (!loaded) return <ApiErrorState title="Activated version could not load" message={publicErrorMessage(failure)} reference={errorReference(failure)} retryHref={`/projects/${projectId}/learning/assignments/${activationId}`} />;
  const { project, activation, context } = loaded;
  return <div className="stack stack--large">
    <nav aria-label="Breadcrumb"><ol className="breadcrumbs"><li><Link href="/projects">Projects</Link></li><li><Link href={`/projects/${project.id}`}>{project.title}</Link></li><li><Link href={`/projects/${project.id}/learning/contexts/${context.id}`}>Saved selection</Link></li><li><Link href={`/projects/${project.id}/learning/drafts/${activation.draft_id}`}>Editable draft</Link></li><li aria-current="page">Activated version</li></ol></nav>
    <header><p className="eyebrow">Accepted learning assignment</p><h1>Activated assignment version</h1><p>This bookmarked version keeps its accepted wording and evidence when the draft is edited. Deleting its draft or a dependency removes this version too.</p></header>
    <DraftEditor initial={activation.draft} context={context} archived={project.status === "archived"} activatedVersion={activation} />
  </div>;
}
