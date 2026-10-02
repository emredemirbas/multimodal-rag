import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import ProjectsError from "@/app/projects/error";

it("does not assert that an uncertain mutation was unapplied and offers a deployment-safe reload", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const reset = vi.fn();
  render(<ProjectsError error={new Error("must-not-be-displayed")} reset={reset} />);
  expect(screen.getByRole("alert")).toHaveTextContent("reload to verify its status");
  expect(screen.queryByText("must-not-be-displayed")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reload latest page" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledOnce();
});
