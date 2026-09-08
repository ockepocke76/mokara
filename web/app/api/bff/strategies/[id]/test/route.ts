import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

type Ctx = { params: Promise<{ id: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return proxyJson(`/strategies/${encodeURIComponent(id)}/test`, {
    method: "POST",
    body: await req.text(),
  });
}
