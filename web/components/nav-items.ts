import {
  BookOpen,
  ChartColumn,
  Home,
  NotebookPen,
  Rocket,
  Trophy,
  type LucideIcon,
} from "lucide-react";

export type NavChild = {
  href: string;
  label: string;
};

export type NavItem = {
  href: string;
  /** Full label, shown in the desktop sidebar. */
  label: string;
  /** Short label, shown under the icon in the mobile bottom bar. */
  short: string;
  icon: LucideIcon;
  /** Shown as a tab in the mobile bottom bar. */
  primary?: boolean;
  /** Sub-pages, rendered as a fold-out group in the sidebar. */
  children?: NavChild[];
};

/** Docs sub-pages: fold-out under Docs in the sidebar, pill row on mobile. */
export const DOCS_NAV: NavChild[] = [
  { href: "/docs/about", label: "About" },
  { href: "/docs/methodology", label: "Methodology" },
  { href: "/docs/assets", label: "Assets" },
  { href: "/docs/glossary", label: "Glossary" },
  { href: "/docs/strategy-api", label: "Strategy API" },
  { href: "/docs/disclaimer", label: "Disclaimer" },
];

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", short: "Home", icon: Home, primary: true },
  { href: "/simulate", label: "Run Simulation", short: "Run", icon: Rocket, primary: true },
  { href: "/simulations", label: "My Simulations", short: "Sims", icon: ChartColumn, primary: true },
  { href: "/strategies", label: "Strategies", short: "Strategies", icon: NotebookPen, primary: true },
  { href: "/leaderboard", label: "Leaderboard", short: "Board", icon: Trophy, primary: true },
  { href: "/docs", label: "Docs", short: "Docs", icon: BookOpen, children: DOCS_NAV },
];

/** The primary destinations shown as tabs in the mobile bottom bar. */
export const BOTTOM_NAV_ITEMS = NAV_ITEMS.filter((item) => item.primary);

export function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
