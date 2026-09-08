import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

type Ctx = { params: Promise<{ runId: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { runId } = await params;
  return proxyJson(`/strategies/generate/${encodeURIComponent(runId)}/resume`, {
    method: "POST",
    body: await req.text(),
  });
}
