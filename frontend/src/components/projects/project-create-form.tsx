"use client";

import { useActionState, useState } from "react";

import { createProjectAction } from "@/app/actions/projects";
import { ActionStatus } from "@/components/ui/action-status";
import { SubmitButton } from "@/components/ui/submit-button";
import { INITIAL_PROJECT_ACTION_STATE } from "@/lib/action-state";

export function ProjectCreateForm() {
  const [title, setTitle] = useState("");
  const [state, action, pending] = useActionState(
    createProjectAction,
    INITIAL_PROJECT_ACTION_STATE,
  );
  const errorId = state.fieldErrors.title ? "new-project-title-error" : undefined;

  return (
    <form action={action} className="stack" noValidate aria-busy={pending}>
      <div className="field">
        <label htmlFor="new-project-title">Project name</label>
        <p className="field-hint" id="new-project-title-hint">
          Use a name that identifies the tutorial or learning goal.
        </p>
        <input
          id="new-project-title"
          name="title"
          type="text"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          disabled={pending}
          minLength={1}
          maxLength={120}
          required
          autoComplete="off"
          aria-describedby={
            errorId ? `new-project-title-hint ${errorId}` : "new-project-title-hint"
          }
          aria-invalid={Boolean(errorId)}
        />
        {state.fieldErrors.title ? (
          <p className="field-error" id={errorId}>
            {state.fieldErrors.title}
          </p>
        ) : null}
      </div>
      <div className="form-actions">
        <SubmitButton pendingLabel="Creating project…">Create project</SubmitButton>
      </div>
      <ActionStatus state={state} />
    </form>
  );
}
