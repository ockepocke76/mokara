"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

const NAV = [
  { href: "/dashboard", label: "🏠 Home" },
  { href: "/simulate", label: "🚀 Run Simulation" },
  { href: "/simulations", label: "📊 My Simulations" },
  { href: "/strategies", label: "📝 Strategies" },
  { href: "/leaderboard", label: "🏆 Leaderboard" },
  { href: "/docs", label: "📚 Docs" },
  { href: "/settings", label: "⚙️ Settings" },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm" className="md:hidden" aria-label="Menu">
          ☰
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-64">
        <SheetHeader>
          <SheetTitle>mokara.ai</SheetTitle>
        </SheetHeader>
        <nav className="mt-2 flex flex-col gap-1 px-2">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className="rounded-md px-3 py-2 text-sm font-medium hover:bg-secondary"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
