import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const res = await apiFetch(`/leaderboard/${encodeURIComponent(id)}/clone`, {
    method: "POST",
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
