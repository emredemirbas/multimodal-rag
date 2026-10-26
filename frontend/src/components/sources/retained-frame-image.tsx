"use client";
import Image from "next/image";
import { useState } from "react";
import { frameImageHref, type VisualFrame } from "@/lib/api/visual-contracts";
import { timestamp } from "@/lib/api/chat-contracts";

export function RetainedFrameImage({ projectId, frame }: { projectId: string; frame: VisualFrame }) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  if (state === "error") return <div role="alert">Frame image could not load. OCR below remains available. <button type="button" className="button button--secondary" onClick={() => setState("loading")}>Retry frame image</button></div>;
  return <div aria-busy={state === "loading"}>
    {state === "loading" ? <p role="status">Loading selected frame…</p> : null}
    <Image unoptimized loading="lazy" src={frameImageHref(projectId, frame.id)} alt={`Selected grayscale frame at ${timestamp(frame.timestamp_ms)}`}
      width={frame.width} height={frame.height} style={{ maxWidth: "100%", height: "auto" }} onLoad={() => setState("ready")} onError={() => setState("error")} />
  </div>;
}
