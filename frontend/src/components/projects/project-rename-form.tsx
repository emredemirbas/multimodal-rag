"use client";

import { useActionState } from "react";

import { renameProjectAction } from "@/app/actions/projects";
import { ActionStatus } from "@/components/ui/action-status";
import { SubmitButton } from "@/components/ui/submit-button";
import { INITIAL_PROJECT_ACTION_STATE } from "@/lib/action-state";

interface ProjectRenameFormProps {
  projectId: string;
  title: string;
}

export function ProjectRenameForm({ projectId, title }: ProjectRenameFormProps) {
  const [state, action] = useActionState(
    renameProjectAction,
    INITIAL_PROJECT_ACTION_STATE,
  );
  const errorId = state.fieldErrors.title ? "project-title-error" : undefined;

  return (
    <form action={action} className="stack" noValidate>
      <input type="hidden" name="projectId" value={projectId} />
      <div className="field">
        <label htmlFor="project-title">Project name</label>
        <input
          id="project-title"
          name="title"
          type="text"
          defaultValue={title}
          minLength={1}
          maxLength={120}
          required
          autoComplete="off"
          aria-describedby={errorId}
          aria-invalid={Boolean(errorId)}
        />
        {state.fieldErrors.title ? (
          <p className="field-error" id={errorId}>
            {state.fieldErrors.title}
          </p>
        ) : null}
      </div>
      <div className="form-actions">
        <SubmitButton pendingLabel="Saving…">Save name</SubmitButton>
      </div>
      <ActionStatus state={state} />
    </form>
  );
}
