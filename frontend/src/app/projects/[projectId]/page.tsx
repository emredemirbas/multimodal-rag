import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProjectLifecycleControls } from "@/components/projects/project-lifecycle-controls";
import { ProjectRenameForm } from "@/components/projects/project-rename-form";
import { ApiErrorState, Notice } from "@/components/ui/api-state";
import { getProject } from "@/lib/api/client";
import type { Project } from "@/lib/api/contracts";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "Project details",
};

interface ProjectPageProps {
  params: Promise<{ projectId: string }>;
  searchParams: Promise<{ notice?: string | string[] }>;
}

const DATE_FORMAT = new Intl.DateTimeFormat("en", {
  dateStyle: "long",
  timeZone: "UTC",
});

function detailNotice(value: string | string[] | undefined): string | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (candidate === "created") {
    return "Project created. You can now configure its name.";
  }
  if (candidate === "restored") {
    return "Project restored to your active workspace.";
  }
  return null;
}

export default async function ProjectPage({ params, searchParams }: ProjectPageProps) {
  const [{ projectId }, query] = await Promise.all([params, searchParams]);

  let project: Project | null = null;
  let loadError: unknown = null;
  try {
    project = await getProject(projectId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    loadError = error;
  }

  if (loadError || !project) {
    return (
      <ApiErrorState
        message={publicErrorMessage(loadError)}
        retryHref={`/projects/${encodeURIComponent(projectId)}`}
        reference={errorReference(loadError)}
      />
    );
  }

  const notice = detailNotice(query.notice);

  return (
    <div className="stack stack--large">
      <nav aria-label="Breadcrumb">
        <ol className="breadcrumbs">
          <li>
            <Link href="/projects">Projects</Link>
          </li>
          <li aria-current="page">{project.title}</li>
        </ol>
      </nav>

      {notice ? <Notice>{notice}</Notice> : null}

      <header className="project-header">
        <div>
          <p className="eyebrow">Project workspace</p>
          <h1>{project.title}</h1>
          <p className="project-card__meta">Created {DATE_FORMAT.format(new Date(project.created_at))}</p>
        </div>
        <span
          className={`status-badge status-badge--${project.status}`}
          aria-label={`Status: ${project.status}`}
        >
          {project.status === "active" ? "Active" : "Archived"}
        </span>
      </header>

      <div className="detail-grid">
        <section className="panel" aria-labelledby="workspace-heading">
          <p className="eyebrow">Learning material</p>
          <h2 id="workspace-heading">Workspace</h2>
          <div className="state-panel state-panel--compact">
            <h3>No source management yet</h3>
            <p>
              Transcript processing arrives in Sprint 2. Citation-backed chat follows in Sprint 3.
            </p>
          </div>
        </section>

        <section className="panel" aria-labelledby="settings-heading">
          <p className="eyebrow">Project settings</p>
          <h2 id="settings-heading">Name</h2>
          <ProjectRenameForm projectId={project.id} title={project.title} />
        </section>

        <section className="panel panel--wide" aria-labelledby="lifecycle-heading">
          <p className="eyebrow">Project lifecycle</p>
          <h2 id="lifecycle-heading">
            {project.status === "active" ? "Archive or delete" : "Restore or delete"}
          </h2>
          <ProjectLifecycleControls
            projectId={project.id}
            projectTitle={project.title}
            status={project.status}
          />
        </section>
      </div>
    </div>
  );
}
