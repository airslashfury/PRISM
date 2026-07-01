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
  type LucideIcon,
} from "lucide-react";

export type NavGroup = "Live" | "Explore" | "Decide" | "Reference";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  desc: string;
  group: NavGroup;
}

// Ordered by group: Live, Explore, Decide, Reference. Keep this flat + ordered —
// other consumers (overview module grid, mobile nav, topbar activeNav) rely on it.
export const NAV: NavItem[] = [
  { href: "/", label: "Overview", icon: LayoutDashboard, desc: "What's at stake across Puerto Rico's infrastructure", group: "Live" },
  { href: "/ask", label: "Ask PRISM", icon: Sparkles, desc: "Ask a question in plain language and get an answer with confidence tiers, drawn from PRISM's models", group: "Live" },
  { href: "/citizen", label: "My Area", icon: Home, desc: "Pick your barrio for a plain-language card on power, flood risk, and emergency access", group: "Live" },

  { href: "/resilience", label: "Resilience", icon: Zap, desc: "Which substations cut power to the most hospitals and people when they fail", group: "Explore" },
  { href: "/economy", label: "Economy", icon: Users, desc: "Who's most vulnerable and how much it costs when the lights go out", group: "Explore" },
  { href: "/parcels", label: "Parcels", icon: LandPlot, desc: "Search any of Puerto Rico's 1.5M parcels by catastro, owner, or address — see ownership footprints and the full CRIM record plus what PRISM knows about that ground", group: "Explore" },
  { href: "/trends", label: "Market Trends", icon: TrendingUp, desc: "Where Puerto Rico's property market is moving: hot-spot municipios by sales, the island-wide price trend, and month-over-month parcel changes", group: "Explore" },
  { href: "/sitefinder", label: "Site Finder", icon: Factory, desc: "Where to build: rank industrial-zoned parcels by access to cargo ports, the grid, water, and flood safety", group: "Explore" },

  { href: "/portfolio", label: "Portfolio", icon: Wallet, desc: "The best combination of hardening investments within a fixed budget", group: "Decide" },
  { href: "/playground", label: "Playground", icon: FlaskConical, desc: "Sketch infrastructure onto the live model and see cost, capacity, and resilience impact instantly", group: "Decide" },

  { href: "/methods", label: "Trust Center", icon: ShieldCheck, desc: "Every model and data layer, with its method, confidence tier, and what would upgrade it", group: "Reference" },
  { href: "/corridor", label: "Rail Corridor", icon: Route, desc: "Ranked routes balancing construction cost, terrain, and population served", group: "Reference" },
];

export function activeNav(pathname: string): NavItem {
  // Longest matching prefix wins; "/" only matches exactly.
  const match = NAV.filter((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return match ?? NAV[0];
}
