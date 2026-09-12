import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  const theme = req.nextUrl.searchParams.get("theme") === "dark" ? "dark" : "light";
  return proxyJson(
    `/strategies/${encodeURIComponent(id)}/flowchart?theme=${theme}`,
  );
}
