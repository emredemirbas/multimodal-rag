export interface ProjectActionState {
  status: "idle" | "error" | "success";
  message: string;
  fieldErrors: {
    title?: string;
  };
  reference: string | null;
  version: number;
  acceptedTitle?: string;
}

export const INITIAL_PROJECT_ACTION_STATE: ProjectActionState = {
  status: "idle",
  message: "",
  fieldErrors: {},
  reference: null,
  version: 0,
};
