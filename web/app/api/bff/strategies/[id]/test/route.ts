import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const res = await apiFetch(`/strategies/${encodeURIComponent(id)}/test`, {
    method: "POST",
    body: await req.text(),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
