"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import {
  archiveProject as archiveProjectRequest,
  createProject as createProjectRequest,
  deleteProject as deleteProjectRequest,
  renameProject as renameProjectRequest,
  restoreProject as restoreProjectRequest,
} from "@/lib/api/client";
import { ApiError, errorReference, publicErrorMessage } from "@/lib/api/errors";
import type { ProjectActionState } from "@/lib/action-state";
import { projectIdFromForm, validateProjectTitle } from "@/lib/validation/projects";

function failure(previous: ProjectActionState, error: unknown): ProjectActionState {
  return {
    status: "error",
    message: publicErrorMessage(error),
    fieldErrors: {},
    reference: errorReference(error),
    version: previous.version + 1,
  };
}

function invalidProject(previous: ProjectActionState): ProjectActionState {
  return {
    status: "error",
    message: "The project identifier is invalid. Return to the projects page and try again.",
    fieldErrors: {},
    reference: null,
    version: previous.version + 1,
  };
}

export async function createProjectAction(
  previous: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const result = validateProjectTitle(formData.get("title"));
  if (!result.ok) {
    return {
      status: "error",
      message: "Check the project name and try again.",
      fieldErrors: { title: result.message },
      reference: null,
      version: previous.version + 1,
    };
  }

  let projectId: string;
  try {
    const project = await createProjectRequest(result.title);
    projectId = project.id;
  } catch (error) {
    const state = failure(previous, error);
    return { ...state, message: `${state.message} If delivery was interrupted, refresh the projects list before trying again; creation may already have completed.` };
  }

  revalidatePath("/projects");
  redirect(`/projects/${projectId}?notice=created`);
}

export async function renameProjectAction(
  previous: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const projectId = projectIdFromForm(formData);
  if (!projectId) {
    return invalidProject(previous);
  }

  const result = validateProjectTitle(formData.get("title"));
  if (!result.ok) {
    return {
      status: "error",
      message: "Check the project name and try again.",
      fieldErrors: { title: result.message },
      reference: null,
      version: previous.version + 1,
    };
  }

  let acceptedTitle: string;
  try {
    const project = await renameProjectRequest(projectId, result.title);
    if (project.id !== projectId) throw new ApiError({ status: 502, code: "invalid_api_response" });
    acceptedTitle = project.title;
  } catch (error) {
    return failure(previous, error);
  }

  revalidatePath("/projects");
  revalidatePath(`/projects/${projectId}`);
  return {
    status: "success",
    message: "Project name updated.",
    fieldErrors: {},
    reference: null,
    version: previous.version + 1,
    acceptedTitle,
  };
}

export async function archiveProjectAction(
  previous: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const projectId = projectIdFromForm(formData);
  if (!projectId) {
    return invalidProject(previous);
  }

  try {
    await archiveProjectRequest(projectId);
  } catch (error) {
    return failure(previous, error);
  }

  revalidatePath("/projects");
  revalidatePath(`/projects/${projectId}`);
  redirect("/projects?status=archived&notice=archived");
}

export async function restoreProjectAction(
  previous: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const projectId = projectIdFromForm(formData);
  if (!projectId) {
    return invalidProject(previous);
  }

  try {
    await restoreProjectRequest(projectId);
  } catch (error) {
    return failure(previous, error);
  }

  revalidatePath("/projects");
  revalidatePath(`/projects/${projectId}`);
  redirect(`/projects/${projectId}?notice=restored`);
}

export async function deleteProjectAction(
  previous: ProjectActionState,
  formData: FormData,
): Promise<ProjectActionState> {
  const projectId = projectIdFromForm(formData);
  if (!projectId) {
    return invalidProject(previous);
  }

  let cleanupId: string | null;
  try {
    cleanupId = await deleteProjectRequest(projectId);
  } catch (error) {
    return failure(previous, error);
  }

  revalidatePath("/projects");
  redirect(cleanupId ? `/projects?notice=deleted&cleanup=${encodeURIComponent(cleanupId)}&cleanupProject=${projectId}` : "/projects?notice=deleted");
}
