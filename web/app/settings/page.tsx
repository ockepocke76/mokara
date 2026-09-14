import type { Metadata } from "next";

import { getViewer, assertViewerFresh } from "@/lib/api";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { SignInGate } from "@/components/sign-in-gate";
import { SettingsForm } from "./settings-form";
import { UsernameForm } from "./username-form";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const viewer = await getViewer();
  assertViewerFresh(viewer);

  if (!viewer.authenticated) {
    return <SignInGate title="⚙️ Settings & Profile" />;
  }

  const initial = (viewer.name ?? viewer.email ?? "?")
    .slice(0, 1)
    .toUpperCase();

  return (
    <main className="mx-auto w-full max-w-xl flex-1 px-4 py-10">
      <h1 className="mb-6 text-3xl font-bold tracking-tight">
        ⚙️ Settings &amp; Profile
      </h1>

      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>User Profile</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-4">
            <Avatar className="size-16">
              <AvatarFallback className="bg-primary text-xl text-primary-foreground">
                {initial}
              </AvatarFallback>
            </Avatar>
            <div className="text-sm">
              <p>
                <strong>Name:</strong> {viewer.name ?? "User"}
              </p>
              <p>
                <strong>Email:</strong> {viewer.email}
              </p>
              <p>
                <strong>Username:</strong>{" "}
                {viewer.username ?? (
                  <span className="text-muted-foreground">Not set</span>
                )}{" "}
                <span className="text-xs text-muted-foreground">
                  (public-facing)
                </span>
              </p>
              <p className="text-muted-foreground">
                Plan: {(viewer.tier ?? "Free").toString()}
              </p>
            </div>
          </CardContent>
        </Card>

        <SettingsForm currency={viewer.currency ?? "SEK"} />

        <Card>
          <CardHeader>
            <CardTitle>Public Username</CardTitle>
            <CardDescription>
              Your username appears on leaderboards and published strategies.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <UsernameForm current={viewer.username ?? ""} />
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
