/**
 * BFF helper: server-side fetch to the FastAPI backend.
 *
 * The browser never calls the API directly. Server components and route
 * handlers use apiFetch(), which attaches the internal shared secret and the
 * authenticated viewer's identity claims (from the Better Auth session).
 */
import "server-only";

import { headers } from "next/headers";

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

export type Viewer = {
  authenticated: boolean;
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

/** The acting viewer's profile from the API (anonymous-safe). */
export async function getViewer(): Promise<Viewer> {
  const res = await apiFetch("/me");
  if (!res.ok) {
    throw new Error(`GET /me failed: ${res.status}`);
  }
  return res.json();
}
