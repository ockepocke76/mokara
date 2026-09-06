import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const res = await apiFetch("/simulations", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
