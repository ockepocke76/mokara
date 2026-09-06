import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ hash: string }> },
) {
  const { hash } = await params;
  const res = await apiFetch(
    `/simulations/${encodeURIComponent(hash)}/pdf/status`,
  );
  return NextResponse.json(await res.json(), { status: res.status });
}
