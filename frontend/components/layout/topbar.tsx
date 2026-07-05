"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/utils";
import { useOverview } from "@/lib/hooks";
import { activeNav } from "./nav";
import { MobileNav } from "./mobile-nav";
import { openCommandPalette } from "@/components/command-palette";

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
    <header data-chrome className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border/70 bg-card/30 px-4 backdrop-blur md:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <MobileNav />
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold tracking-tight">{nav.label}</h1>
          <p className="truncate text-xs text-muted-foreground">{nav.desc}</p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-5 text-xs">
        <CommandPaletteTrigger />
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

/** ⌘K trigger (F8 excellence pass). Platform sniff for the kbd label is
 *  gated behind `mounted` so the server-rendered markup (always "Ctrl") never
 *  mismatches the client's first paint on a Mac. */
function CommandPaletteTrigger() {
  const [mounted, setMounted] = useState(false);
  const [isMac, setIsMac] = useState(false);

  useEffect(() => {
    setMounted(true);
    setIsMac(/Mac|iPhone|iPad/.test(window.navigator.platform));
  }, []);

  return (
    <button
      type="button"
      onClick={() => openCommandPalette()}
      className="hidden items-center gap-2 rounded-md border border-border/70 bg-background/40 px-2.5 py-1.5 text-muted-foreground transition-colors hover:border-border hover:text-foreground sm:flex"
    >
      <Search className="h-3.5 w-3.5" />
      <span>Search</span>
      <kbd className="ml-1 rounded border border-border/70 bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground/80">
        {mounted && isMac ? "⌘K" : "Ctrl K"}
      </kbd>
    </button>
  );
}
