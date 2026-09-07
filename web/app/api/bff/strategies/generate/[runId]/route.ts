import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

type Ctx = { params: Promise<{ runId: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { runId } = await params;
  return proxyJson(`/strategies/generate/${encodeURIComponent(runId)}`);
}
