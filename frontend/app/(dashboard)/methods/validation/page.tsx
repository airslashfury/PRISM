"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceChip } from "@/components/provenance-badge";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useModelCards, useValidationBacktests, useValidationSensitivity } from "@/lib/hooks";
import { fmtDateTime, fmtPct } from "@/lib/utils";
import type { BacktestResult, ModelCard, SensitivityResult, SensitivityStability } from "@/lib/api";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

const STABILITY_STYLE: Record<SensitivityStability, string> = {
  robust: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600",
  sensitive: "border-amber-500/40 bg-amber-500/10 text-amber-600",
  unknown: "border-border/60 bg-background/40 text-muted-foreground",
};

export default function ValidationPage() {
  const t = useMessages().validation;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const { data: backtests, isLoading: btLoading, error: btError } = useValidationBacktests();
  const { data: sensitivity, isLoading: senLoading, error: senError } = useValidationSensitivity();
  const { data: cards, isLoading: cardsLoading, error: cardsError } = useModelCards();

  if (btLoading || senLoading || cardsLoading) return <LoadingBlock label={t.loadingReport} className="p-10" />;
  if (btError) return <ErrorBlock error={btError} className="m-6" />;
  if (senError) return <ErrorBlock error={senError} className="m-6" />;
  if (cardsError) return <ErrorBlock error={cardsError} className="m-6" />;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <div className="text-xs text-muted-foreground">
          <Link href="/methods" className="hover:underline">
            {t.trustCenter}
          </Link>
          {t.breadcrumbSuffix}
        </div>
        <h1 className="mt-1 text-xl font-semibold text-foreground">{t.title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {t.headerDesc}
        </p>
      </div>

      <InfoPanel
        title={t.aboutThisReport}
        defaultOpen
        sections={[
          t.infoSections.whatThisIs,
          t.infoSections.howCalculated,
          t.infoSections.accuracy,
        ]}
      />

      <BacktestsSection results={backtests ?? []} />
      <SensitivitySection results={sensitivity ?? []} />
      <ModelCardsSection cards={cards ?? []} />
    </div>
  );
}

function BacktestsSection({ results }: { results: BacktestResult[] }) {
  const t = useMessages().validation;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-foreground">{t.eventBacktests(results.length)}</h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {results.map((r) => (
          <Card key={r.event_key}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-sm">
                <span>{r.event_name}</span>
                <span className="text-[10px] font-normal text-muted-foreground">
                  {r.event_date ? fmtDateTime(r.event_date, tag).split(",")[0] : "—"}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <Stat label={t.precision} value={fmtPct(r.precision_at_n)} />
                <Stat label={t.recall} value={fmtPct(r.recall)} />
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground">{r.notes}</p>
              {r.misses.length > 0 && (
                <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-amber-600">
                    {t.missed(r.misses.length)}
                  </div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{r.misses.join(", ")}</div>
                </div>
              )}
              <button
                type="button"
                onClick={() => setExpanded((e) => (e === r.event_key ? null : r.event_key))}
                className="text-[11px] text-primary hover:underline"
              >
                {expanded === r.event_key ? t.hideHitsMisses : t.showHitsMisses}
              </button>
              {expanded === r.event_key && <HitsMissesTable result={r} />}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-base font-semibold text-foreground">{value}</div>
    </div>
  );
}

