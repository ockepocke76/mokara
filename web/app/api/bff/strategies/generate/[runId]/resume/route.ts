import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

type Ctx = { params: Promise<{ runId: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { runId } = await params;
  const res = await apiFetch(
    `/strategies/generate/${encodeURIComponent(runId)}/resume`,
    { method: "POST", body: await req.text() },
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
