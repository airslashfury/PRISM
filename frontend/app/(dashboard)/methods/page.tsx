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

const TIER_FILTERS: { value: "all" | ConfidenceTierKey; label: string }[] = [
  { value: "all", label: "All" },
  { value: "authoritative", label: "Authoritative" },
  { value: "modeled", label: "Modeled" },
  { value: "proxy", label: "Proxy" },
  { value: "estimated", label: "Estimated" },
];

export default function MethodsPage() {
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

  if (tiersLoading || invLoading) return <LoadingBlock label="Loading trust center" className="p-10" />;
  if (tiersError) return <ErrorBlock error={tiersError} className="m-6" />;
  if (invError) return <ErrorBlock error={invError} className="m-6" />;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Trust Center</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
          Every figure PRISM shows is backed by one of the four tiers below. A number&apos;s tier is the
          tier of its <em>weakest</em> required input — a composite score built on a Proxy
          relationship is itself Proxy, even when every other input is Authoritative. This page is
          the live index: every model and every one of PRISM&apos;s {fmtInt((inventory ?? []).length)} mirrored
          data layers, with its method, confidence tier, and what would upgrade it.
        </p>
        <Link
          href="/methods/validation"
          className="mt-2 inline-flex items-center text-sm text-primary hover:underline"
        >
          Calibration &amp; Validation — event backtests, sensitivity sweeps, and per-model cards →
        </Link>
        <div>
          <Link
            href="/sync"
            className="mt-1 inline-flex items-center text-sm text-primary hover:underline"
          >
            Data source registry — sync intervals, last-fetched times, and rescore history →
          </Link>
        </div>
      </div>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(tiers ?? []).map((t) => (
          <Card key={t.key}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: t.color ?? undefined }} />
                {t.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs leading-relaxed text-muted-foreground">{t.description}</CardContent>
          </Card>
        ))}
      </section>

      <InfoPanel
        title="About the Trust Center"
        defaultOpen
        sections={[
          {
            title: "What this is",
            body:
              "A live index of every model PRISM computes and every data layer it mirrors, each stamped with a confidence tier (config/confidence.yml). Click the chip on any figure across the app to see this same information for that specific number.",
          },
          {
            title: "How it's calculated",
            body:
              "Tiers and methods are declared once in config/confidence.yml and merged at request time with catalog/metadata.json (source, vintage, license, row counts). Nothing here is hand-typed prose disconnected from the live catalog.",
          },
          {
            title: "Sources & accuracy",
            body:
              "Authoritative = government/federal data, measured. Modeled = PRISM's computation over Authoritative inputs. Proxy = a spatial/statistical stand-in for a relationship that isn't public (chiefly substation-to-facility feeder assignment). Estimated = a national constant used until a PR-specific figure is available.",
          },
        ]}
      />

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-foreground">Models ({filteredModels.length})</h2>
          <Segmented options={TIER_FILTERS} value={tierFilter} onChange={setTierFilter} />
        </div>
        <div className="overflow-x-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Model</th>
                <th className="px-3 py-2 font-medium">Method</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 font-medium">Rows</th>
                <th className="px-3 py-2 font-medium">Assumptions</th>
                <th className="px-3 py-2 font-medium">Upgrade path</th>
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
                  <td className="px-3 py-2 text-muted-foreground">{m.row_count != null ? fmtInt(m.row_count) : "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{m.assumptions ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{m.upgrade_path ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-foreground">Global assumptions ({(assumptions ?? []).length})</h2>
        <p className="text-xs text-muted-foreground">
          Constants baked into the formulas above — every one of these is a candidate for the
          sensitivity sweep (P2) and the engineer assumptions panel (P3-eng).
        </p>
        <div className="overflow-x-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Assumption</th>
                <th className="px-3 py-2 font-medium">Value</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 font-medium">Used by</th>
                <th className="px-3 py-2 font-medium">Notes</th>
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
        <h2 className="text-sm font-semibold text-foreground">Assumptions & choices ({(rationale ?? []).length})</h2>
        <p className="text-xs text-muted-foreground">
          The handful of constants that most shape what PRISM tells you — why each one was
          chosen, where it comes from, and what would need to change for a better number.
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
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Why chosen</dt>
                  <dd className="mt-0.5 text-muted-foreground">{r.why_chosen}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">Source</dt>
                  <dd className="mt-0.5 text-muted-foreground">{r.source}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">What would change it</dt>
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
        <h2 className="text-sm font-semibold text-foreground">Excluded data ({data.total})</h2>
        <Segmented
          options={[
            { value: "all", label: `All ${data.total}` },
            { value: "institutions", label: `Upstream defects ${fixable}` },
          ]}
          value={institutionsOnly ? "institutions" : "all"}
          onChange={(v) => setInstitutionsOnly(v === "institutions")}
        />
      </div>
      <p className="max-w-3xl text-xs text-muted-foreground">
        PRISM sets some source data aside before it reaches a view or a calculation — a placeholder
        owner name, a sale price of $10<sup>13</sup>, a parcel with no catastro number. Each one is
        listed here with what it affects and how big it is, because a number you can&apos;t audit is
        a number you have to take on faith. {fixable} of the {data.total} are defects in published
        government data rather than choices PRISM made, and each names the body that could close
        it — {(data.institutions ?? []).length} agencies in all. The full register is in{" "}
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
                  {open ? "Hide" : "Details"}
                </span>
              </button>

              {open && (
                <div className="space-y-2.5 border-t border-border/60 px-3 py-3 text-xs">
                  <p className="text-muted-foreground">
                    <span className="text-foreground/90">What&apos;s excluded. </span>
                    {a.what}
                  </p>
                  <p className="text-muted-foreground">
                    <span className="text-foreground/90">Why. </span>
                    {a.why}
                  </p>
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      Affects
                    </div>
                    <ul className="mt-1 list-inside list-disc text-muted-foreground">
                      {a.scope.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <p className="text-muted-foreground">
                    <span className="text-foreground/90">
                      What would fix it
                      {a.remediation_owner_names?.length
                        ? ` (${a.remediation_owner_names.join(", ")})`
                        : ""}
                      .{" "}
                    </span>
                    {a.remediation ?? (
                      <>
                        Nothing upstream — this is a PRISM modelling choice, listed because it is a
                        real exclusion from a calculation.
                      </>
                    )}
                  </p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-[10px] text-muted-foreground/70">
                    <span>
                      Source: <span className="text-muted-foreground">{a.source}</span>
                    </span>
                    <span>
                      Dataset: <code className="text-muted-foreground">{a.dataset}</code>
                    </span>
                    <span>
                      Enforced at: <code className="text-muted-foreground">{a.where}</code>
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
          Counts measured {data.measured_on}. Registry: config/anomalies.yml
        </p>
      )}
    </section>
  );
}

function DataInventory({ sources }: { sources: InventoryEntry[] }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Data inventory ({sources.length} mirrored layers)</h2>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="text-xs text-primary hover:underline"
        >
          {open ? "Hide" : "Show"}
        </button>
      </div>
      {open && (
        <div className="max-h-[32rem] overflow-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-muted/30 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Layer</th>
                <th className="px-3 py-2 font-medium">Domain</th>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Vintage</th>
                <th className="px-3 py-2 font-medium">Features</th>
                <th className="px-3 py-2 font-medium">License</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {sources.map((s) => (
                <tr key={s.id}>
                  <td className="px-3 py-2 font-medium text-foreground">{s.title ?? s.id}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.domain ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.source ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.pulled_at ? fmtDateTime(s.pulled_at) : "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{s.feature_count != null ? fmtInt(s.feature_count) : "—"}</td>
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
