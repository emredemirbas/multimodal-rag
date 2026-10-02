import Link from "next/link";

interface ApiErrorStateProps {
  message: string;
  retryHref: string;
  reference?: string | null;
}

export function ApiErrorState({ message, retryHref, reference }: ApiErrorStateProps) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <h2>Projects could not load</h2>
      <p>{message}</p>
      {reference ? <p className="error-reference">Reference: {reference}</p> : null}
      <Link className="button button--secondary" href={retryHref}>
        Retry
      </Link>
    </div>
  );
}

interface NoticeProps {
  children: React.ReactNode;
}

export function Notice({ children }: NoticeProps) {
  return (
    <div className="notice" role="status" aria-live="polite">
      {children}
    </div>
  );
}
