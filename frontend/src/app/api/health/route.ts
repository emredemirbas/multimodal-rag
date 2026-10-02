import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET() {
  return NextResponse.json(
    { status: "ok", service: "frontend", version: "0.2.0" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
