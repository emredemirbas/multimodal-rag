export default function ProjectsLoading() {
  return (
    <div className="loading-state" role="status" aria-live="polite" aria-busy="true">
      <span className="loading-indicator" aria-hidden="true" />
      <div>
        <h1>Projects</h1>
        <p>Loading your projects…</p>
      </div>
    </div>
  );
}
