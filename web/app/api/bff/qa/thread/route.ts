import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const qs = new URLSearchParams();
  for (const key of ["subject_type", "subject_id"]) {
    const value = req.nextUrl.searchParams.get(key);
    if (value) qs.set(key, value);
  }
  return proxyJson(`/qa/thread?${qs.toString()}`);
}
