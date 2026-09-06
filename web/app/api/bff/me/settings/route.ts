import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function PUT(req: NextRequest) {
  const res = await apiFetch("/me/settings", {
    method: "PUT",
    body: JSON.stringify(await req.json()),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
