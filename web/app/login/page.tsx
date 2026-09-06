import type { Metadata } from "next";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <LoginForm devLogin={process.env.AUTH_DEV_LOGIN === "1"} />
    </main>
  );
}
