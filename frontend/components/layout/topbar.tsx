"use client";

import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/utils";
import { useOverview } from "@/lib/hooks";
import { activeNav } from "./nav";

export function Topbar() {
  const pathname = usePathname();
  const nav = activeNav(pathname);
  const { data: overview } = useOverview();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  });

  const ok = health.data?.status === "ok";

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border/70 bg-card/30 px-6 backdrop-blur">
      <div className="min-w-0">
        <h1 className="truncate text-base font-semibold tracking-tight">{nav.label}</h1>
        <p className="truncate text-xs text-muted-foreground">{nav.desc}</p>
      </div>

      <div className="flex items-center gap-5 text-xs">
        <div className="hidden items-center gap-1.5 sm:flex">
          <span className="text-muted-foreground">Last sync</span>
          <span className="tnum text-foreground/90">{fmtRelative(overview?.last_sync_at)}</span>
        </div>
        <div className="h-5 w-px bg-border" />
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              health.isLoading ? "bg-amber-400" : ok ? "bg-emerald-400" : "bg-red-500"
            }`}
          />
          <span className="text-muted-foreground">
            {health.isLoading ? "Connecting" : ok ? "API connected" : "API offline"}
          </span>
        </div>
      </div>
    </header>
  );
}
