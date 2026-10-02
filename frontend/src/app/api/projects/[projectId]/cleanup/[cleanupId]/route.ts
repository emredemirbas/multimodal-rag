import { NextResponse } from "next/server";

import { requestJson } from "@/lib/api/client";
import { parseCleanup, UUID_PATTERN } from "@/lib/api/source-contracts";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";

export async function GET(_request: Request, { params }: { params: Promise<{ projectId: string; cleanupId: string }> }) {
  const { projectId, cleanupId } = await params;
  if (!UUID_PATTERN.test(projectId) || !UUID_PATTERN.test(cleanupId)) return NextResponse.json({ message: "Invalid cleanup ticket." }, { status: 404 });
  try {
    const ticket = parseCleanup(await requestJson(`/api/v1/projects/${projectId}/cleanup/${cleanupId}`));
    return NextResponse.json(ticket, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ message: publicErrorMessage(error) }, { status: error instanceof ApiError ? error.status : 502 });
  }
}
