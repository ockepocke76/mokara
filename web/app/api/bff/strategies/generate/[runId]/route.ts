import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

type Ctx = { params: Promise<{ runId: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { runId } = await params;
  const res = await apiFetch(`/strategies/generate/${encodeURIComponent(runId)}`);
  return NextResponse.json(await res.json(), { status: res.status });
}
