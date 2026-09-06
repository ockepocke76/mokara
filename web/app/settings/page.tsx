import type { Metadata } from "next";
import Link from "next/link";

import { getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SettingsForm } from "./settings-form";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const viewer = await getViewer();

  if (!viewer.authenticated) {
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-xl flex-1 px-4 py-10">
      <h1 className="mb-1 text-3xl font-semibold tracking-tight">Settings</h1>
      <p className="mb-8 text-sm text-muted-foreground">
        {viewer.email}
        {viewer.tier ? ` · ${viewer.tier}` : ""}
      </p>
      <SettingsForm currency={viewer.currency ?? "SEK"} />
    </main>
  );
}
