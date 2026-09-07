import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function PUT(req: NextRequest) {
  const res = await apiFetch("/me/username", {
    method: "PUT",
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function GET() {
  const res = await apiFetch("/me/username/random");
  return NextResponse.json(await res.json(), { status: res.status });
}
