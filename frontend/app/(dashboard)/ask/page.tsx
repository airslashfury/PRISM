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
        <h1 className="text-xl font-semibold text-foreground">Ask PRISM</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Ask a question about Puerto Rico&apos;s infrastructure in plain language. PRISM answers using
          its own models — with the confidence tier of every figure it cites — never an invented number.
        </p>
      </div>

      <InfoPanel
        title="What you can ask"
        defaultOpen
        sections={[
          {
            title: "Infrastructure & failures",
            body: "“What happens if Palo Seco substation fails?” — what breaks downstream.",
          },
          {
            title: "Resilience rankings",
            body: "“What are the highest-risk substations under a Cat-3 hurricane?”",
          },
          {
            title: "The investment plan",
            body: "“What's the top investment in the current portfolio?”",
          },
          {
            title: "Community vulnerability (SVI)",
            body: "“How vulnerable is Comerío to a disruption?”",
          },
          {
            title: "Parcels, owners & addresses (CRIM)",
            body: "“Who owns the most land in Bayamón?”",
          },
          {
            title: "What changed recently",
            body: "“Did anything change in the data this week?”",
          },
          {
            title: "Rail corridors",
            body: "“Compare rail routes from San Juan to Ponce.”",
          },
        ]}
      />

      <InfoPanel
        title="About Ask PRISM"
        sections={[
          {
            title: "What this is",
            body:
              "A natural-language front end over a handful of PRISM's existing read-only models: entity lookup, downstream-failure consequences, top resilience risks, the investment portfolio, rail corridor comparisons, barrio social-vulnerability/civic data, CRIM owner and parcel lookups, and the what-changed feed. A small model routes your question to one of those models; another model writes up the answer.",
          },
          {
            title: "Honest by construction",
            body:
              "Every answer either cites the confidence tier(s) of the data it used, or says plainly that it couldn't find a matching model. It never makes up a number that didn't come from the live model.",
          },
          {
            title: "Needs an AI backend",
            body:
              "If no LLM backend is configured (ANTHROPIC_API_KEY or a local Ollama via PRISM_LLM_BACKEND), Ask PRISM will say so rather than failing silently.",
          },
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
          placeholder="Ask about a substation, an owner, a parcel, the portfolio, or what changed recently..."
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
                <CardTitle className="text-sm font-medium text-muted-foreground">Answer</CardTitle>
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
                            {p.name ?? `entity ${p.entity_id}`}
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
