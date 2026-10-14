import Link from "next/link";

export default function TranscriptNotFound() {
  return <div className="state-panel">
    <h1>Transcript unavailable</h1>
    <p>This source, published generation or page is unavailable, or you do not have access. Open the project again to choose its current transcript.</p>
    <Link href="/projects">Back to projects</Link>
  </div>;
}
