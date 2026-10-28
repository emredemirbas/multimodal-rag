"use client";

import { useActionState, useState } from "react";

import { renameProjectAction } from "@/app/actions/projects";
import { ActionStatus } from "@/components/ui/action-status";
import { SubmitButton } from "@/components/ui/submit-button";
import { INITIAL_PROJECT_ACTION_STATE, type ProjectActionState } from "@/lib/action-state";

interface ProjectRenameFormProps {
  projectId: string;
  title: string;
}

export function ProjectRenameForm({ projectId, title }: ProjectRenameFormProps) {
  const [draft, setDraft] = useState({ baseline: title, value: title });
  const [state, action, pending] = useActionState(
    async (previous: ProjectActionState, form: FormData) => {
      const next = await renameProjectAction(previous, form);
      const acceptedTitle = next.acceptedTitle;
      if (next.status === "success" && acceptedTitle !== undefined) {
        setDraft((current) => ({ ...current, value: acceptedTitle }));
      }
      return next;
    },
    INITIAL_PROJECT_ACTION_STATE,
  );
  // Refresh pristine values, but never overwrite a user's unsubmitted correction.
  if (draft.baseline !== title) {
    setDraft({ baseline: title, value: draft.value === draft.baseline ? title : draft.value });
  }
  const errorId = state.fieldErrors.title ? "project-title-error" : undefined;

  return (
    <form action={action} className="stack" noValidate aria-busy={pending}>
      <input type="hidden" name="projectId" value={projectId} />
      <div className="field">
        <label htmlFor="project-title">Project name</label>
        <input
          id="project-title"
          name="title"
          type="text"
          value={draft.value}
          onChange={(event) => {
            const value = event.target.value;
            setDraft((current) => ({ ...current, value }));
          }}
          disabled={pending}
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
