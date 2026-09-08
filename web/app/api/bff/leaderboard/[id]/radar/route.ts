import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const qs = req.nextUrl.searchParams;
  const category = qs.get("category") ?? "WITHDRAWAL_ONLY";
  const profile = qs.get("profile") ?? "balanced_withdrawal";
  const res = await apiFetch(
    `/leaderboard/${encodeURIComponent(id)}/radar?category=${encodeURIComponent(category)}&profile=${encodeURIComponent(profile)}`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
