"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { isActivePath } from "@/components/nav-items";

const DOCS_NAV = [
  { href: "/docs/about", label: "About" },
  { href: "/docs/methodology", label: "Methodology" },
  { href: "/docs/assets", label: "Assets" },
  { href: "/docs/glossary", label: "Glossary" },
  { href: "/docs/strategy-api", label: "Strategy API" },
  { href: "/docs/disclaimer", label: "Disclaimer" },
];

/** Vertical docs nav for the desktop layout's secondary sidebar. */
export function DocsSidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-10 flex flex-col gap-2 text-sm">
      {DOCS_NAV.map((item) => {
        const active = isActivePath(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "transition-colors",
              active
                ? "font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Horizontally scrollable pill row, pinned under the mobile top bar. */
export function DocsMobileNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Docs sections"
      className="sticky top-14 z-30 -mb-2 border-b bg-background/95 backdrop-blur md:hidden"
    >
      <div className="flex gap-2 overflow-x-auto px-4 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {DOCS_NAV.map((item) => {
          const active = isActivePath(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "shrink-0 rounded-full border px-3 py-1 text-sm font-medium transition-colors",
                active
                  ? "border-transparent bg-primary text-primary-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
