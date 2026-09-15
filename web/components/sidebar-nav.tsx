"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { DOCS_NAV, NAV_ITEMS, isActivePath, type NavItem } from "@/components/nav-items";

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
      )}
    >
      <item.icon className="size-4 shrink-0" aria-hidden />
      {item.label}
    </Link>
  );
}

function DocsGroup({ item, pathname }: { item: NavItem; pathname: string }) {
  const inDocs = isActivePath(pathname, item.href);
  // null = follow the route; a chevron click overrides until the next navigation
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setManualOpen(null);
  }
  const open = manualOpen ?? inDocs;

  return (
    <div>
      <div
        className={cn(
          "flex items-center rounded-md pr-1 transition-colors",
          inDocs
            ? "bg-secondary text-foreground"
            : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
        )}
      >
        <Link
          href={item.href}
          aria-current={inDocs ? "page" : undefined}
          className="flex flex-1 items-center gap-3 px-3 py-2 text-sm font-medium"
        >
          <item.icon className="size-4 shrink-0" aria-hidden />
          {item.label}
        </Link>
        <button
          type="button"
          aria-expanded={open}
          aria-label="Toggle docs sections"
          onClick={() => setManualOpen(!open)}
          className="rounded p-1 hover:bg-secondary"
        >
          <ChevronDown
            className={cn("size-4 transition-transform", open && "rotate-180")}
            aria-hidden
          />
        </button>
      </div>
      {open && (
        <div className="mt-1 ml-5 flex flex-col gap-0.5 border-l pl-4">
          {DOCS_NAV.map((sub) => {
            const active = isActivePath(pathname, sub.href);
            return (
              <Link
                key={sub.href}
                href={sub.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2 py-1.5 text-sm transition-colors",
                  active
                    ? "font-medium text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {sub.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 px-3">
      {NAV_ITEMS.map((item) =>
        item.href === "/docs" ? (
          <DocsGroup key={item.href} item={item} pathname={pathname} />
        ) : (
          <NavLink
            key={item.href}
            item={item}
            active={isActivePath(pathname, item.href)}
          />
        ),
      )}
    </nav>
  );
}
