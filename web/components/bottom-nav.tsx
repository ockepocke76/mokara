"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { BOTTOM_NAV_ITEMS, isActivePath } from "@/components/nav-items";

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      <div
        className="grid h-tabbar"
        style={{
          gridTemplateColumns: `repeat(${BOTTOM_NAV_ITEMS.length}, minmax(0, 1fr))`,
        }}
      >
        {BOTTOM_NAV_ITEMS.map((item) => {
          const active = isActivePath(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors",
                active ? "text-primary" : "text-muted-foreground",
              )}
            >
              <item.icon
                className="size-5"
                strokeWidth={active ? 2.5 : 2}
                aria-hidden
              />
              {item.short}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
