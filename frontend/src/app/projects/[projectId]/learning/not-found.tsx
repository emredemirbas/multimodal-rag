import Link from "next/link";
export default function LearningNotFound() {
  return <div className="state-panel"><h1>Learning material unavailable</h1><p>The project or saved selection could not be found. Deleting a selected source also removes its saved selections and documentation.</p><Link href="/projects">Back to projects</Link></div>;
}
