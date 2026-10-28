import type { Metadata } from "next";
import Link from "next/link";

import { ProjectCreateForm } from "@/components/projects/project-create-form";
import { ProjectList } from "@/components/projects/project-list";
import { ProjectStatusFilter } from "@/components/projects/project-status-filter";
import { ApiErrorState, Notice } from "@/components/ui/api-state";
import { listProjects } from "@/lib/api/client";
import type { Project, ProjectListStatus } from "@/lib/api/contracts";
import { errorReference, publicErrorMessage } from "@/lib/api/errors";
import { UUID_PATTERN } from "@/lib/api/source-contracts";
import { CleanupStatus } from "@/components/sources/cleanup-status";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata: Metadata = {
  title: "Projects",
};

interface ProjectsPageProps {
  searchParams: Promise<{
    status?: string | string[];
    notice?: string | string[];
    cleanup?: string;
    cleanupProject?: string;
  }>;
}

const NOTICE_MESSAGES: Record<string, string> = {
  archived: "Project archived. You can restore it at any time.",
  deleted: "Project records deleted. Retained file cleanup is tracked separately.",
};

function projectStatus(value: string | string[] | undefined): ProjectListStatus {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate === "archived" || candidate === "all" ? candidate : "active";
}

function noticeMessage(value: string | string[] | undefined): string | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate ? (NOTICE_MESSAGES[candidate] ?? null) : null;
}

export default async function ProjectsPage({ searchParams }: ProjectsPageProps) {
  const query = await searchParams;
  const status = projectStatus(query.status);
  const notice = noticeMessage(query.notice);
  const retryHref = status === "active" ? "/projects" : `/projects?status=${status}`;

  let projects: Project[] | null = null;
  let loadError: unknown = null;
  try {
    const result = await listProjects(status);
    projects = result.items;
  } catch (error) {
    loadError = error;
  }

  const content = loadError ? (
      <ApiErrorState
        message={publicErrorMessage(loadError)}
        retryHref={retryHref}
        reference={errorReference(loadError)}
      />
    ) : (
      <ProjectList projects={projects ?? []} status={status} />
    );

  return (
    <div className="page-grid">
      <section className="page-primary" aria-labelledby="projects-heading">
        <div className="page-heading">
          <div>
            <p className="eyebrow">Private learning workspace</p>
            <h1 id="projects-heading">Projects</h1>
            <p className="lede">Organize each tutorial and its learning material in one place.</p>
          </div>
        </div>
        {notice ? <Notice>{notice}</Notice> : null}
        {typeof query.cleanup === "string" && typeof query.cleanupProject === "string" && UUID_PATTERN.test(query.cleanup) && UUID_PATTERN.test(query.cleanupProject)
          ? <CleanupStatus initialTicket={{ id: query.cleanup, project_id: query.cleanupProject, status: "pending" }} /> : null}
        <ProjectStatusFilter selected={status} />
        {content}
      </section>

      <aside className="panel page-sidebar" id="create-project" aria-labelledby="create-heading">
        <p className="eyebrow">Get started</p>
        <h2 id="create-heading">Create a project</h2>
        <p>Projects are private and keep their sources and learning activity isolated.</p>
        <ProjectCreateForm />
        <p>New here? <Link href="/demo">Try the keyless demo with a synthetic sample.</Link></p>
      </aside>
    </div>
  );
}
