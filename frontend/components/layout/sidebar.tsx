"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandWordmark } from "@/components/brand";
import { NAV } from "./nav";
import { cn } from "@/lib/utils";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border/70 bg-card/40 md:flex">
      <div className="flex h-16 items-center border-b border-border/70 px-5">
        <Link href="/">
          <BrandWordmark />
        </Link>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        <div className="px-2 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          Modules
        </div>
        {NAV.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  active ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground",
                )}
              />
              <span className="font-medium">{item.label}</span>
              {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border/70 p-4">
        <div className="rounded-lg border border-border/60 bg-background/60 p-3">
          <div className="flex items-center gap-2 text-xs">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-muted-foreground">Model online</span>
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground/70">
            Phases 0–10 complete · EPSG:32161
          </div>
        </div>
      </div>
    </aside>
  );
}
