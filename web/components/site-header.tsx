import Image from "next/image";
import Link from "next/link";

import type { Viewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { UserMenu } from "@/components/user-menu";

/** Slim top bar, shown on mobile only — the desktop nav lives in the sidebar. */
export function SiteHeader({ viewer }: { viewer: Viewer | null }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur md:hidden">
      <div className="flex h-topbar items-center gap-3 px-4">
        <Link href="/" className="flex min-w-0 flex-1 items-center gap-2.5">
          <Image
            src="/mokara-mark.jpg"
            alt="Mokara logo"
            width={32}
            height={32}
            className="rounded-md"
          />
          <span className="truncate text-lg font-semibold tracking-tight">
            mokara.ai
          </span>
        </Link>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            href="/docs"
            className="px-1 text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
          >
            Docs
          </Link>
          {viewer?.authenticated ? (
            <UserMenu
              name={viewer.name ?? viewer.email ?? "Account"}
              email={viewer.email ?? ""}
              isAdmin={viewer.is_admin ?? false}
            />
          ) : (
            <Button asChild size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
