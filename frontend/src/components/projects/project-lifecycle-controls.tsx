"use client";

import { useActionState, useEffect, useRef } from "react";

import {
  archiveProjectAction,
  deleteProjectAction,
  restoreProjectAction,
} from "@/app/actions/projects";
import { ActionStatus } from "@/components/ui/action-status";
import { SubmitButton } from "@/components/ui/submit-button";
import { INITIAL_PROJECT_ACTION_STATE } from "@/lib/action-state";
import type { ProjectStatus } from "@/lib/api/contracts";

interface ProjectLifecycleControlsProps {
  projectId: string;
  projectTitle: string;
  status: ProjectStatus;
}

function LifecycleForm({ projectId, status }: Pick<ProjectLifecycleControlsProps, "projectId" | "status">) {
  const actionFunction = status === "active" ? archiveProjectAction : restoreProjectAction;
  const [state, action] = useActionState(actionFunction, INITIAL_PROJECT_ACTION_STATE);
  const isActive = status === "active";

  return (
    <form action={action} className="stack">
      <input type="hidden" name="projectId" value={projectId} />
      <p>
        {isActive
          ? "Archiving hides this project from the active list. You can restore it later."
          : "Restore this project to return it to your active workspace."}
      </p>
      <div className="form-actions">
        <SubmitButton
          pendingLabel={isActive ? "Archiving…" : "Restoring…"}
          className="button button--secondary"
        >
          {isActive ? "Archive project" : "Restore project"}
        </SubmitButton>
      </div>
      <ActionStatus state={state} />
    </form>
  );
}

function DeleteProjectDialog({ projectId, projectTitle }: Omit<ProjectLifecycleControlsProps, "status">) {
  const [state, action] = useActionState(deleteProjectAction, INITIAL_PROJECT_ACTION_STATE);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (state.status === "error" && !dialogRef.current?.open) {
      dialogRef.current?.showModal();
    }
  }, [state]);

  function closeDialog() {
    dialogRef.current?.close();
    triggerRef.current?.focus();
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="button button--danger"
        onClick={() => dialogRef.current?.showModal()}
      >
        Delete project
      </button>
      <dialog
        ref={dialogRef}
        className="confirmation-dialog"
        aria-labelledby="delete-project-title"
        onClose={() => triggerRef.current?.focus()}
      >
        <div className="confirmation-dialog__content">
          <h2 id="delete-project-title">Delete “{projectTitle}”?</h2>
          <p>
            This permanently removes project records immediately and schedules retained file cleanup. This action cannot be undone.
          </p>
          <form action={action} className="stack">
            <input type="hidden" name="projectId" value={projectId} />
            <ActionStatus state={state} />
            <div className="form-actions form-actions--end">
              <button type="button" className="button button--secondary" onClick={closeDialog}>
                Cancel
              </button>
              <SubmitButton pendingLabel="Deleting…" className="button button--danger">
                Yes, delete project
              </SubmitButton>
            </div>
          </form>
        </div>
      </dialog>
    </>
  );
}

export function ProjectLifecycleControls({
  projectId,
  projectTitle,
  status,
}: ProjectLifecycleControlsProps) {
  return (
    <div className="stack stack--large">
      <LifecycleForm projectId={projectId} status={status} />
      <div className="danger-zone">
        <h3>Delete project</h3>
        <p>Delete this project only when you no longer need its learning material.</p>
        <DeleteProjectDialog projectId={projectId} projectTitle={projectTitle} />
      </div>
    </div>
  );
}
