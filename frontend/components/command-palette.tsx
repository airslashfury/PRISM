"use client";

/** Global ⌘K / Ctrl+K command palette (F8 excellence pass, chunk D).
 *
 * Opens over any page: jump to a page, run a canned scenario action, or
 * search substations/parcels/owners/Ask PRISM without leaving the keyboard.
 * `shouldFilter={false}` — we own filtering/grouping so remote-search results
 * (parcels/owners) can be interleaved with the static local lists.
 *
 * The trigger button lives in the Topbar, a sibling of where this component
 * mounts (`app/(dashboard)/layout.tsx`) — rather than wrap the app in a new
 * context provider for one boolean, open/close is bridged with a plain
 * `window` CustomEvent (`prism:command-palette:open`). See `openCommandPalette()`.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Search,
  LandPlot,
  Building2,
  Sparkles,
  Loader2,
  type LucideIcon,
} from "lucide-react";

import { NAV } from "@/components/layout/nav";
import { useParcelSearch, useOwnerSearch, useScores } from "@/lib/hooks";
import { fmtNum, fmtUsd, fmtInt, cn } from "@/lib/utils";

const OPEN_EVENT = "prism:command-palette:open";

/** Fire from anywhere (e.g. the Topbar trigger button) to open the palette
 *  without prop-drilling or a context provider. */
export function openCommandPalette() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(OPEN_EVENT));
}

interface StaticAction {
  label: string;
  desc: string;
  href: string;
}

const ACTIONS: StaticAction[] = [
  { label: "Run Cat-3 scenario", desc: "Category 3 hurricane overlay on Resilience", href: "/resilience?scenario=cat3" },
  { label: "Compare combined scenario", desc: "Sea-level rise + hurricane surge overlay", href: "/resilience?scenario=combined" },
  { label: "Track the live storm", desc: "The current NHC advisory cone, if active", href: "/weather?lens=storm" },
  { label: "Open the assumptions lab", desc: "Dial VOLL, hazard, and feeder confidence", href: "/assumptions" },
  { label: "Find industrial sites", desc: "Rank industrial parcels by port/grid/water access", href: "/sitefinder" },
];

const DEBOUNCE_MS = 200;
const MIN_QUERY_LEN = 2;
const ASK_MIN_LEN = 3;

