import type { Metadata } from "next";

import { apiFetch, getViewer } from "@/lib/api";
import type { ParamSchema } from "@/lib/param-types";
import { SignInGate } from "@/components/sign-in-gate";
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
      <SignInGate
        title="Run a simulation"
        message="Sign in to run Monte Carlo simulations."
      />
    );
  }

  if (!viewer.allowed) {
    return <SignInGate title="Run a simulation" variant="beta-full" />;
  }

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-10">
      <h1 className="mb-1 text-3xl font-bold tracking-tight">
        🚀 Run Simulation
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Configure and run a simulation for your financial strategy.
      </p>
      <SimulateForm schema={schema} currency={viewer.currency} />
    </main>
  );
}
