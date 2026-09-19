import { betterAuth } from "better-auth";
import { Pool } from "pg";

// Hard-gated to non-production: open email+password sign-up with no
// verification would let anyone claim an arbitrary email — and the BFF's
// X-User-Email identity forwarding turns that into full account takeover.
const devLogin =
  process.env.AUTH_DEV_LOGIN === "1" && process.env.NODE_ENV !== "production";
const googleConfigured =
  !!process.env.GOOGLE_CLIENT_ID && !!process.env.GOOGLE_CLIENT_SECRET;

const API_URL = process.env.API_URL ?? "http://localhost:8000";

// Which auth route produced this session — same derivation Better Auth's
// own last-login-method plugin uses.
function loginMethod(path: string | undefined): string {
  if (!path) return "unknown";
  if (path.startsWith("/callback/")) return path.split("/").pop() || "oauth";
  if (path === "/sign-in/email" || path === "/sign-up/email") return "email";
  return "unknown";
}

export const auth = betterAuth({
  database: new Pool({ connectionString: process.env.DATABASE_URL }),
  databaseHooks: {
    session: {
      create: {
        // A new session = a login. Recorded as a product-analytics event on
        // the API. Fire-and-forget with a short timeout: analytics must never
        // delay or block sign-in, even with the API down.
        after: async (session, ctx) => {
          try {
            const user = await ctx?.context.internalAdapter.findUserById(session.userId);
            if (!user?.email) return;
            void fetch(`${API_URL}/me/login-event`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Internal-Secret": process.env.INTERNAL_API_SECRET ?? "",
                "X-User-Email": user.email,
                ...(user.name ? { "X-User-Name": user.name } : {}),
              },
              body: JSON.stringify({ method: loginMethod(ctx?.path) }),
              signal: AbortSignal.timeout(2000),
            })
              .then((res) => {
                if (!res.ok) console.warn(`login-event: API responded ${res.status}`);
              })
              .catch((err) => console.warn("login-event: failed to record", err));
          } catch (err) {
            console.warn("login-event: failed to record", err);
          }
        },
      },
    },
  },
  // Dev-only credentials login so the app is fully testable without Google
  // OAuth credentials. Never enable in production.
  emailAndPassword: {
    enabled: devLogin,
  },
  socialProviders: googleConfigured
    ? {
        google: {
          clientId: process.env.GOOGLE_CLIENT_ID!,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
        },
      }
    : {},
});
