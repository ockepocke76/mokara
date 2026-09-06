import Link from "next/link";
import { headers } from "next/headers";

import { auth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { UserMenu } from "@/components/user-menu";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/simulate", label: "Simulate" },
  { href: "/simulations", label: "My Simulations" },
  { href: "/strategies", label: "Strategies" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/docs", label: "Docs" },
];

export async function SiteHeader() {
  const session = await auth.api.getSession({ headers: await headers() });

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-6 px-4">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Mokara
        </Link>
        <nav className="hidden items-center gap-4 text-sm text-muted-foreground md:flex">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="transition-colors hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto">
          {session?.user ? (
            <UserMenu
              name={session.user.name ?? session.user.email}
              email={session.user.email}
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
