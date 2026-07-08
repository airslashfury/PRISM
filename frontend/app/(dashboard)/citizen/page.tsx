"use client";

import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Search } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfidenceChip } from "@/components/provenance-badge";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { useCitizenBarrios, useCivicCard } from "@/lib/hooks";
import { fmtInt, fmtIntTiered, fmtPct, fmtRelative, fmtUsdTiered } from "@/lib/utils";
import { humanizeIntervention, interventionCopy } from "@/lib/interventions";
import type { BarrioOption, CivicConsequence, CivicToday, ServingSubstation } from "@/lib/api";

const FLOOD_COPY: Record<string, string> = {
  minimal: "This area has minimal mapped flood risk — little to none of it falls inside the FEMA 1%-annual-chance (100-year) flood zone.",
  low: "A small part of this area falls inside the FEMA 1%-annual-chance (100-year) flood zone.",
  moderate: "A moderate part of this area falls inside the FEMA 1%-annual-chance (100-year) flood zone.",
  high: "A large part of this area falls inside the FEMA 1%-annual-chance (100-year) flood zone — flooding is a serious risk here in major storms.",
};

export default function CitizenPage() {
  const { data: barrios, isLoading, error } = useCitizenBarrios();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<BarrioOption | null>(null);

  const matches = useMemo(() => {
    if (!barrios || query.trim().length < 2) return [];
    const q = query.trim().toLowerCase();
    return barrios
      .filter((b) => b.name.toLowerCase().includes(q) || (b.municipio ?? "").toLowerCase().includes(q))
      .slice(0, 8);
  }, [barrios, query]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">What about my area?</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Pick your barrio to see what PRISM&apos;s models say about power, flood risk, and emergency
          access where you live — in plain language, with a confidence label on every figure.
        </p>
      </div>

      <InfoPanel
        title="About this card"
        sections={[
          {
            title: "What this is",
            body:
              "A plain-language summary of PRISM's existing models for one barrio: which substation is estimated to serve it and what rides on it, what the island grid is doing right now, what a hurricane or earthquake could mean here, how this area's overall resilience compares to the rest of Puerto Rico, road access to the nearest hospital, flood exposure, and any investments already planned nearby.",
          },
          {
            title: "Honest by construction",
            body:
              "This is informational, not a prediction you should act on. The colored chip on each figure tells you how solid it is — \"Proxy\" means PRISM approximated something (like which substation serves this area) because the real data isn't public. Click a chip for details.",
          },
          {
            title: "Not an emergency notice",
            body:
              "This card does not come from your utility and is not a real-time outage report. For active outages or emergencies, contact LUMA / PREPA and your municipio's emergency management office directly.",
          },
        ]}
      />

      <div className="relative">
        <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 shadow-sm">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelected(null);
            }}
            placeholder="Search for your barrio (e.g. &quot;Playa&quot;, &quot;Bayamón&quot;)"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        {isLoading && <LoadingBlock label="Loading barrios" className="py-2" />}
        {error && <ErrorBlock error={error} className="mt-2" />}
        {!selected && matches.length > 0 && (
          <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover shadow-lg">
            {matches.map((b) => (
              <button
                key={b.entity_id}
                onClick={() => {
                  setSelected(b);
                  setQuery(`${b.name}, ${b.municipio ?? ""}`);
                }}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              >
                <span className="font-medium text-foreground">{b.name}</span>
                <span className="text-xs text-muted-foreground">{b.municipio}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {selected && <CivicCardView barrio={selected} />}
    </div>
  );
}

function CivicCardView({ barrio }: { barrio: BarrioOption }) {
  const { data: card, isLoading, error } = useCivicCard(barrio.entity_id);

  if (isLoading) return <LoadingBlock label="Loading your civic card" className="py-10" />;
  if (error) return <ErrorBlock error={error} />;
  if (!card) return null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {card.barrio_name}
            {card.municipio_name && <span className="text-muted-foreground">, {card.municipio_name} Municipio</span>}
          </CardTitle>
        </CardHeader>
      </Card>

      {card.serving_substation && (
        <PowerCard sub={card.serving_substation} consequence={card.consequence} today={card.today} />
      )}

      {card.community_resilience && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Community resilience</CardTitle>
            <ConfidenceChip tier={card.community_resilience.confidence_tier} />
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              PRISM scores every barrio on a mix of social vulnerability, nearby infrastructure, and planned
              investment. This area ranks <span className="font-semibold text-foreground">higher than {fmtPct(card.community_resilience.percentile, 0)}</span>{" "}
              of Puerto Rico&apos;s barrios on overall resilience
              {card.community_resilience.percentile < 0.34 && " — among the more vulnerable areas in PRISM's model"}
              {card.community_resilience.percentile > 0.66 && " — among the more resilient areas in PRISM's model"}
              .
            </p>
          </CardContent>
        </Card>
      )}

      {card.road_access && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Emergency access</CardTitle>
            <ConfidenceChip tier={card.road_access.confidence_tier} />
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              The nearest hospital, <span className="font-semibold text-foreground">{card.road_access.nearest_hospital}</span>,
              is roughly <span className="font-semibold text-foreground">{card.road_access.travel_time_min.toFixed(0)} minutes</span> away
              by road under normal conditions (assuming a flat 40 km/h average — real travel time varies with traffic
              and road damage).
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Flood risk</CardTitle>
          <ConfidenceChip tier={card.flood_exposure.confidence_tier} />
        </CardHeader>
        <CardContent className="text-sm">
          <p>{FLOOD_COPY[card.flood_exposure.level] ?? FLOOD_COPY.minimal}</p>
        </CardContent>
      </Card>

      {card.planned_nearby.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">What&apos;s planned nearby</CardTitle>
            <ConfidenceChip tier={card.planned_nearby[0].confidence_tier} />
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-muted-foreground">
              From PRISM&apos;s current resilience investment plan, items affecting this area or its substation:
            </p>
            <ul className="space-y-1.5">
              {card.planned_nearby.map((item, i) => {
                const copy = interventionCopy(item.intervention_type);
                return (
                  <li key={i} className="rounded-md border border-border/60 bg-background/40 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground">
                        {humanizeIntervention(item.intervention_type)}
                        {item.entity_name && (
                          <span className="font-normal text-muted-foreground"> — {item.entity_name}</span>
                        )}
                      </span>
                      <span className="shrink-0 font-medium text-foreground">
                        {fmtUsdTiered(item.cost_usd, item.confidence_tier)}
                      </span>
                    </div>
                    {copy && <p className="mt-0.5 text-xs text-muted-foreground">{copy.why}</p>}
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}

      <p className="text-xs text-muted-foreground">
        This card is generated from PRISM&apos;s models for informational purposes only. It is not an official
        notice from LUMA, PREPA, PRASA, or your municipio.
      </p>
    </div>
  );
}

/** "a", "a and b", "a, b and c" — clause list for the power lead sentence. */
function listJoin(nodes: ReactNode[]): ReactNode {
  return nodes.map((n, i) => (
    <Fragment key={i}>
      {i > 0 && (i === nodes.length - 1 ? " and " : ", ")}
      {n}
    </Fragment>
  ));
}

/** Power section: lead with what the substation does, then the live island
 * picture, then the hazard scenarios (Cat-3 + quake) — one short honesty
 * clause at the end instead of a negative lead. */
function PowerCard({
  sub,
  consequence,
  today,
}: {
  sub: ServingSubstation;
  consequence: CivicConsequence | null;
  today: CivicToday | null;
}) {
  const clauses: ReactNode[] = [];
  if (consequence) {
    if (consequence.population_affected > 0) {
      clauses.push(
        <Fragment key="pop">
          about{" "}
          <span className="font-medium text-foreground">
            {fmtIntTiered(consequence.population_affected, consequence.confidence_tier)}
          </span>{" "}
          people
        </Fragment>,
      );
    }
    if (consequence.hospitals > 0) {
      clauses.push(
        <Fragment key="hosp">
          {consequence.hospitals} hospital{consequence.hospitals > 1 ? "s" : ""}
        </Fragment>,
      );
    }
    if (consequence.water_plants > 0) {
      clauses.push(
        <Fragment key="water">
          {consequence.water_plants} water treatment plant{consequence.water_plants > 1 ? "s" : ""}
        </Fragment>,
      );
    }
  }

  const hasToday = today != null && (today.generation_mw != null || today.outage_pct_island != null);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">Power</CardTitle>
        <ConfidenceChip tier={sub.confidence_tier} />
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>
          Your area draws power from the{" "}
          <span className="font-semibold text-foreground">{sub.name}</span> substation
          {clauses.length > 0 ? (
            <> — the same grid section that keeps {listJoin(clauses)} running.</>
          ) : (
            "."
          )}
        </p>

        {hasToday && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">Right now</span>,{" "}
            {today.generation_mw != null && (
              <>
                the island grid is generating{" "}
                <span className="font-medium text-foreground">{fmtInt(today.generation_mw)} MW</span>
                {today.plants_offline != null && today.plants_total != null && (
                  <>
                    {" "}with {today.plants_offline} of {today.plants_total} plants offline
                  </>
                )}{" "}
                <span className="text-xs">(live, PREPA · {fmtRelative(today.generation_as_of)})</span>
                {today.outage_pct_island != null ? "; " : "."}
              </>
            )}
            {today.outage_pct_island != null && (
              <>
                LUMA reports{" "}
                {today.outage_pct_island === 0 ? (
                  "no customers without service island-wide"
                ) : (
                  <>
                    {today.outage_pct_island < 0.1 ? "under 0.1" : today.outage_pct_island.toFixed(1)}% of
                    customers island-wide without service
                  </>
                )}{" "}
                <span className="text-xs">(live · {fmtRelative(today.outage_as_of)})</span>.
              </>
            )}
          </p>
        )}

        {consequence && consequence.population_affected > 0 && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">In a Category 3 hurricane</span>, if that
            substation goes down, PRISM estimates it would cut power to about{" "}
            <span className="font-medium text-foreground">
              {fmtIntTiered(consequence.population_affected, consequence.confidence_tier)}
            </span>{" "}
            people
            {consequence.hospitals > 0 && (
              <>, {consequence.hospitals} hospital{consequence.hospitals > 1 ? "s" : ""}</>
            )}
            {consequence.water_plants > 0 && (
              <>
                , and {consequence.water_plants} water treatment plant
                {consequence.water_plants > 1 ? "s" : ""}
              </>
            )}
            .
          </p>
        )}

        {consequence?.quake_rank != null && consequence.quake_total != null && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">In a major earthquake</span>, this substation
            ranks{" "}
            <span className="font-medium text-foreground">
              #{consequence.quake_rank} of {consequence.quake_total}
            </span>{" "}
            island-wide on PRISM&apos;s risk list — a mix of how close it sits to mapped faults and how
            much depends on it.
          </p>
        )}

        <p className="text-xs text-muted-foreground">
          Estimated from the local grid layout — the chip above says how solid this is.
        </p>
      </CardContent>
    </Card>
  );
}
