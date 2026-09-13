"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { DOCS_NAV, isActivePath } from "@/components/nav-items";

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
