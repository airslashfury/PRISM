"use client";

import { useMemo, useState } from "react";
import { ScatterplotLayer } from "@deck.gl/layers";
import { MVTLayer } from "@deck.gl/geo-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { GradientLegend } from "@/components/legend";
import { Segmented } from "@/components/ui/segmented";
import { InfoPanel } from "@/components/info-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import { ProvenanceBadge } from "@/components/provenance-badge";
import { useEconomyTracts, useExposure } from "@/lib/hooks";
import { sviColor, type RGB } from "@/lib/colors";
import { fmtInt, fmtIntTiered, fmtNum, fmtPct, fmtUsd, fmtUsdTiered } from "@/lib/utils";
import { tileUrl, type ExposureRow } from "@/lib/api";

const SVI_STOPS: RGB[] = [
  [56, 78, 122],
  [120, 70, 160],
  [200, 60, 130],
  [240, 70, 70],
];

export default function EconomyPage() {
  const { data: tracts, isLoading, error } = useEconomyTracts();
  const { data: exposure } = useExposure(400);
  const [showExposure, setShowExposure] = useState<string>("on");
  const [showFlood, setShowFlood] = useState(false);

  const stats = useMemo(() => {
    const feats = tracts?.features ?? [];
    if (!feats.length) return { n: 0, avg: 0, high: 0 };
    let sum = 0;
    let high = 0;
    for (const f of feats) {
      const s = Number((f.properties as Record<string, unknown>).svi_score ?? 0);
      sum += s;
      if (s >= 0.75) high += 1;
    }
    return { n: feats.length, avg: sum / feats.length, high };
  }, [tracts]);

  const layers = useMemo(() => {
    const ls: Layer[] = [
      new MVTLayer({
        id: "svi-choropleth",
        data: tileUrl("tracts"),
        minZoom: 0,
        maxZoom: 14,
        filled: true,
        stroked: true,
        getFillColor: (f: { properties: Record<string, number> }) =>
          [...sviColor(f.properties.svi_score ?? 0), 155] as [number, number, number, number],
        getLineColor: [148, 163, 184, 35],
        lineWidthMinPixels: 0.5,
        pickable: true,
      }),
    ];
    if (showFlood) {
      ls.push(
        new MVTLayer({
          id: "flood",
          data: tileUrl("flood"),
          minZoom: 0,
          maxZoom: 14,
          filled: true,
          stroked: false,
          getFillColor: [37, 99, 235, 55],
          pickable: false,
        }),
      );
    }
    if (exposure && showExposure === "on") {
      ls.push(
        new ScatterplotLayer<ExposureRow>({
          id: "exposure",
          data: exposure.filter((e) => e.lon != null && e.lat != null),
          getPosition: (d) => [d.lon as number, d.lat as number],
          getRadius: (d) => Math.sqrt(Math.max(d.population_affected ?? 0, 1)) * 16,
          radiusUnits: "meters",
          radiusMinPixels: 2,
          radiusMaxPixels: 30,
          getFillColor: [34, 211, 238, 110],
          getLineColor: [34, 211, 238, 220],
          getLineWidth: 1,
          lineWidthUnits: "pixels",
          stroked: true,
          pickable: true,
        }),
      );
    }
    return ls;
  }, [exposure, showExposure, showFlood]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "exposure") {
      const d = info.object as ExposureRow;
      return tip(
        [
          ["Population", fmtInt(d.population_affected)],
          ["Economic benefit", fmtUsd(d.economic_benefit_usd)],
          ["Property impact", fmtUsd(d.property_impact_usd)],
        ],
        d.entity_name ?? "Substation",
      );
    }
    const f = info.object as { properties: Record<string, number | string> } | undefined;
    if (!f?.properties) return null;
    const p = f.properties;
    return tip(
      [
        ["SVI", fmtNum(Number(p.svi_score), 3)],
        ["Population", fmtInt(Number(p.population))],
        ["Median income", fmtUsd(Number(p.median_income_usd), 0)],
        ["Poverty rate", fmtPct(Number(p.poverty_rate))],
        ["Elderly", fmtPct(Number(p.pct_elderly))],
        ["Disabled", fmtPct(Number(p.pct_disabled))],
      ],
      `Tract ${p.tract_geoid}`,
    );
  };

  const topExposed = exposure?.slice(0, 20) ?? [];

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip}>
          <div className="pointer-events-auto absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Social Vulnerability Index (SVI)
              <ProvenanceBadge table="economy.barrio_economics" />
            </div>
            <div className="mt-0.5 text-[10px] text-muted-foreground/70">
              0 = low vulnerability, 1 = high · weighted: poverty · age · disability · flood · slope
            </div>
            <div className="mt-0.5 flex items-baseline gap-2">
              <span className="text-2xl font-semibold tnum">{fmtNum(stats.avg, 2)}</span>
              <span className="text-xs text-muted-foreground">mean · {fmtInt(stats.n)} tracts</span>
            </div>
            <div className="text-[11px] text-muted-foreground">
              {fmtInt(stats.high)} tracts at SVI ≥ 0.75 (limited self-recovery capacity)
            </div>
          </div>
          <div className="absolute right-4 top-4 w-48 rounded-lg border border-border/70 bg-card/90 p-3 shadow-lg backdrop-blur">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Layers
            </div>
            <Segmented
              className="mb-2 w-full"
              options={[
                { value: "on", label: "Exposure" },
                { value: "off", label: "Hide" },
              ]}
              value={showExposure}
              onChange={setShowExposure}
            />
            <button
              onClick={() => setShowFlood((v) => !v)}
              className="flex w-full items-center gap-2 rounded-md px-1 py-1.5 text-left text-xs hover:bg-accent/40"
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: "rgb(37,99,235)", opacity: showFlood ? 1 : 0.3 }} />
              <span className={showFlood ? "flex-1 text-foreground" : "flex-1 text-muted-foreground"}>
                Flood zones (1%)
              </span>
              <span className={`relative h-4 w-7 rounded-full ${showFlood ? "bg-primary/70" : "bg-muted"}`}>
                <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${showFlood ? "left-3.5" : "left-0.5"}`} />
              </span>
            </button>
          </div>
          <GradientLegend
            className="absolute bottom-6 left-4"
            title="Social vulnerability"
            stops={SVI_STOPS}
            minLabel="Low"
            maxLabel="High"
          />
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[360px] md:shrink-0 md:border-l md:border-t-0">
        <div className="space-y-3 border-b border-border/70 p-4">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              Most exposed substations
              <ProvenanceBadge table="economy.substation_exposure" />
            </h2>
            <p className="text-xs text-muted-foreground">
              Ranked by people who lose power if this substation fails. Circle size on the map
              is proportional to that population. VOLL (Value of Lost Load) converts outage
              exposure to a 30-year net-present-value dollar figure at $2,389/person.
            </p>
          </div>
          <InfoPanel
            sections={[
              {
                title: "What this is",
                body: "Two related layers: the SVI choropleth (per Census tract, how vulnerable residents are to a disruption) and substation exposure (how many people each substation powers, and what an outage there would cost).",
              },
              {
                title: "How it's calculated",
                body: "SVI is a weighted composite, percentile-ranked 0–1 across all 981 tracts: poverty rate (30%), elderly population (15%), disability rate (10%), flood-zone overlap (30%), terrain slope (15%). Exposure traces the knowledge graph downstream from each substation (FEEDS → POWERS) to count the population it serves; VOLL converts that population's expected outage hours into a 30-year NPV dollar figure ($2,389/person) used as the \"economic benefit\" in Portfolio.",
              },
              {
                title: "Data sources & accuracy",
                body: "Poverty, elderly, and disability rates are from Census ACS 5-year 2022 estimates per tract. Flood zones are from the PR government WFS hazard layers; slope is derived from USGS 3DEP elevation. Median income and home value are currently statewide ACS medians applied uniformly, not yet per-tract.",
              },
            ]}
          />
        </div>
        <div className="flex-1 overflow-y-auto">
          {error && <div className="p-4"><ErrorBlock error={error} /></div>}
          {isLoading && <LoadingBlock label="Loading economy" />}
          <ul>
            {topExposed.map((e, i) => (
              <li
                key={e.entity_id}
                className="flex items-center gap-3 border-b border-border/40 px-4 py-2.5"
              >
                <span className="w-5 shrink-0 text-xs tnum text-muted-foreground/60">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{e.entity_name ?? `#${e.entity_id}`}</div>
                  <div className="text-xs text-muted-foreground">
                    {fmtIntTiered(e.population_affected, "proxy")} people · {fmtUsdTiered(e.economic_benefit_usd, "proxy")}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
