import Image from "next/image";
import Link from "next/link";

import type { Viewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { SidebarNav } from "@/components/sidebar-nav";
import { UserMenu } from "@/components/user-menu";

export function Sidebar({ viewer }: { viewer: Viewer | null }) {
  return (
    <aside className="sticky top-0 z-40 hidden h-screen w-64 shrink-0 flex-col border-r bg-background md:flex">
      <Link href="/" className="flex items-center gap-3 px-5 py-5">
        <Image
          src="/mokara-mark.jpg"
          alt="Mokara logo"
          width={40}
          height={40}
          className="rounded-lg"
          priority
        />
        <span className="flex min-w-0 flex-col leading-tight">
          <span className="truncate text-lg font-semibold tracking-tight">
            mokara.ai
          </span>
          <span className="truncate text-[10px] text-muted-foreground">
            Wisdom of the Crowd, Applied
          </span>
        </span>
      </Link>
      <SidebarNav />
      <div className="mt-auto border-t p-3">
        {viewer?.authenticated ? (
          <UserMenu
            name={viewer.name ?? viewer.email ?? "Account"}
            email={viewer.email ?? ""}
            isAdmin={viewer.is_admin ?? false}
            className="w-full"
          />
        ) : (
          <Button asChild size="sm" className="w-full">
            <Link href="/login">Sign in</Link>
          </Button>
        )}
      </div>
    </aside>
  );
}
