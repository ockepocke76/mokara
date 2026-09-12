import type { Metadata } from "next";
import Image from "next/image";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-16">
      <div className="flex flex-col items-center gap-2 text-center">
        <Image
          src="/mokara-mark.jpg"
          alt="Mokara"
          width={72}
          height={72}
          priority
        />
        <h1 className="text-3xl font-bold tracking-tight">mokara.ai</h1>
        <p className="text-sm text-muted-foreground">
          Wisdom of the Crowd, Applied
        </p>
      </div>
      <LoginForm
        devLogin={
          // Must match lib/auth.ts's gate: dev login never exists in prod.
          process.env.AUTH_DEV_LOGIN === "1" &&
          process.env.NODE_ENV !== "production"
        }
      />
    </main>
  );
}
