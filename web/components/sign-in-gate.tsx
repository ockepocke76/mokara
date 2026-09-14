import Link from "next/link";

import { Button } from "@/components/ui/button";

type SignInGateProps = {
  /** Optional page heading shown above the prompt. */
  title?: string;
  /** Prompt copy under the heading (e.g. "Sign in to see your history."). */
  message?: React.ReactNode;
  /**
   * "sign-in" (default): the sign-in prompt with a login button, for
   * unauthenticated viewers. "beta-full": the early-access-full notice, for
   * authenticated viewers without access (viewer.allowed === false).
   */
  variant?: "sign-in" | "beta-full";
};

/**
 * The one full-page gate shown instead of page content when the viewer is
 * signed out (or, with variant="beta-full", signed in but not yet allowed).
 */
export function SignInGate({
  title,
  message,
  variant = "sign-in",
}: SignInGateProps) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      {title && (
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      )}
      {variant === "beta-full" ? (
        <p className="max-w-md text-muted-foreground">
          {message ?? (
            <>
              Early access is currently full. We&apos;ll notify you when new
              spots open — meanwhile, explore the{" "}
              <Link href="/leaderboard" className="underline">
                leaderboard
              </Link>{" "}
              and{" "}
              <Link href="/docs/methodology" className="underline">
                methodology
              </Link>
              .
            </>
          )}
        </p>
      ) : (
        <>
          {message && <p className="text-muted-foreground">{message}</p>}
          <Button asChild>
            <Link href="/login">Sign in</Link>
          </Button>
        </>
      )}
    </main>
  );
}
