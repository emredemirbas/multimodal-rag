import type { ProjectActionState } from "@/lib/action-state";

interface ActionStatusProps {
  state: ProjectActionState;
}

export function ActionStatus({ state }: ActionStatusProps) {
  if (state.status === "idle") {
    return <div className="action-status-placeholder" aria-live="polite" />;
  }

  return (
    <div
      className={`action-status action-status--${state.status}`}
      role={state.status === "error" ? "alert" : "status"}
      key={state.version}
    >
      <p>{state.message}</p>
      {state.reference ? <p className="error-reference">Reference: {state.reference}</p> : null}
    </div>
  );
}
