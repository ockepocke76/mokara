import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ hash: string }> },
) {
  const { hash } = await params;
  const res = await apiFetch(`/simulations/${encodeURIComponent(hash)}/pdf`, {
    method: "POST",
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ hash: string }> },
) {
  const { hash } = await params;
  const res = await apiFetch(`/simulations/${encodeURIComponent(hash)}/pdf`);
  if (!res.ok) {
    return NextResponse.json(await res.json(), { status: res.status });
  }
  return new NextResponse(res.body, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition":
        res.headers.get("Content-Disposition") ?? "attachment",
    },
  });
}
