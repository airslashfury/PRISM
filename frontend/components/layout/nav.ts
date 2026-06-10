import {
  LayoutDashboard,
  Zap,
  Wallet,
  Users,
  Route,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  desc: string;
}

export const NAV: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard, desc: "What's at stake across Puerto Rico's infrastructure" },
  { href: "/resilience", label: "Resilience", icon: Zap, desc: "Which substations cut power to the most hospitals and people when they fail" },
  { href: "/portfolio", label: "Portfolio", icon: Wallet, desc: "The best combination of hardening investments within a fixed budget" },
  { href: "/economy", label: "Economy", icon: Users, desc: "Who's most vulnerable and how much it costs when the lights go out" },
  { href: "/corridor", label: "Rail Corridor", icon: Route, desc: "Ranked routes balancing construction cost, terrain, and population served" },
  { href: "/sync", label: "Digital Twin", icon: RefreshCw, desc: "Live hazard data — new flood maps auto-trigger a resilience re-score" },
];

export function activeNav(pathname: string): NavItem {
  // Longest matching prefix wins; "/" only matches exactly.
  const match = NAV.filter((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return match ?? NAV[0];
}
