import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const res = await apiFetch(`/jobs/${encodeURIComponent(id)}`);
  return NextResponse.json(await res.json(), { status: res.status });
}
