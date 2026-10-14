export default function TranscriptLoading() {
  return <div className="loading-state" role="status" aria-live="polite" aria-busy="true">
    <span className="loading-indicator" aria-hidden="true" />
    <p>Loading published transcript…</p>
  </div>;
}
