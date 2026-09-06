import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

export async function GET() {
  const res = await apiFetch("/strategies");
  return NextResponse.json(await res.json(), { status: res.status });
}
