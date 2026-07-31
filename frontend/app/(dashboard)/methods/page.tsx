"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceChip } from "@/components/provenance-badge";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { Segmented } from "@/components/ui/segmented";
import {
  useAssumptionRationale,
  useConfidenceTiers,
  useProvenanceAnomalies,
  useProvenanceAssumptions,
  useProvenanceInventory,
} from "@/lib/hooks";
import { fmtDateTime, fmtInt } from "@/lib/utils";
import type { ConfidenceTierKey, InventoryEntry } from "@/lib/api";
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";

export default function MethodsPage() {
  const t = useMessages().methods;
  const tierLabels = useMessages().confidenceTiers;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const TIER_FILTERS: { value: "all" | ConfidenceTierKey; label: string }[] = [
    { value: "all", label: t.tierFilters.all },
    { value: "authoritative", label: t.tierFilters.authoritative },
    { value: "modeled", label: t.tierFilters.modeled },
    { value: "proxy", label: t.tierFilters.proxy },
    { value: "estimated", label: t.tierFilters.estimated },
  ];
  const { data: tiers, isLoading: tiersLoading, error: tiersError } = useConfidenceTiers();
  const { data: assumptions } = useProvenanceAssumptions();
  const { data: rationale } = useAssumptionRationale();
  const { data: inventory, isLoading: invLoading, error: invError } = useProvenanceInventory();

  const [tierFilter, setTierFilter] = useState<"all" | ConfidenceTierKey>("all");

  const models = useMemo(
    () => (inventory ?? []).filter((e) => e.is_derived),
    [inventory],
  );
  const sources = useMemo(
    () => (inventory ?? []).filter((e) => !e.is_derived),
    [inventory],
  );

  const filteredModels = useMemo(
    () => (tierFilter === "all" ? models : models.filter((m) => m.confidence_tier === tierFilter)),
    [models, tierFilter],
  );

  if (tiersLoading || invLoading) return <LoadingBlock label={t.loadingTrustCenter} className="p-10" />;
  if (tiersError) return <ErrorBlock error={tiersError} className="m-6" />;
  if (invError) return <ErrorBlock error={invError} className="m-6" />;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">{t.trustCenter}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          {t.headerDesc(fmtInt((inventory ?? []).length, tag))}
        </p>
        <Link
          href="/methods/validation"
          className="mt-2 inline-flex items-center text-sm text-primary hover:underline"
        >
          {t.calibrationLink}
        </Link>
        <div>
          <Link
            href="/sync"
            className="mt-1 inline-flex items-center text-sm text-primary hover:underline"
          >
            {t.syncLink}
          </Link>
        </div>
      </div>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(tiers ?? []).map((tier) => (
          <Card key={tier.key}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tier.color ?? undefined }} />
                {tierLabels[tier.key as ConfidenceTierKey]?.label ?? tier.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs leading-relaxed text-muted-foreground">
              {t.tierDescriptions[tier.key] ?? tier.description}
            </CardContent>
          </Card>
        ))}
      </section>

      <InfoPanel
        title={t.aboutTrustCenter}
        defaultOpen
        sections={[
          t.infoSections.whatThisIs,
          t.infoSections.howCalculated,
          t.infoSections.accuracy,
        ]}
      />

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-foreground">{t.models(filteredModels.length)}</h2>
          <Segmented options={TIER_FILTERS} value={tierFilter} onChange={setTierFilter} />
        </div>
        <div className="overflow-x-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t.columns.model}</th>
                <th className="px-3 py-2 font-medium">{t.columns.method}</th>
                <th className="px-3 py-2 font-medium">{t.columns.confidence}</th>
                <th className="px-3 py-2 font-medium">{t.columns.rows}</th>
                <th className="px-3 py-2 font-medium">{t.columns.assumptions}</th>
                <th className="px-3 py-2 font-medium">{t.columns.upgradePath}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {filteredModels.map((m) => (
                <tr key={m.id} className="align-top">
                  <td className="px-3 py-2 font-medium text-foreground">
                    <div>{m.title ?? m.table}</div>
                    <div className="text-[10px] text-muted-foreground">{m.table}</div>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{m.method}</td>
                  <td className="px-3 py-2">
                    <ConfidenceChip tier={m.confidence_tier} detail={m} />
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{m.row_count != null ? fmtInt(m.row_count, tag) : "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{m.assumptions ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{m.upgrade_path ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-foreground">{t.globalAssumptions((assumptions ?? []).length)}</h2>
        <p className="text-xs text-muted-foreground">
          {t.globalAssumptionsDesc}
        </p>
        <div className="overflow-x-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t.columns.assumption}</th>
                <th className="px-3 py-2 font-medium">{t.columns.value}</th>
                <th className="px-3 py-2 font-medium">{t.columns.confidence}</th>
                <th className="px-3 py-2 font-medium">{t.columns.usedBy}</th>
                <th className="px-3 py-2 font-medium">{t.columns.notes}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {(assumptions ?? []).map((a) => (
                <tr key={a.key} className="align-top">
                  <td className="px-3 py-2 font-medium text-foreground">{a.label}</td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {a.value != null ? `${a.value} ${a.unit ?? ""}` : a.unit ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    <ConfidenceChip tier={a.confidence_tier} />
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{a.used_by.join(", ")}</td>
                  <td className="px-3 py-2 text-muted-foreground">{a.assumptions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-foreground">{t.assumptionsAndChoices((rationale ?? []).length)}</h2>
        <p className="text-xs text-muted-foreground">
          {t.assumptionsAndChoicesDesc}
        </p>
        <div className="space-y-2">
          {(rationale ?? []).map((r) => (
            <div key={r.key} className="rounded-lg border border-border/70 p-3 text-xs">
              <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium text-foreground">{r.label}</span>
                <span className="tnum rounded bg-muted/40 px-1.5 py-0.5 font-medium text-foreground">{r.value}</span>
              </div>
              <dl className="grid gap-1.5 sm:grid-cols-3">
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.whyChosen}</dt>
                  <dd className="mt-0.5 text-muted-foreground">{r.why_chosen}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.source}</dt>
                  <dd className="mt-0.5 text-muted-foreground">{r.source}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.whatWouldChangeIt}</dt>
                  <dd className="mt-0.5 text-muted-foreground">{r.what_would_change_it}</dd>
                </div>
              </dl>
            </div>
          ))}
        </div>
      </section>

      <ExcludedData />

      <DataInventory sources={sources} />
    </div>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  high: "bg-red-500/10 text-red-400 border-red-500/30",
  medium: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  low: "bg-muted/40 text-muted-foreground border-border/60",
};

/** F14b — every exclusion PRISM applies to source data, from config/anomalies.yml. */
function ExcludedData() {
  const t = useMessages().methods;
  const { data } = useProvenanceAnomalies();
  const [openId, setOpenId] = useState<string | null>(null);
  const [institutionsOnly, setInstitutionsOnly] = useState(false);

  const rows = useMemo(() => {
    const all = data?.anomalies ?? [];
    return institutionsOnly ? all.filter((a) => a.remediation) : all;
  }, [data, institutionsOnly]);

  if (!data) return null;

  const fixable = (data.anomalies ?? []).filter((a) => a.remediation).length;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">{t.excludedData(data.total)}</h2>
        <Segmented
          options={[
            { value: "all", label: t.allCount(data.total) },
            { value: "institutions", label: t.upstreamDefects(fixable) },
          ]}
          value={institutionsOnly ? "institutions" : "all"}
          onChange={(v) => setInstitutionsOnly(v === "institutions")}
        />
      </div>
      <p className="max-w-3xl text-xs text-muted-foreground">
        {t.excludedDataDesc(fixable, data.total, (data.institutions ?? []).length)}
        <code className="rounded bg-muted/40 px-1 py-0.5">ANOMALIES.md</code>.
      </p>

      <div className="space-y-1.5">
        {rows.map((a) => {
          const open = openId === a.id;
          return (
            <div key={a.id} className="rounded-lg border border-border/70">
              <button
                type="button"
                onClick={() => setOpenId(open ? null : a.id)}
                aria-expanded={open}
                className="flex w-full items-start gap-3 p-3 text-left"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                    SEVERITY_STYLE[a.severity] ?? SEVERITY_STYLE.low
                  }`}
                >
                  {a.severity}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-medium text-foreground">{a.title}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    {a.magnitude.measured}
                  </span>
                </span>
                <span className="shrink-0 text-[10px] text-muted-foreground/70">
                  {open ? t.hide : t.details}
                </span>
              </button>

              {open && (
                <div className="space-y-2.5 border-t border-border/60 px-3 py-3 text-xs">
                  <p className="text-muted-foreground">
                    <span className="text-foreground/90">{t.whatsExcluded}</span>
                    {a.what}
                  </p>
                  <p className="text-muted-foreground">
                    <span className="text-foreground/90">{t.why}</span>
                    {a.why}
                  </p>
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {t.affects}
                    </div>
                    <ul className="mt-1 list-inside list-disc text-muted-foreground">
                      {a.scope.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <p className="text-muted-foreground">
                    <span className="text-foreground/90">
                      {t.whatWouldFixIt}
                      {a.remediation_owner_names?.length
                        ? ` (${a.remediation_owner_names.join(", ")})`
                        : ""}
                      .{" "}
                    </span>
                    {a.remediation ?? t.noUpstreamFix}
                  </p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-[10px] text-muted-foreground/70">
                    <span>
                      {t.sourceLabel}<span className="text-muted-foreground">{a.source}</span>
                    </span>
                    <span>
                      {t.dataset}<code className="text-muted-foreground">{a.dataset}</code>
                    </span>
                    <span>
                      {t.enforcedAt}<code className="text-muted-foreground">{a.where}</code>
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {data.measured_on && (
        <p className="text-[10px] text-muted-foreground/70">
          {t.countsMeasured(data.measured_on)}
        </p>
      )}
    </section>
  );
}

function DataInventory({ sources }: { sources: InventoryEntry[] }) {
  const t = useMessages().methods;
  const { locale } = useLocale();
  const tag = intlTag(locale);
  const [open, setOpen] = useState(false);
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">{t.dataInventory(sources.length)}</h2>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="text-xs text-primary hover:underline"
        >
          {open ? t.hide : t.show}
        </button>
      </div>
      {open && (
        <div className="max-h-[32rem] overflow-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">{t.invColumns.layer}</th>
                <th className="px-3 py-2 font-medium">{t.invColumns.domain}</th>
                <th className="px-3 py-2 font-medium">{t.invColumns.source}</th>
                <th className="px-3 py-2 font-medium">{t.invColumns.vintage}</th>
                <th className="px-3 py-2 font-medium">{t.invColumns.features}</th>
                <th className="px-3 py-2 font-medium">{t.invColumns.license}</th>
                <th className="px-3 py-2 font-medium">{t.invColumns.confidence}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {sources.map((s) => (
                <tr key={s.id}>
                  <td className="px-3 py-2 font-medium text-foreground">{s.title ?? s.id}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.domain ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.source ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.pulled_at ? fmtDateTime(s.pulled_at, tag) : "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.feature_count != null ? fmtInt(s.feature_count, tag) : "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.license ?? "—"}</td>
                  <td className="px-3 py-2">
                    <ConfidenceChip tier={s.confidence_tier} detail={s} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
