"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Search, Sparkles } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceChip } from "@/components/provenance-badge";
import { InfoPanel } from "@/components/info-panel";
import { NarrativePanel } from "@/components/narrative-panel";
import { ErrorBlock } from "@/components/query-state";
import { api, ApiError, type AskResponse, type ConfidenceTierKey } from "@/lib/api";
import { readParam } from "@/lib/url-state";
import { useLocale, useMessages } from "@/lib/i18n/context";

// English-only by design (F12c carve-out, not F12b's job): these are the
// literal text sent verbatim to Ask PRISM's router, which doesn't yet
// understand Spanish queries. Translating the chips would invite a
// Spanish-speaking user to type a Spanish question the backend can't route —
// see aboutSections.languageNote below for the on-screen honesty note this
// implies under es-PR.
const EXAMPLES = [
  "What happens if Palo Seco substation fails?",
  "What about my area in Mayagüez?",
  "What's the top investment in the current portfolio?",
  "Compare rail routes from San Juan to Ponce",
  "Who owns the most land in Bayamón?",
  "What's the largest industrial parcel in Ponce?",
  "Did anything change in the data this week?",
];

interface Turn {
  query: string;
  loading: boolean;
  error?: string;
  response?: AskResponse;
}

const MAP_PAGE_BY_KIND: Record<string, string> = {
  substation: "/resilience",
  barrio: "/citizen",
  municipio: "/citizen",
};

export default function AskPage() {
  const t = useMessages().ask;
  const { locale } = useLocale();
  const [query, setQuery] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);

  // Command-palette handoff (F8 excellence pass): a `?q=` param prefills the
  // input and auto-submits once on mount — a `hasAutoSubmitted` ref (not
  // state) guards it so a later `setQuery` from typing never re-triggers it.
  const hasAutoSubmitted = useRef(false);
  useEffect(() => {
    if (hasAutoSubmitted.current) return;
    hasAutoSubmitted.current = true;
    const q = readParam("q");
    if (q && q.trim()) {
      setQuery(q);
      void submit(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(q: string) {
    const text = q.trim();
    if (!text) return;
    setQuery("");
    setTurns((prev) => [...prev, { query: text, loading: true }]);
    try {
      const response = await api.ask(text);
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, loading: false, response } : t)),
      );
    } catch (err) {
      setTurns((prev) =>
        prev.map((t, i) =>
          i === prev.length - 1
            ? { ...t, loading: false, error: err instanceof ApiError ? err.message : String(err) }
            : t,
        ),
      );
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">{t.title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          {t.subtitle}
        </p>
      </div>

      <InfoPanel
        title={t.whatYouCanAsk}
        defaultOpen
        sections={[
          t.sections.infra,
          t.sections.resilience,
          t.sections.portfolio,
          t.sections.svi,
          t.sections.parcels,
          t.sections.whatsNew,
          t.sections.corridor,
        ]}
      />

      <InfoPanel
        title={t.about}
        sections={[
          t.aboutSections.whatThisIs,
          t.aboutSections.honest,
          t.aboutSections.needsBackend,
          ...(locale === "es-PR" ? [t.aboutSections.languageNote] : []),
        ]}
      />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit(query);
        }}
        className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 shadow-sm"
      >
        <Search className="h-4 w-4 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t.placeholder}
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </form>

      {turns.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => void submit(ex)}
              className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-4">
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <p className="text-sm font-medium text-foreground">{turn.query}</p>
            <Card>
              <CardHeader className="flex flex-row items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <CardTitle className="text-sm font-medium text-muted-foreground">{t.answer}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {turn.loading && <NarrativePanel loading />}
                {turn.error && <ErrorBlock error={new Error(turn.error)} />}
                {turn.response && (
                  <>
                    <NarrativePanel
                      markdown={turn.response.answer_md}
                    />
                    {Object.keys(turn.response.confidence_tiers).length > 0 && (
                      <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-2">
                        {Object.entries(turn.response.confidence_tiers).map(([table, tier]) => (
                          <ConfidenceChip key={table} tier={tier as ConfidenceTierKey} />
                        ))}
                      </div>
                    )}
                    {turn.response.map_points.length > 0 && (
                      <div className="flex flex-wrap gap-2 border-t border-border/60 pt-2">
                        {turn.response.map_points.map((p) => (
                          <Link
                            key={p.entity_id}
                            href={MAP_PAGE_BY_KIND[p.kind ?? ""] ?? "/resilience"}
                            className="rounded-full border border-border bg-background/40 px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                          >
                            {p.name ?? t.entityFallback(p.entity_id)}
                          </Link>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
}
