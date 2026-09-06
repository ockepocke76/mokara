import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const res = await apiFetch(`/strategies/${encodeURIComponent(id)}/evaluation`);
  return NextResponse.json(await res.json(), { status: res.status });
}
