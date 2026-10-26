import Link from "next/link";
export default function FramesNotFound() {
  return <div className="state-panel"><h1>Selected frames unavailable</h1><p>The source was removed or is unavailable, or you do not have access.</p><Link href="/projects">Back to projects</Link></div>;
}