function HitsMissesTable({ result }: { result: BacktestResult }) {
  const t = useMessages().validation;
  return (
    <div className="max-h-64 overflow-auto rounded-md border border-border/60">
      <table className="w-full text-left text-[11px]">
        <thead className="sticky top-0 bg-muted/30 text-muted-foreground">
          <tr>
            <th className="px-2 py-1 font-medium">{t.rank}</th>
            <th className="px-2 py-1 font-medium">{t.substation}</th>
            <th className="px-2 py-1 font-medium">
              {result.validation_type === "spof_corridor" ? t.municipio : t.municipios}
            </th>
            <th className="px-2 py-1 font-medium">{t.hitQuestion}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {result.hits.map((h) => (
            <tr key={h.entity_id}>
              <td className="px-2 py-1 text-muted-foreground">{h.rank}</td>
              <td className="px-2 py-1 font-medium text-foreground">
                {(h.entity_name as string | null) ?? `eid=${h.entity_id}`}
              </td>
              <td className="px-2 py-1 text-muted-foreground">
                {result.validation_type === "spof_corridor"
                  ? (h.municipio as string | null) ?? "—"
                  : ((h.municipios as string[] | undefined) ?? []).join(", ") || "—"}
              </td>
              <td className="px-2 py-1">
                {h.is_hit ? (
                  <span className="text-emerald-600">{t.hit}</span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SensitivitySection({ results }: { results: SensitivityResult[] }) {
  const t = useMessages().validation;
  const grouped = useMemo(() => {
    const out = new Map<string, SensitivityResult[]>();
    for (const r of results) {
      const list = out.get(r.assumption_key) ?? [];
      list.push(r);
      out.set(r.assumption_key, list);
    }
    return out;
  }, [results]);

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-foreground">{t.sensitivitySweeps(results.length)}</h2>
      <div className="overflow-x-auto rounded-lg border border-border/70">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/30 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">{t.assumption}</th>
              <th className="px-3 py-2 font-medium">{t.perturbation}</th>
              <th className="px-3 py-2 font-medium">{t.spearmanRho}</th>
              <th className="px-3 py-2 font-medium">{t.top10Overlap}</th>
              <th className="px-3 py-2 font-medium">{t.stability}</th>
              <th className="px-3 py-2 font-medium">{t.notes}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {[...grouped.entries()].map(([key, rows]) =>
              rows.map((r, i) => (
                <tr key={`${key}-${r.perturbation}`} className="align-top">
                  {i === 0 && (
                    <td className="px-3 py-2 font-medium text-foreground" rowSpan={rows.length}>
                      {key}
                    </td>
                  )}
                  <td className="px-3 py-2 text-muted-foreground">{r.perturbation}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {r.spearman_rho != null ? r.spearman_rho.toFixed(4) : "—"}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {r.top10_overlap != null ? fmtPct(r.top10_overlap, 0) : "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${STABILITY_STYLE[r.stability]}`}
                    >
                      {t.stabilityValue[r.stability] ?? r.stability}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{r.notes}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ModelCardsSection({ cards }: { cards: ModelCard[] }) {
  const t = useMessages().validation;
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-foreground">{t.modelCards(cards.length)}</h2>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {cards.map((c) => (
          <Card key={c.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-sm">
                <span>{c.name}</span>
                {c.provenance && <ConfidenceChip tier={c.provenance.confidence_tier} detail={c.provenance} />}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <p className="leading-relaxed text-muted-foreground">{c.purpose}</p>

              {c.inputs.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t.inputs}</div>
                  <ul className="mt-0.5 list-inside list-disc text-[11px] text-muted-foreground">
                    {c.inputs.map((inp) => (
                      <li key={inp}>{inp}</li>
                    ))}
                  </ul>
                </div>
              )}

              {c.known_limitations.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t.knownLimitations}</div>
                  <ul className="mt-0.5 list-inside list-disc text-[11px] text-muted-foreground">
                    {c.known_limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                </div>
              )}

              {c.backtests.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t.backtests}</div>
                  <ul className="mt-0.5 space-y-0.5 text-[11px] text-muted-foreground">
                    {c.backtests.map((b) => (
                      <li key={b.event_key}>
                        {t.backtestLine(b.event_name, fmtPct(b.precision_at_n), fmtPct(b.recall))}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {c.sensitivity.length > 0 && (
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t.sensitivity}</div>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {c.sensitivity.flatMap((s) =>
                      s.results.map((r) => (
                        <span
                          key={`${s.assumption_key}-${r.perturbation}`}
                          className={`inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${STABILITY_STYLE[r.stability]}`}
                          title={r.notes ?? undefined}
                        >
                          {s.assumption_key} {r.perturbation}: {t.stabilityValue[r.stability] ?? r.stability}
                        </span>
                      )),
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
