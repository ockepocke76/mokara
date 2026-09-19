import { NextRequest } from "next/server";

import { proxyJson } from "@/lib/api";

export async function POST(req: NextRequest) {
  return proxyJson("/qa/messages", {
    method: "POST",
    body: await req.text(),
  });
}
