"use client";

import { useEffect } from "react";

interface ProjectsErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ProjectsError({ error, reset }: ProjectsErrorProps) {
  useEffect(() => {
    console.error("Projects route failed", error);
  }, [error]);

  return (
    <div className="state-panel state-panel--error" role="alert">
      <h1>Something went wrong</h1>
      <p>The projects page could not be displayed. No changes were made.</p>
      <button type="button" className="button button--secondary" onClick={reset}>
        Try again
      </button>
    </div>
  );
}
