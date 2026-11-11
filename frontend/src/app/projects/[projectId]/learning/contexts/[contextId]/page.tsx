import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SavedContextWorkspace } from "@/components/curriculum/saved-context-workspace";
import { ApiErrorState } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import { getDocumentationCatalog, getLearningContext, listContextDocuments } from "@/lib/api/curriculum";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = { title: "Saved learning material" };

export default async function ContextPage({ params }: { params: Promise<{ projectId: string; contextId: string }> }) {
  const { projectId, contextId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(contextId)) notFound();
  let loadError: unknown = null;
  let loaded: Awaited<ReturnType<typeof load>> | null = null;
  try { loaded = await load(); }
  catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    loadError = error;
  }
  async function load() {
    const project = await getProject(projectId);
    if (project.id.toLowerCase() !== projectId.toLowerCase()) throw new ApiError({ status: 502, code: "invalid_api_response" });
    const scope = { tenant_id: project.tenant_id, project_id: project.id };
    const context = await getLearningContext(scope, contextId);
    const [catalog, documents] = await Promise.all([
      getDocumentationCatalog(scope), listContextDocuments(scope, context.id),
    ]);
    return { project, context, catalog, documents };
  }
  if (!loaded) return <ApiErrorState title="Saved learning material could not load" message={publicErrorMessage(loadError)}
    retryHref={`/projects/${projectId}/learning/contexts/${contextId}`} reference={errorReference(loadError)} />;
  const { project, context, catalog, documents } = loaded;
  return <div className="stack stack--large">
      <nav aria-label="Breadcrumb"><ol className="breadcrumbs">
        <li><Link href="/projects">Projects</Link></li>
        <li><Link href={`/projects/${project.id}`}>{project.title}</Link></li>
        <li><Link href={`/projects/${project.id}/learning`}>Learning material</Link></li>
        <li aria-current="page">Saved selection</li>
      </ol></nav>
      <header><p className="eyebrow">Learning preparation</p><h1>Saved learning material</h1>
        <p>Your selected source versions and preferences stay fixed. Bookmark this page to return to this selection.</p>
      </header>
      <SavedContextWorkspace key={`${project.id}:${context.id}`} context={context} projectId={project.id}
        archived={project.status === "archived"} catalog={catalog} initialDocuments={documents} />
    </div>;
}
