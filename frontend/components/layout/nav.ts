import {
  LayoutDashboard,
  Zap,
  Wallet,
  Users,
  Route,
  RefreshCw,
  FlaskConical,
  ShieldCheck,
  Home,
  Sparkles,
  Factory,
  LandPlot,
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
  { href: "/ask", label: "Ask PRISM", icon: Sparkles, desc: "Ask a question in plain language and get an answer with confidence tiers, drawn from PRISM's models" },
  { href: "/citizen", label: "My Area", icon: Home, desc: "Pick your barrio for a plain-language card on power, flood risk, and emergency access" },
  { href: "/resilience", label: "Resilience", icon: Zap, desc: "Which substations cut power to the most hospitals and people when they fail" },
  { href: "/portfolio", label: "Portfolio", icon: Wallet, desc: "The best combination of hardening investments within a fixed budget" },
  { href: "/economy", label: "Economy", icon: Users, desc: "Who's most vulnerable and how much it costs when the lights go out" },
  { href: "/corridor", label: "Rail Corridor", icon: Route, desc: "Ranked routes balancing construction cost, terrain, and population served" },
  { href: "/sitefinder", label: "Site Finder", icon: Factory, desc: "Where to build: rank industrial-zoned parcels by access to cargo ports, the grid, water, and flood safety" },
  { href: "/parcels", label: "Parcels", icon: LandPlot, desc: "Search any of Puerto Rico's 1.5M parcels by catastro, owner, or address — see ownership footprints and the full CRIM record plus what PRISM knows about that ground" },
  { href: "/sync", label: "Digital Twin", icon: RefreshCw, desc: "Live hazard data — new flood maps auto-trigger a resilience re-score" },
  { href: "/playground", label: "Playground", icon: FlaskConical, desc: "Sketch infrastructure onto the live model and see cost, capacity, and resilience impact instantly" },
  { href: "/methods", label: "Trust Center", icon: ShieldCheck, desc: "Every model and data layer, with its method, confidence tier, and what would upgrade it" },
];

export function activeNav(pathname: string): NavItem {
  // Longest matching prefix wins; "/" only matches exactly.
  const match = NAV.filter((n) => (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href)))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return match ?? NAV[0];
}
