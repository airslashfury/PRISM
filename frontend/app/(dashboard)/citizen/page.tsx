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
import { useLocale, useMessages } from "@/lib/i18n/context";
import { intlTag } from "@/lib/i18n/locales";
import type { Messages } from "@/lib/i18n/dictionaries/en";
import type { BarrioOption, CivicConsequence, CivicToday, ServingSubstation } from "@/lib/api";

export default function CitizenPage() {
  const { data: barrios, isLoading, error } = useCitizenBarrios();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<BarrioOption | null>(null);
  const t = useMessages().citizen;

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
        <h1 className="text-xl font-semibold text-foreground">{t.title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t.subtitle}</p>
      </div>

      <InfoPanel
        title={t.infoPanel.title}
        sections={[
          { title: t.infoPanel.whatThisIs.title, body: t.infoPanel.whatThisIs.body },
          { title: t.infoPanel.honest.title, body: t.infoPanel.honest.body },
          { title: t.infoPanel.notEmergency.title, body: t.infoPanel.notEmergency.body },
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
            placeholder={t.searchPlaceholder}
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        {isLoading && <LoadingBlock label={t.loadingBarrios} className="py-2" />}
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
  const { locale } = useLocale();
  const t = useMessages().citizen;

  if (isLoading) return <LoadingBlock label={t.loadingCard} className="py-10" />;
  if (error) return <ErrorBlock error={error} />;
  if (!card) return null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {card.barrio_name}
            {card.municipio_name && (
              <span className="text-muted-foreground">, {t.municipioLabel(card.municipio_name)}</span>
            )}
          </CardTitle>
        </CardHeader>
      </Card>

      {card.serving_substation && (
        <PowerCard sub={card.serving_substation} consequence={card.consequence} today={card.today} />
      )}

      {card.community_resilience && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t.cards.communityResilience}</CardTitle>
            <ConfidenceChip tier={card.community_resilience.confidence_tier} />
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              {t.resilienceSentence.lead}{" "}
              <span className="font-semibold text-foreground">
                {t.resilienceSentence.higherThan(fmtPct(card.community_resilience.percentile, 0))}
              </span>{" "}
              {t.resilienceSentence.ofBarrios}
              {card.community_resilience.percentile < 0.34 && t.resilienceSentence.moreVulnerable}
              {card.community_resilience.percentile > 0.66 && t.resilienceSentence.moreResilient}
              .
            </p>
          </CardContent>
        </Card>
      )}

      {card.road_access && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t.cards.emergencyAccess}</CardTitle>
            <ConfidenceChip tier={card.road_access.confidence_tier} />
          </CardHeader>
          <CardContent className="text-sm">
            {card.road_access.nearest_hospital && card.road_access.travel_time_min != null ? (
              <p>
                {t.access.hospitalLead}
                <span className="font-semibold text-foreground">{card.road_access.nearest_hospital}</span>
                {t.access.hospitalMid}
                <span className="font-semibold text-foreground">
                  {card.road_access.travel_time_min.toFixed(0)}{t.access.minutesUnit}
                </span>
                {t.access.hospitalAfter}
              </p>
            ) : (
              // F10c-7: no true hospital is reachable by road from here (a disconnected
              // road-graph component) — fall back to the nearest community clinic rather
              // than silently omitting this card. A clinic is primary care, not an ER.
              <p>
                {t.access.noHospital}{" "}
                {card.road_access.nearest_clinic && card.road_access.clinic_travel_time_min != null ? (
                  <>
                    {t.access.clinicLead}
                    <span className="font-semibold text-foreground">{card.road_access.nearest_clinic}</span>
                    {t.access.clinicMid}
                    <span className="font-semibold text-foreground">
                      {card.road_access.clinic_travel_time_min.toFixed(0)}{t.access.minutesUnit}
                    </span>
                    {t.access.clinicAfter}
                  </>
                ) : (
                  t.access.noClinicEither
                )}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{t.cards.floodRisk}</CardTitle>
          <ConfidenceChip tier={card.flood_exposure.confidence_tier} />
        </CardHeader>
        <CardContent className="text-sm">
          <p>{t.floodCopy[card.flood_exposure.level as keyof typeof t.floodCopy] ?? t.floodCopy.minimal}</p>
        </CardContent>
      </Card>

      {card.planned_nearby.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{t.cards.plannedNearby}</CardTitle>
            <ConfidenceChip tier={card.planned_nearby[0].confidence_tier} />
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-muted-foreground">{t.plannedNearbyIntro}</p>
            <ul className="space-y-1.5">
              {card.planned_nearby.map((item, i) => {
                const copy = interventionCopy(item.intervention_type, locale);
                return (
                  <li key={i} className="rounded-md border border-border/60 bg-background/40 px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-foreground">
                        {humanizeIntervention(item.intervention_type, locale)}
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

      <p className="text-xs text-muted-foreground">{t.disclaimer}</p>
    </div>
  );
}

/** Locale-aware clause list: "a, b and c" (en) / "a, b y c" (es-PR). */
function listJoin(nodes: ReactNode[], t: Messages["citizen"]["power"]): ReactNode {
  return nodes.map((n, i) => (
    <Fragment key={i}>
      {i > 0 && (i === nodes.length - 1 ? t.and : t.listSep)}
      {n}
    </Fragment>
  ));
}

/** Power section: lead with what the substation does, then the live island
 * picture, then the hazard scenarios (Cat-3 + quake) — one short honesty
 * clause at the end instead of a negative lead.
 *
 * The dictionary carries lead/after string *pairs* around each bolded value
 * (substation name, MW figure, population count) rather than a single
 * template function — Spanish reorders some of these relative to English
 * ("la subestación {name}" vs "the {name} substation"), so the split point
 * around the bold span has to move with the locale, not just the words. */
function PowerCard({
  sub,
  consequence,
  today,
}: {
  sub: ServingSubstation;
  consequence: CivicConsequence | null;
  today: CivicToday | null;
}) {
  const { locale } = useLocale();
  const t = useMessages().citizen;
  const p = t.power;
  const intl = intlTag(locale);

  const clauses: ReactNode[] = [];
  if (consequence) {
    if (consequence.population_affected > 0) {
      clauses.push(
        <Fragment key="pop">
          {p.about}{" "}
          <span className="font-medium text-foreground">
            {fmtIntTiered(consequence.population_affected, consequence.confidence_tier, intl)}
          </span>{" "}
          {p.people(consequence.population_affected)}
        </Fragment>,
      );
    }
    if (consequence.hospitals > 0) {
      clauses.push(<Fragment key="hosp">{consequence.hospitals} {p.hospital(consequence.hospitals)}</Fragment>);
    }
    if (consequence.water_plants > 0) {
      clauses.push(<Fragment key="water">{consequence.water_plants} {p.waterPlant(consequence.water_plants)}</Fragment>);
    }
  }

  const hasToday = today != null && (today.generation_mw != null || today.outage_pct_island != null);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{t.cards.power}</CardTitle>
        <ConfidenceChip tier={sub.confidence_tier} />
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>
          {p.drawsFromLead}
          <span className="font-semibold text-foreground">{sub.name}</span>
          {p.drawsFromAfter}
          {clauses.length > 0 ? (
            <>
              {p.keepsRunningLead}
              {listJoin(clauses, p)}
              {p.keepsRunningAfter}
            </>
          ) : (
            p.period
          )}
        </p>

        {hasToday && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">{p.rightNow}</span>,{" "}
            {today.generation_mw != null && (
              <>
                {p.generatingLead}
                <span className="font-medium text-foreground">{fmtInt(today.generation_mw, intl)}{p.mwUnit}</span>
                {today.plants_offline != null && today.plants_total != null &&
                  p.plantsOffline(today.plants_offline, today.plants_total)}{" "}
                <span className="text-xs">{p.live(fmtRelative(today.generation_as_of, intl))}</span>
                {today.outage_pct_island != null ? "; " : "."}
              </>
            )}
            {today.outage_pct_island != null && (
              <>
                {p.lumaReports}{" "}
                {today.outage_pct_island === 0
                  ? p.noOutages
                  : p.pctWithoutService(
                      today.outage_pct_island < 0.1 ? p.underPointOne : today.outage_pct_island.toFixed(1),
                    )}{" "}
                <span className="text-xs">{p.liveDot(fmtRelative(today.outage_as_of, intl))}</span>
              </>
            )}
          </p>
        )}

        {consequence && consequence.population_affected > 0 && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">{p.cat3Lead}</span>
            {p.cat3Mid}{" "}
            {p.about}{" "}
            <span className="font-medium text-foreground">
              {fmtIntTiered(consequence.population_affected, consequence.confidence_tier, intl)}
            </span>{" "}
            {p.people(consequence.population_affected)}
            {consequence.hospitals > 0 && (
              <>{p.listSep}{consequence.hospitals} {p.hospital(consequence.hospitals)}</>
            )}
            {consequence.water_plants > 0 && (
              <>{p.andComma}{consequence.water_plants} {p.waterPlant(consequence.water_plants)}</>
            )}
            .
          </p>
        )}

        {consequence?.quake_rank != null && consequence.quake_total != null && (
          <p className="text-muted-foreground">
            <span className="font-medium text-foreground">{p.quakeLead}</span>
            {p.quakeMid}{" "}
            <span className="font-medium text-foreground">
              {p.quakeRankOf(consequence.quake_rank, consequence.quake_total)}
            </span>{" "}
            {p.quakeAfter}
          </p>
        )}

        <p className="text-xs text-muted-foreground">{p.estimatedNote}</p>
      </CardContent>
    </Card>
  );
}
