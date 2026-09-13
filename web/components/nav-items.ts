import {
  BookOpen,
  ChartColumn,
  Home,
  NotebookPen,
  Rocket,
  Trophy,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  /** Full label, shown in the desktop sidebar. */
  label: string;
  /** Short label, shown under the icon in the mobile bottom bar. */
  short: string;
  icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", short: "Home", icon: Home },
  { href: "/simulate", label: "Run Simulation", short: "Run", icon: Rocket },
  { href: "/simulations", label: "My Simulations", short: "Sims", icon: ChartColumn },
  { href: "/strategies", label: "Strategies", short: "Strategies", icon: NotebookPen },
  { href: "/leaderboard", label: "Leaderboard", short: "Board", icon: Trophy },
  { href: "/docs", label: "Docs", short: "Docs", icon: BookOpen },
];

/** The five primary destinations shown in the mobile bottom bar. */
export const BOTTOM_NAV_ITEMS = NAV_ITEMS.slice(0, 5);

/** Docs sub-pages: fold-out under Docs in the sidebar, pill row on mobile. */
export const DOCS_NAV = [
  { href: "/docs/about", label: "About" },
  { href: "/docs/methodology", label: "Methodology" },
  { href: "/docs/assets", label: "Assets" },
  { href: "/docs/glossary", label: "Glossary" },
  { href: "/docs/strategy-api", label: "Strategy API" },
  { href: "/docs/disclaimer", label: "Disclaimer" },
];

export function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
