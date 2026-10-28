import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DemoPage, { metadata } from "@/app/demo/page";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

describe("static keyless demo walkthrough", () => {
  it("reuses the exact existing authored transcript and includes its unchanged MIT notice", () => {
    expect(readFileSync(path.join(frontend, "public/samples/fastapi-intro.vtt")))
      .toEqual(readFileSync(path.join(frontend, "../examples/fastapi-intro.vtt")));
    expect(readFileSync(path.join(frontend, "public/samples/LICENSE.txt")))
      .toEqual(readFileSync(path.join(frontend, "../LICENSE")));
  });
  it("renders an accessible server-only guide without a provider, project read or automatic mutation", () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    try {
      render(<DemoPage />);
      expect(metadata.title).toBe("Keyless demo guide");
      expect(screen.getByRole("heading", { level: 1, name: "Try the keyless demo" })).toBeVisible();
      expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(5);
      expect(screen.getByRole("link", { name: "Download sample VTT" })).toHaveAttribute("href", "/samples/fastapi-intro.vtt");
      expect(screen.getByRole("link", { name: "Download sample VTT" })).toHaveAttribute("download", "fastapi-intro.vtt");
      expect(screen.getByRole("link", { name: "Download sample MIT license" })).toHaveAttribute("href", "/samples/LICENSE.txt");
      expect(screen.getByRole("link", { name: "Create a project" })).toHaveAttribute("href", "/projects#create-project");
      expect(screen.queryByRole("button")).toBeNull();
      expect(screen.queryByRole("form")).toBeNull();
      expect(fetcher).not.toHaveBeenCalled();
    } finally { vi.unstubAllGlobals(); }
  });
  it("labels synthetic rights, default mode, actual chunk spans, abstention and confirmed cleanup honestly", () => {
    render(<DemoPage />);
    expect(screen.getByText(/default offline extractive/)).toHaveTextContent("this guide changes no settings");
    expect(screen.getByText(/Four authored subtitle cues/)).toHaveTextContent("no underlying recording");
    expect(screen.getByText(/For Ownership/)).toHaveTextContent("Its license permits this processing");
    expect(screen.getByText(/Wait for ready:/)).toHaveTextContent("without reloading the page");
    expect(screen.getByText(/Default answers quote/)).toHaveTextContent("00:01–00:22");
    expect(screen.getByText("How does Kubernetes ingress handle TLS?").parentElement).toHaveTextContent("no citations");
    expect(screen.getByText(/Records become inaccessible/)).toHaveTextContent("Retained file cleanup completed.");
    expect(screen.getByText(/does not complete the independent/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });
  it("packages the public sample in the standalone Docker runner", () => {
    const dockerfile = readFileSync(path.join(frontend, "Dockerfile"), "utf8");
    expect(dockerfile).toContain("COPY --from=builder --chown=node:node /app/public ./public");
  });
});
