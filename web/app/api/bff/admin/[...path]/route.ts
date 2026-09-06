import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/api";

/**
 * Proxy for admin endpoints. Forwards under /admin/* only; the API enforces
 * the admin tier server-side on every route.
 */
async function forward(req: NextRequest, path: string[]) {
  const qs = req.nextUrl.search;
  const target = `/admin/${path.map(encodeURIComponent).join("/")}${qs}`;
  const hasBody = req.method !== "GET" && req.method !== "DELETE";
  const res = await apiFetch(target, {
    method: req.method,
    body: hasBody ? await req.text() : undefined,
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, { params }: Ctx) {
  return forward(req, (await params).path);
}

export async function POST(req: NextRequest, { params }: Ctx) {
  return forward(req, (await params).path);
}

export async function DELETE(req: NextRequest, { params }: Ctx) {
  return forward(req, (await params).path);
}
