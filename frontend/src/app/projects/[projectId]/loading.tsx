export default function ProjectLoading() {
  return (
    <div className="loading-state" role="status" aria-live="polite" aria-busy="true">
      <span className="loading-indicator" aria-hidden="true" />
      <div>
        <h1>Project</h1>
        <p>Loading project details…</p>
      </div>
    </div>
  );
}
