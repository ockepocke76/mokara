import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function POST(req: NextRequest) {
  const res = await apiFetch("/strategies/generate", {
    method: "POST",
    body: await req.text(),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
