import Image from "next/image";
import Link from "next/link";

import { getViewer } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { MobileNav } from "@/components/mobile-nav";
import { UserMenu } from "@/components/user-menu";

export const NAV = [
  { href: "/dashboard", label: "Home", emoji: "🏠" },
  { href: "/simulate", label: "Run", emoji: "🚀" },
  { href: "/simulations", label: "Sims", emoji: "📊" },
  { href: "/strategies", label: "Strategies", emoji: "📝" },
  { href: "/leaderboard", label: "Leaderboard", emoji: "🏆" },
  { href: "/docs", label: "Docs", emoji: "📚" },
];

export async function SiteHeader() {
  const viewer = await getViewer().catch(() => null);

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-[72px] w-full max-w-6xl items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-3">
          <Image
            src="/mokara-mark.jpg"
            alt="Mokara logo"
            width={48}
            height={48}
            className="rounded-lg"
            priority
          />
          <span className="flex flex-col leading-tight">
            <span className="text-2xl font-semibold tracking-tight">
              mokara.ai
            </span>
            <span className="hidden text-xs text-muted-foreground sm:block">
              Wisdom of the Crowd, Applied
            </span>
          </span>
        </Link>
        <nav className="ml-4 hidden items-center gap-5 text-sm font-medium text-muted-foreground md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="transition-colors hover:text-primary"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
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
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
