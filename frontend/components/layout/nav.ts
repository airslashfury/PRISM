import {
  LayoutDashboard,
  Zap,
  Wallet,
  Users,
  Route,
  FlaskConical,
  ShieldCheck,
  Home,
  Sparkles,
  Factory,
  LandPlot,
  TrendingUp,
  SlidersHorizontal,
  CloudSun,
  Droplets,
  RadioTower,
  type LucideIcon,
} from "lucide-react";

import { useMessages } from "@/lib/i18n/context";

export type NavGroup = "Live" | "Explore" | "Decide" | "Reference";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  desc: string;
  group: NavGroup;
}

type NavId = "overview" | "ask" | "citizen" | "weather" | "resilience" | "economy" | "water"
  | "telecom" | "parcels" | "trends" | "sitefinder" | "portfolio" | "playground"
  | "assumptions" | "methods" | "corridor";

interface NavMeta {
  id: NavId;
  href: string;
  icon: LucideIcon;
  group: NavGroup;
}

// Ordered by group: Live, Explore, Decide, Reference. Keep this flat + ordered —
// other consumers (overview module grid, mobile nav, topbar activeNav, ⌘K
// palette) rely on it. Label/desc are translated at read time via `useNav()`
// (F12a) — `id` is the key into each locale's `nav.<id>` dictionary entry.
const NAV_META: NavMeta[] = [
  { id: "overview", href: "/", icon: LayoutDashboard, group: "Live" },
  { id: "ask", href: "/ask", icon: Sparkles, group: "Live" },
  { id: "citizen", href: "/citizen", icon: Home, group: "Live" },
  { id: "weather", href: "/weather", icon: CloudSun, group: "Live" },

  { id: "resilience", href: "/resilience", icon: Zap, group: "Explore" },
  { id: "economy", href: "/economy", icon: Users, group: "Explore" },
  { id: "water", href: "/water", icon: Droplets, group: "Explore" },
  { id: "telecom", href: "/telecom", icon: RadioTower, group: "Explore" },
  { id: "parcels", href: "/parcels", icon: LandPlot, group: "Explore" },
  { id: "trends", href: "/trends", icon: TrendingUp, group: "Explore" },
  { id: "sitefinder", href: "/sitefinder", icon: Factory, group: "Explore" },

  { id: "portfolio", href: "/portfolio", icon: Wallet, group: "Decide" },
  { id: "playground", href: "/playground", icon: FlaskConical, group: "Decide" },
  { id: "assumptions", href: "/assumptions", icon: SlidersHorizontal, group: "Decide" },

  { id: "methods", href: "/methods", icon: ShieldCheck, group: "Reference" },
  { id: "corridor", href: "/corridor", icon: Route, group: "Reference" },
];

/** The nav array, translated for the active locale. */
export function useNav(): NavItem[] {
  const t = useMessages().nav;
  return NAV_META.map((m) => ({
    href: m.href,
    icon: m.icon,
    group: m.group,
    label: t[m.id].label,
    desc: t[m.id].desc,
  }));
}

/** Longest matching prefix wins; "/" only matches exactly. Takes the
 * already-resolved (translated) array so it doesn't need its own locale. */
export function activeNav(nav: NavItem[], pathname: string): NavItem {
  const match = nav
    .filter((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return match ?? nav[0];
}
