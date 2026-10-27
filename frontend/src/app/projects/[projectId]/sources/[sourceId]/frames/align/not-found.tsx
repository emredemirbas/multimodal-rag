import Link from "next/link";
export default function AlignmentNotFound() {
  return <section className="state-panel" role="status"><h1>Timeline comparison unavailable</h1>
    <p>Use a complete gallery and published transcript in the same accessible project, confirm the recording and choose valid generations and offset.</p>
    <Link href="/projects">Back to projects</Link></section>;
}
