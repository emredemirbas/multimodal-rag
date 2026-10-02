import { describe, expect, it } from "vitest";

import { ApiError, apiErrorFromResponse, publicErrorMessage } from "@/lib/api/errors";

describe("API error normalization", () => {
  it("keeps a stable code and request reference without exposing API detail", async () => {
    const response = new Response(
      JSON.stringify({
        code: "project_conflict",
        detail: "sensitive internal database detail",
      }),
      {
        status: 409,
        headers: {
          "content-type": "application/json",
          "x-request-id": "request-409",
        },
      },
    );

    const error = await apiErrorFromResponse(response);

    expect(error.status).toBe(409);
    expect(error.code).toBe("project_conflict");
    expect(error.requestId).toBe("request-409");
    expect(error.message).not.toContain("database");
    expect(publicErrorMessage(error)).toMatch(/changed while you were editing/i);
  });

  it("uses a safe message for an unavailable upstream", () => {
    const error = new ApiError({ status: 503, code: "upstream_unavailable" });

    expect(publicErrorMessage(error)).toBe(
      "The project service is temporarily unavailable. Please try again.",
    );
  });

  it("falls back safely when an error body is not JSON", async () => {
    const response = new Response("gateway failure", { status: 502 });
    const error = await apiErrorFromResponse(response);

    expect(error.code).toBe("request_failed");
    expect(publicErrorMessage(error)).not.toContain("gateway failure");
  });
});
