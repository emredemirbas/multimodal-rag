"use client";

import { useEffect } from "react";

interface ProjectsErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ProjectsError({ error, reset }: ProjectsErrorProps) {
  useEffect(() => {
    console.error("Projects route failed", { digest: error.digest ?? "unknown" });
  }, [error]);

  return (
    <div className="state-panel state-panel--error" role="alert">
      <h1>Something went wrong</h1>
      <p>The latest workspace could not be displayed. If you were submitting a change, reload to verify its status before trying again.</p>
      <button type="button" className="button button--secondary" onClick={reset}>
        Try again
      </button>
      <button type="button" className="button button--secondary" onClick={() => window.location.reload()}>
        Reload latest page
      </button>
    </div>
  );
}
