import Link from "next/link";

export default function ProjectNotFound() {
  return (
    <div className="state-panel">
      <h1>Project not found</h1>
      <p>The project may have been deleted, or you may not have access to it.</p>
      <Link href="/projects" className="button button--secondary">
        Return to projects
      </Link>
    </div>
  );
}
