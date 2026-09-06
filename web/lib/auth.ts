import { betterAuth } from "better-auth";
import { Pool } from "pg";

const devLogin = process.env.AUTH_DEV_LOGIN === "1";
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
