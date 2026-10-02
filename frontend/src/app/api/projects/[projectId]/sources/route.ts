import { NextResponse } from "next/server";

import { listSources } from "@/lib/api/sources";
import { UUID_PATTERN } from "@/lib/api/source-contracts";
import { ApiError, publicErrorMessage } from "@/lib/api/errors";

export async function GET(_request: Request, { params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  if (!UUID_PATTERN.test(projectId)) return NextResponse.json({ message: "Invalid project." }, { status: 404 });
  try {
    return NextResponse.json({ items: await listSources(projectId) }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ message: publicErrorMessage(error) }, { status: error instanceof ApiError ? error.status : 502 });
  }
}
