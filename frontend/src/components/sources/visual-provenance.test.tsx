import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VisualProvenance } from "@/components/sources/visual-provenance";
import { visualFixture } from "../../../test-support/visual-fixture";

describe("versioned visual citation provenance", () => {
  it("shows selection limits beside unreviewed citation origin, including legacy evidence", () => {
    const origin = visualFixture().origin!;
    const { rerender } = render(<VisualProvenance origin={origin} />);
    expect(screen.getByRole("region", { name: "Visual evidence provenance" })).toHaveTextContent("Uniform sampling");
    rerender(<VisualProvenance origin={{ ...origin, profile: `local-visual-v2:${"a".repeat(64)}`, checkpoint_version: "visual-checkpoint-v2" }} />);
    expect(screen.getByRole("region")).toHaveTextContent("Experimental change-aware selection");
    expect(screen.getByRole("region")).toHaveTextContent("not speech or image understanding");
    expect(screen.queryByText(/Uniform sampling/)).toBeNull();
    rerender(<VisualProvenance origin={null} />);
    expect(screen.queryByRole("region")).toBeNull();
  });
});
