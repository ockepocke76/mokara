import { Loader2Icon } from "lucide-react";

/** Root loading state: a centered spinner while server components fetch. */
export default function Loading() {
  return (
    <main
      className="flex flex-1 items-center justify-center px-6 py-24"
      aria-busy
      aria-label="Loading"
    >
      <Loader2Icon className="size-8 animate-spin text-muted-foreground" />
    </main>
  );
}
