import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const profile = req.nextUrl.searchParams.get("profile") ?? "balanced";
  const res = await apiFetch(
    `/leaderboard/${encodeURIComponent(id)}/radar?profile=${encodeURIComponent(profile)}`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
