/**
 * BFF helper: server-side fetch to the FastAPI backend.
 *
 * The browser never calls the API directly. Server components and route
 * handlers use apiFetch(), which attaches the internal shared secret and the
 * authenticated viewer's identity claims (from the Better Auth session).
 */
import "server-only";

import { headers } from "next/headers";
import { unstable_rethrow } from "next/navigation";
import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const session = await auth.api.getSession({ headers: await headers() });

  const h = new Headers(init.headers);
  h.set("X-Internal-Secret", process.env.INTERNAL_API_SECRET ?? "");
  if (session?.user?.email) {
    h.set("X-User-Email", session.user.email);
    if (session.user.name) h.set("X-User-Name", session.user.name);
  }
  if (init.body && !h.has("Content-Type")) {
    h.set("Content-Type", "application/json");
  }

  return fetch(`${API_URL}${path}`, { ...init, headers: h, cache: "no-store" });
}

/**
 * BFF route boilerplate: forward to the API and relay the JSON response.
 * Tolerates non-JSON upstream bodies (proxy 502 pages, API down) instead of
 * turning them into unhandled 500s.
 */
export async function proxyJson(
  path: string,
  init: RequestInit = {},
): Promise<NextResponse> {
  const res = await apiFetch(path, init);
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = { detail: res.statusText || "Upstream error" };
  }
  return NextResponse.json(body, { status: res.status });
}

export type Viewer = {
  authenticated: boolean;
  /** True when this is the outage fallback, not a real /me answer. */
  degraded?: boolean;
  id?: number;
  email?: string;
  name?: string | null;
  allowed?: boolean;
  is_admin?: boolean;
  tier?: string | null;
  currency?: string;
  username?: string | null;
  beta: {
    current_users: number;
    max_users: number;
    is_full: boolean;
    percent_full: number;
  };
};

/** What /me returns for anonymous viewers — also our fallback when it fails. */
function anonymousViewer(): Viewer {
  return {
    authenticated: false,
    degraded: true,
    beta: { current_users: 0, max_users: 0, is_full: false, percent_full: 0 },
  };
}

/**
 * Guard for pages that BRANCH on auth state: a degraded (outage-fallback)
 * viewer must fail loud into the error boundary — silently treating a
 * logged-in user as a guest (or an admin as a 404) is worse than a
 * retryable error page.
 */
export function assertViewerFresh(viewer: Viewer): void {
  if (viewer.degraded) {
    throw new Error("Could not reach the backend to resolve your session.");
  }
}

/**
 * The acting viewer's profile from the API (anonymous-safe).
 *
 * Degrades gracefully: if /me fails (API down or non-OK), returns the
 * anonymous viewer shape instead of throwing, so public pages render
 * logged-out during an API outage. Pages that require auth still gate
 * correctly, since the fallback is unauthenticated (and not admin/allowed).
 */
export async function getViewer(): Promise<Viewer> {
  try {
    const res = await apiFetch("/me");
    if (!res.ok) return anonymousViewer();
    return await res.json();
  } catch (e) {
    // Never swallow Next's control-flow signals (dynamic-rendering
    // postpone, redirect, notFound) — doing so would let pages prerender
    // statically as logged-out at build time.
    unstable_rethrow(e);
    return anonymousViewer();
  }
}
