import { Skeleton } from "@/components/ui/skeleton";

/**
 * Dashboard skeleton, mirroring the page's layout (heading, stats, quick
 * actions, recent-simulation cards) while its serial fetches complete.
 */
export default function DashboardLoading() {
  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8" aria-busy>
      <Skeleton className="mb-4 h-9 w-72" />

      <div className="mb-6 grid grid-cols-2 gap-6 sm:max-w-md">
        <div>
          <Skeleton className="mb-2 h-4 w-28" />
          <Skeleton className="h-10 w-16" />
        </div>
        <div>
          <Skeleton className="mb-2 h-4 w-32" />
          <Skeleton className="h-10 w-16" />
        </div>
      </div>

      <section className="mb-8">
        <Skeleton className="mb-3 h-6 w-32" />
        <div className="grid gap-3 sm:grid-cols-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      </section>

      <section>
        <Skeleton className="mb-3 h-6 w-44" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      </section>
    </main>
  );
}
