import { betterAuth } from "better-auth";
import { Pool } from "pg";

// Hard-gated to non-production: open email+password sign-up with no
// verification would let anyone claim an arbitrary email — and the BFF's
// X-User-Email identity forwarding turns that into full account takeover.
const devLogin =
  process.env.AUTH_DEV_LOGIN === "1" && process.env.NODE_ENV !== "production";
const googleConfigured =
  !!process.env.GOOGLE_CLIENT_ID && !!process.env.GOOGLE_CLIENT_SECRET;

export const auth = betterAuth({
  database: new Pool({ connectionString: process.env.DATABASE_URL }),
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
