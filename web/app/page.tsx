import { getViewer } from "@/lib/api";

export default async function Home() {
  const viewer = await getViewer();
  const spotsLeft = Math.max(
    0,
    viewer.beta.max_users - viewer.beta.current_users,
  );

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-24 text-center">
      <h1 className="text-5xl font-semibold tracking-tight">Mokara</h1>
      <p className="max-w-md text-lg text-muted-foreground">
        Monte Carlo portfolio simulation. Stress-test investment strategies
        across thousands of possible futures.
      </p>
      {viewer.authenticated ? (
        <p className="text-sm text-muted-foreground">
          Signed in as {viewer.email}
          {viewer.tier ? ` · ${viewer.tier}` : ""}
          {viewer.allowed ? "" : " · beta access pending"}
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          {viewer.beta.is_full
            ? "Early access is currently full."
            : `Early access open — ${spotsLeft} spots remaining.`}
        </p>
      )}
    </main>
  );
}
