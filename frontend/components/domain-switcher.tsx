"use client";

import { Zap, Droplets, RadioTower } from "lucide-react";

import { formatViewport } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { useMessages } from "@/lib/i18n/context";

/** Domain switcher (F9b B4): every map page (Power/Water/Telecom) shows the
 *  same switcher, hopping between them carries the current viewport via
 *  `?view=` (already mirrored live by each page's permalink effect) so the
 *  camera doesn't jump on switch. Symmetric — any domain can hand off to any
 *  other, not just Power outward. */
const DOMAIN_META = [
  { id: "power", href: "/resilience", icon: Zap, color: "text-domain-power" },
  { id: "water", href: "/water", icon: Droplets, color: "text-domain-water" },
  { id: "telecom", href: "/telecom", icon: RadioTower, color: "text-domain-telecom" },
] as const;

export function DomainSwitcher({
  className,
  active,
  getView,
}: {
  className?: string;
  active: "power" | "water" | "telecom";
  /** Reads the live camera position at click time — the URL's `?view=` only
   *  updates once the user pans, so this can't just be a plain href. */
  getView: () => { longitude?: number; latitude?: number; zoom?: number };
}) {
  const t = useMessages().domains;
  const DOMAINS = DOMAIN_META.map((d) => ({ ...d, label: t[d.id] }));
  return (
    <div className={cn("inline-flex items-center gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5", className)}>
      {DOMAINS.map((d) => {
        const Icon = d.icon;
        if (d.id === active) {
          return (
            <span
              key={d.id}
              className="flex items-center gap-1.5 rounded-md bg-primary/15 px-3 py-1 text-xs font-medium text-primary shadow-sm"
            >
              <Icon className={cn("h-3 w-3", d.color)} /> {d.label}
            </span>
          );
        }
        return (
          <a
            key={d.id}
            href={d.href}
            onClick={(e) => {
              e.preventDefault();
              const view = formatViewport(getView());
              window.location.href = view ? `${d.href}?view=${view}` : d.href;
            }}
            className="flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <Icon className={cn("h-3 w-3", d.color)} /> {d.label}
          </a>
        );
      })}
    </div>
  );
}
