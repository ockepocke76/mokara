export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-24 text-center">
      <h1 className="text-5xl font-semibold tracking-tight">Mokara</h1>
      <p className="max-w-md text-lg text-muted-foreground">
        Monte Carlo portfolio simulation. Stress-test investment strategies
        across thousands of possible futures.
      </p>
      <p className="text-sm text-muted-foreground">
        Rebuild in progress — see PORT_PLAN.md
      </p>
    </main>
  );
}
