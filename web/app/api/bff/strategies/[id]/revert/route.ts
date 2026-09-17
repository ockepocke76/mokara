import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const body = await req.text();
  return proxyJson(`/strategies/${encodeURIComponent(id)}/revert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
