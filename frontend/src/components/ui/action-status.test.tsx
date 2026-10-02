import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActionStatus } from "@/components/ui/action-status";
import { INITIAL_PROJECT_ACTION_STATE } from "@/lib/action-state";

describe("ActionStatus", () => {
  it("announces a successful mutation as status text", () => {
    render(
      <ActionStatus
        state={{
          ...INITIAL_PROJECT_ACTION_STATE,
          status: "success",
          message: "Project name updated.",
          version: 1,
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Project name updated.");
  });

  it("announces a safe failure and request reference as an alert", () => {
    render(
      <ActionStatus
        state={{
          ...INITIAL_PROJECT_ACTION_STATE,
          status: "error",
          message: "The project service is temporarily unavailable. Please try again.",
          reference: "request-123",
          version: 1,
        }}
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("temporarily unavailable");
    expect(alert).toHaveTextContent("Reference: request-123");
  });
});
