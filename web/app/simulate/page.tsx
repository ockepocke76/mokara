import type { Metadata } from "next";
import Link from "next/link";

import { apiFetch, getViewer } from "@/lib/api";
import type { ParamSchema } from "@/lib/param-types";
import { Button } from "@/components/ui/button";
import { SimulateForm } from "./simulate-form";

export const metadata: Metadata = { title: "Simulate" };

export default async function SimulatePage() {
  const [viewer, schemaRes] = await Promise.all([
    getViewer(),
    apiFetch("/config/params"),
  ]);
  const schema: ParamSchema = await schemaRes.json();

  if (!viewer.authenticated) {
    return (
      <Gate>
        <p className="text-muted-foreground">
          Sign in to run Monte Carlo simulations.
        </p>
        <Button asChild>
          <Link href="/login">Sign in</Link>
        </Button>
      </Gate>
    );
  }

  if (!viewer.allowed) {
    return (
      <Gate>
        <p className="max-w-md text-muted-foreground">
          Early access is currently full. We&apos;ll notify you when new spots
          open — meanwhile, explore the{" "}
          <Link href="/leaderboard" className="underline">
            leaderboard
          </Link>{" "}
          and{" "}
          <Link href="/docs/methodology" className="underline">
            methodology
          </Link>
          .
        </p>
      </Gate>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <h1 className="mb-1 text-3xl font-semibold tracking-tight">
        Run a simulation
      </h1>
      <p className="mb-8 text-sm text-muted-foreground">
        Configure a strategy and asset model, then stress-test it across
        thousands of Monte Carlo scenarios.
      </p>
      <SimulateForm schema={schema} />
    </main>
  );
}

function Gate({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">
        Run a simulation
      </h1>
      {children}
    </main>
  );
}
