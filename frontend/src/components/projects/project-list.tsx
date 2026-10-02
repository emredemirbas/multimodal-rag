import Link from "next/link";

import type { Project, ProjectListStatus } from "@/lib/api/contracts";

interface ProjectListProps {
  projects: Project[];
  status: ProjectListStatus;
}

const DATE_FORMAT = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeZone: "UTC",
});

function emptyMessage(status: ProjectListStatus): string {
  if (status === "archived") {
    return "No archived projects. Projects you archive will appear here.";
  }
  if (status === "all") {
    return "Create a private project to start organizing your tutorial material.";
  }
  return "Create a private project to add your first tutorial.";
}

export function ProjectList({ projects, status }: ProjectListProps) {
  if (projects.length === 0) {
    return (
      <div className="state-panel" data-testid="empty-projects">
        <h2>No projects yet</h2>
        <p>{emptyMessage(status)}</p>
        {status === "archived" ? (
          <Link href="/projects" className="text-link">
            View active projects
          </Link>
        ) : (
          <a href="#create-project" className="text-link">
            Create a project
          </a>
        )}
      </div>
    );
  }

  return (
    <ul className="project-list" aria-label="Projects">
      {projects.map((project) => (
        <li className="project-card" key={project.id}>
          <div className="project-card__content">
            <div className="project-card__heading">
              <h2>
                <Link href={`/projects/${project.id}`}>{project.title}</Link>
              </h2>
              <span
                className={`status-badge status-badge--${project.status}`}
                aria-label={`Status: ${project.status}`}
              >
                {project.status === "active" ? "Active" : "Archived"}
              </span>
            </div>
            <p className="project-card__meta">
              Updated {DATE_FORMAT.format(new Date(project.updated_at))}
            </p>
          </div>
          <Link
            href={`/projects/${project.id}`}
            className="button button--secondary"
            aria-label={`Open ${project.title}`}
          >
            Open
          </Link>
        </li>
      ))}
    </ul>
  );
}
