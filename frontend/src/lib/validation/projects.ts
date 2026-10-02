const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export type TitleValidation =
  | { ok: true; title: string }
  | { ok: false; message: string };

export function validateProjectTitle(value: FormDataEntryValue | null): TitleValidation {
  if (typeof value !== "string") {
    return { ok: false, message: "Enter a project name." };
  }

  const title = value.trim();
  if (!title) {
    return { ok: false, message: "Enter a project name." };
  }
  if (title.length > 120) {
    return { ok: false, message: "Project names must be 120 characters or fewer." };
  }

  return { ok: true, title };
}

export function projectIdFromForm(formData: FormData): string | null {
  const value = formData.get("projectId");
  return typeof value === "string" && UUID_PATTERN.test(value) ? value : null;
}
