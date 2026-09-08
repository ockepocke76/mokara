import { NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";

type Ctx = { params: Promise<{ runId: string }> };

// SSE must never be statically cached or buffered.
export const dynamic = "force-dynamic";

/** SSE pass-through: pipe the API's event stream body to the browser. */
export async function GET(req: NextRequest, { params }: Ctx) {
  const { runId } = await params;
  const after = req.nextUrl.searchParams.get("after") ?? "0";
  const res = await apiFetch(
    `/strategies/generate/${encodeURIComponent(runId)}/events?after=${encodeURIComponent(after)}`,
  );
  if (!res.ok || !res.body) {
    return new Response(await res.text(), { status: res.status });
  }
  return new Response(res.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
