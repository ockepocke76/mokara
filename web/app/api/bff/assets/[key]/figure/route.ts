import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ key: string }> },
) {
  const { key } = await params;
  const res = await apiFetch(`/assets/${encodeURIComponent(key)}/figure`);
  return NextResponse.json(await res.json(), { status: res.status });
}