function substr(haystack: string | null | undefined, needle: string): boolean {
  return !!haystack && haystack.toLowerCase().includes(needle);
}

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Bridge: the Topbar trigger (and anything else) opens us via a window event.
  useEffect(() => {
    const onOpenEvent = () => setOpen(true);
    window.addEventListener(OPEN_EVENT, onOpenEvent);
    return () => window.removeEventListener(OPEN_EVENT, onOpenEvent);
  }, []);

  // Global Ctrl+K / Cmd+K to open, Esc to close. Ignore when focus is in a
  // form field elsewhere on the page — unless it's our own palette input.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const isCombo = (e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey);
      if (isCombo) {
        const target = e.target as HTMLElement | null;
        const inOwnInput = target === inputRef.current;
        const inField =
          !inOwnInput &&
          !!target &&
          (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
        if (inField) return;
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // Debounce the query for the remote searches only; local filtering (Pages,
  // Actions, Substations) reacts to every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  // Reset on close so reopening never shows stale results.
  useEffect(() => {
    if (!open) {
      setQuery("");
      setDebounced("");
    } else {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [open]);

  const remoteQuery = debounced.trim().length >= MIN_QUERY_LEN ? debounced.trim() : null;

  // Cat-3 scores fetched once the palette first opens; react-query caches so
  // subsequent opens are instant. Client-filtered by name below.
  const scores = useScores("cat3", 400);
  const parcelSearch = useParcelSearch(remoteQuery);
  const ownerSearch = useOwnerSearch(remoteQuery);

  const navigate = useCallback(
    (href: string) => {
      setOpen(false);
      setQuery("");
      router.push(href);
    },
    [router],
  );

  const q = query.trim().toLowerCase();
  const showAsk = query.trim().length >= ASK_MIN_LEN;

  const pageMatches = q ? NAV.filter((n) => substr(n.label, q) || substr(n.desc, q)) : NAV;
  const actionMatches = q ? ACTIONS.filter((a) => substr(a.label, q) || substr(a.desc, q)) : ACTIONS;
  const substationMatches = q
    ? (scores.data ?? []).filter((s) => substr(s.name, q)).slice(0, 6)
    : [];
  const parcelHits = remoteQuery ? (parcelSearch.data?.parcels ?? []).slice(0, 5) : [];
  const ownerHits = remoteQuery ? (ownerSearch.data?.owners ?? []).slice(0, 5) : [];

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-background/70 pt-[15vh] backdrop-blur-sm animate-in fade-in duration-150 motion-reduce:animate-none"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl rounded-xl border border-border bg-popover shadow-2xl animate-in fade-in zoom-in-95 duration-150 motion-reduce:animate-none"
        onClick={(e) => e.stopPropagation()}
      >
        <Command shouldFilter={false} loop className="outline-none">
          <div className="flex items-center gap-2.5 border-b border-border/70 px-4">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground/70" />
            <Command.Input
              ref={inputRef}
              autoFocus
              value={query}
              onValueChange={setQuery}
              placeholder="Search pages, substations, parcels, owners, or ask a question…"
              className="w-full bg-transparent py-3.5 text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>

          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">
              No results.
            </Command.Empty>

            {pageMatches.length > 0 && (
              <Command.Group
                heading="Pages"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {pageMatches.map((n) => (
                  <PageItem key={n.href} icon={n.icon} label={n.label} desc={n.desc} onSelect={() => navigate(n.href)} />
                ))}
              </Command.Group>
            )}

            {actionMatches.length > 0 && (
              <Command.Group
                heading="Actions"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {actionMatches.map((a) => (
                  <Command.Item
                    key={a.href}
                    value={`action-${a.href}`}
                    onSelect={() => navigate(a.href)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-accent/60"
                  >
                    <Sparkles className="h-4 w-4 shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{a.label}</span>
                      <span className="block truncate text-xs text-muted-foreground">{a.desc}</span>
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {q && (
              <Command.Group
                heading="Substations"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {scores.isLoading && <LoadingRow />}
                {substationMatches.map((s) => (
                  <Command.Item
                    key={`sub-${s.entity_id}`}
                    value={`sub-${s.entity_id}`}
                    onSelect={() => navigate(`/resilience?sel=${s.entity_id}`)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-accent/60"
                  >
                    <span className="min-w-0 flex-1 truncate font-medium">{s.name ?? `Substation ${s.entity_id}`}</span>
                    <span className="shrink-0 text-xs tnum text-muted-foreground">{fmtNum(s.composite_score, 1)}</span>
                  </Command.Item>
                ))}
                {!scores.isLoading && substationMatches.length === 0 && (
                  <div className="px-2.5 py-1.5 text-xs text-muted-foreground/70">No substations match.</div>
                )}
              </Command.Group>
            )}

            {remoteQuery && (
              <Command.Group
                heading="Parcels"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {parcelSearch.isLoading && <LoadingRow />}
                {parcelHits.map((p) => (
                  <Command.Item
                    key={`parcel-${p.num_catastro}`}
                    value={`parcel-${p.num_catastro}`}
                    onSelect={() => navigate(`/parcels?sel=${encodeURIComponent(p.num_catastro)}`)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-accent/60"
                  >
                    <LandPlot className="h-4 w-4 shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{p.owner ?? p.num_catastro}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {p.num_catastro} · {p.municipio ?? ""}
                      </span>
                    </span>
                    {p.totalval != null && (
                      <span className="shrink-0 text-xs tnum text-muted-foreground">{fmtUsd(p.totalval, 0)}</span>
                    )}
                  </Command.Item>
                ))}
                {!parcelSearch.isLoading && parcelHits.length === 0 && (
                  <div className="px-2.5 py-1.5 text-xs text-muted-foreground/70">No parcels match.</div>
                )}
              </Command.Group>
            )}

            {remoteQuery && (
              <Command.Group
                heading="Owners"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {ownerSearch.isLoading && <LoadingRow />}
                {ownerHits.map((o) => (
                  <Command.Item
                    key={`owner-${o.owner_key}`}
                    value={`owner-${o.owner_key}`}
                    onSelect={() => navigate(`/parcels?owner=${encodeURIComponent(o.owner_key)}`)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-accent/60"
                  >
                    <Building2 className="h-4 w-4 shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{o.display_name ?? o.owner_key}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {fmtInt(o.parcel_count)} parcels · {fmtInt(o.municipio_count)} municipios
                      </span>
                    </span>
                  </Command.Item>
                ))}
                {!ownerSearch.isLoading && ownerHits.length === 0 && (
                  <div className="px-2.5 py-1.5 text-xs text-muted-foreground/70">No owners match.</div>
                )}
              </Command.Group>
            )}

            {showAsk && (
              <Command.Group
                heading="Ask PRISM"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                <Command.Item
                  value={`ask-${query}`}
                  onSelect={() => navigate(`/ask?q=${encodeURIComponent(query.trim())}`)}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-accent/60"
                >
                  <Sparkles className="h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1 truncate font-medium">Ask PRISM: &ldquo;{query.trim()}&rdquo;</span>
                </Command.Item>
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}

function PageItem({
  icon: Icon,
  label,
  desc,
  onSelect,
}: {
  icon: LucideIcon;
  label: string;
  desc: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      value={`page-${label}`}
      onSelect={onSelect}
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm data-[selected=true]:bg-accent/60",
      )}
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground/70" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{label}</span>
        <span className="block truncate text-xs text-muted-foreground">{desc}</span>
      </span>
    </Command.Item>
  );
}

function LoadingRow() {
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-muted-foreground/70">
      <Loader2 className="h-3 w-3 animate-spin" /> Searching…
    </div>
  );
}
