import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LearningContextForm } from "@/components/curriculum/learning-context-form";
import { ApiErrorState } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import { listLearningSources } from "@/lib/api/curriculum";
import { UUID_PATTERN } from "@/lib/api/identifiers";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = { title: "Prepare learning material" };

export default async function LearningPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  if (!UUID_PATTERN.test(projectId)) notFound();
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
    const sources = await listLearningSources({ tenant_id: project.tenant_id, project_id: project.id });
    return { project, sources };
  }
  if (!loaded) return <ApiErrorState title="Learning material could not load" message={publicErrorMessage(loadError)}
    retryHref={`/projects/${projectId}/learning`} reference={errorReference(loadError)} />;
  const { project, sources } = loaded;
  return <div className="stack stack--large">
      <nav aria-label="Breadcrumb"><ol className="breadcrumbs">
        <li><Link href="/projects">Projects</Link></li>
        <li><Link href={`/projects/${project.id}`}>{project.title}</Link></li>
        <li aria-current="page">Learning material</li>
      </ol></nav>
      <header><p className="eyebrow">Learning preparation</p><h1>Prepare learning material</h1>
        <p>Choose published material and your preferences. Saving a selection does not generate an assignment or retrieve an external document.</p>
      </header>
      <LearningContextForm key={project.id} projectId={project.id} tenantId={project.tenant_id} sources={sources} archived={project.status === "archived"} />
    </div>;
}
