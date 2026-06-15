"use client";

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { GeoJsonLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import {
  Ban,
  Building2,
  FlaskConical,
  Milestone,
  Plus,
  Route as RoadIcon,
  Sparkles,
  TrainFront,
  Trash2,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { MapCanvas, tip } from "@/components/map/map-canvas";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { InfoPanel } from "@/components/info-panel";
import { NarrativePanel } from "@/components/narrative-panel";
import { LoadingBlock, ErrorBlock } from "@/components/query-state";
import {
  usePlaygroundAssetTypes,
  usePlaygroundGeojson,
  usePlaygroundScenario,
  usePlaygroundScenarios,
  useScores,
} from "@/lib/hooks";
import { api, ApiError, pollJob, type AssetTypeSchema, type WhatIfResult } from "@/lib/api";
import { fmtInt, fmtNum, fmtUsd } from "@/lib/utils";

const ASSET_ICONS: Record<string, LucideIcon> = {
  train: TrainFront,
  road: RoadIcon,
  zap: Zap,
  "building-2": Building2,
  milestone: Milestone,
};

const ASSET_COLORS: Record<string, [number, number, number]> = {
  rail: [56, 189, 248],
  road: [251, 191, 36],
  transmission: [167, 139, 250],
  bridge: [163, 230, 53],
  substation: [244, 114, 182],
};

type DrawMode =
  | { kind: "asset"; assetType: string; geometry: "point" | "line" }
  | { kind: "fail" }
  | { kind: "whatif" }
  | null;

type Coord = [number, number];

/** Generic param form rendered from an AssetTypeSchema's `params` list. */
function ParamForm({
  schema,
  params,
  onChange,
}: {
  schema: AssetTypeSchema;
  params: Record<string, unknown>;
  onChange: (p: Record<string, unknown>) => void;
}) {
  const paramDefs = schema.params ?? [];
  if (!paramDefs.length) return null;
  return (
    <div className="space-y-2">
      {paramDefs.map((p) => {
        const name = String(p.name);
        const type = String(p.type);
        const label = String(p.label ?? name);
        const value = params[name];

        if (type === "enum") {
          const options = (p.options as string[]) ?? [];
          return (
            <div key={name}>
              <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
              <Select value={String(value)} onValueChange={(v) => onChange({ ...params, [name]: v })}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {options.map((o) => (
                    <SelectItem key={o} value={o}>{o}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        }

        if (type === "bool") {
          return (
            <label key={name} className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={Boolean(value)}
                onChange={(e) => onChange({ ...params, [name]: e.target.checked })}
                className="h-3.5 w-3.5 accent-primary"
              />
              {label}
            </label>
          );
        }

        return (
          <div key={name}>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            <input
              type="number"
              value={value == null ? "" : Number(value)}
              onChange={(e) =>
                onChange({
                  ...params,
                  [name]: type === "int" ? parseInt(e.target.value || "0", 10) : parseFloat(e.target.value || "0"),
                })
              }
              className="h-8 w-full rounded-md border border-border bg-card px-2 text-xs"
            />
          </div>
        );
      })}
    </div>
  );
}

function defaultParams(schema: AssetTypeSchema): Record<string, unknown> {
  return Object.fromEntries((schema.params ?? []).map((p) => [String(p.name), p.default]));
}

export default function PlaygroundPage() {
  const queryClient = useQueryClient();

  const { data: scenarios, isLoading: scenariosLoading } = usePlaygroundScenarios();
  const { data: assetTypes } = usePlaygroundAssetTypes();
  const { data: scores } = useScores("cat3", 400);

  const [scenarioId, setScenarioId] = useState<number | null>(null);
  const activeScenarioId = scenarioId ?? scenarios?.[0]?.scenario_id ?? null;

  const { data: detail, isLoading: detailLoading } = usePlaygroundScenario(activeScenarioId);
  const { data: geojson } = usePlaygroundGeojson(activeScenarioId);

  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const [drawMode, setDrawMode] = useState<DrawMode>(null);
  const [drawPoints, setDrawPoints] = useState<Coord[]>([]);
  const [drawParams, setDrawParams] = useState<Record<string, unknown>>({});

  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const [whatifResult, setWhatifResult] = useState<WhatIfResult | null>(null);
  const [whatifError, setWhatifError] = useState<string | null>(null);
  const [whatifLoading, setWhatifLoading] = useState(false);

  const [compareTargetId, setCompareTargetId] = useState<number | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareNarrative, setCompareNarrative] = useState<{
    markdown: string;
    model?: string | null;
    generatedAt?: string | null;
    status?: string | null;
  } | null>(null);

  const invalidateScenario = (id: number) => {
    queryClient.invalidateQueries({ queryKey: ["playgroundScenario", id] });
    queryClient.invalidateQueries({ queryKey: ["playgroundGeojson", id] });
    queryClient.invalidateQueries({ queryKey: ["playgroundScenarios"] });
  };

  const handleCreateScenario = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const s = await api.createPlaygroundScenario({ name: newName.trim() });
      setNewName("");
      setScenarioId(s.scenario_id);
      queryClient.invalidateQueries({ queryKey: ["playgroundScenarios"] });
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteScenario = async (id: number) => {
    await api.deletePlaygroundScenario(id);
    if (activeScenarioId === id) setScenarioId(null);
    queryClient.invalidateQueries({ queryKey: ["playgroundScenarios"] });
  };

  const [committing, setCommitting] = useState(false);
  const [commitResult, setCommitResult] = useState<{ stations_created: number; serves_created: number } | null>(null);
  const [commitError, setCommitError] = useState<string | null>(null);

  const handleCommit = async () => {
    if (!activeScenarioId) return;
    if (!window.confirm(
      "Commit this scenario as a reference plan? This is the one Playground action that " +
      "writes to the live model: any drafted rail lines get permanent station entities " +
      "(+ SERVES links to the nearest barrio) in the knowledge graph.",
    )) return;
    setCommitting(true);
    setCommitError(null);
    try {
      const res = await api.commitPlaygroundScenario(activeScenarioId);
      setCommitResult({ stations_created: res.stations_created, serves_created: res.serves_created });
      invalidateScenario(activeScenarioId);
    } catch (e) {
      setCommitError(e instanceof ApiError ? e.message : "Commit failed");
    } finally {
      setCommitting(false);
    }
  };

  const selectAssetType = (atype: AssetTypeSchema) => {
    setDrawPoints([]);
    setDrawParams(defaultParams(atype));
    setDrawMode({ kind: "asset", assetType: atype.asset_type, geometry: atype.geometry });
  };

  const cancelDraw = () => {
    setDrawMode(null);
    setDrawPoints([]);
  };

  const finishLine = async () => {
    if (!activeScenarioId || drawMode?.kind !== "asset" || drawPoints.length < 2) return;
    await api.addPlaygroundAsset(activeScenarioId, {
      asset_type: drawMode.assetType,
      op: "add",
      geometry: { type: "LineString", coordinates: drawPoints },
      params: drawParams,
    });
    cancelDraw();
    invalidateScenario(activeScenarioId);
  };

  const handleMapClick = async (info: PickingInfo) => {
    const coord = info.coordinate as Coord | undefined;

    if (drawMode?.kind === "fail" || drawMode?.kind === "whatif") {
      const props = (info.object as { properties?: Record<string, unknown> } | undefined)?.properties;
      const eid = props?.entity_id;
      if (typeof eid !== "number") return;

      if (drawMode.kind === "whatif") {
        setWhatifLoading(true);
        setWhatifError(null);
        setWhatifResult(null);
        try {
          const { job_id } = await api.enqueueWhatIf(eid);
          const result = await pollJob<WhatIfResult>(job_id);
          setWhatifResult(result);
        } catch (e) {
          setWhatifError(e instanceof ApiError ? e.message : "What-if check failed");
        } finally {
          setWhatifLoading(false);
        }
        return;
      }

      if (activeScenarioId) {
        await api.addPlaygroundEvent(activeScenarioId, eid);
        invalidateScenario(activeScenarioId);
      }
      return;
    }

    if (!coord || !activeScenarioId || drawMode?.kind !== "asset") return;

    if (drawMode.geometry === "point") {
      await api.addPlaygroundAsset(activeScenarioId, {
        asset_type: drawMode.assetType,
        op: "add",
        geometry: { type: "Point", coordinates: coord },
        params: drawParams,
      });
      cancelDraw();
      invalidateScenario(activeScenarioId);
    } else {
      setDrawPoints((pts) => [...pts, coord]);
    }
  };

  const handleDeleteAsset = async (assetId: number) => {
    if (!activeScenarioId) return;
    await api.deletePlaygroundAsset(activeScenarioId, assetId);
    invalidateScenario(activeScenarioId);
  };

  const handleDeleteEvent = async (eventId: number) => {
    if (!activeScenarioId) return;
    await api.deletePlaygroundEvent(activeScenarioId, eventId);
    invalidateScenario(activeScenarioId);
  };

  const handleEvaluate = async () => {
    if (!activeScenarioId) return;
    setEvaluating(true);
    setEvalError(null);
    try {
      const { job_id } = await api.enqueueEvaluate(activeScenarioId);
      await pollJob(job_id, { timeoutMs: 180_000 });
      invalidateScenario(activeScenarioId);
    } catch (e) {
      setEvalError(e instanceof ApiError ? e.message : "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  };

  const handleCompare = async () => {
    if (!activeScenarioId || !compareTargetId) return;
    setComparing(true);
    setCompareError(null);
    setCompareNarrative(null);
    try {
      const { job_id } = await api.enqueueComparisonNarrative(activeScenarioId, compareTargetId);
      const result = await pollJob<{ narrative_id: number | null; status: string }>(job_id, {
        timeoutMs: 180_000,
      });
      if (!result.narrative_id) {
        setCompareError("Narrative generation failed (no LLM backend available).");
        return;
      }
      const narratives = await api.narratives(50);
      const match = narratives.find((n) => n.narrative_id === result.narrative_id);
      if (match?.text) {
        setCompareNarrative({
          markdown: match.text,
          model: match.model_used,
          generatedAt: match.generated_at,
          status: match.status,
        });
      } else {
        setCompareError("Narrative generated but could not be loaded.");
      }
    } catch (e) {
      setCompareError(e instanceof ApiError ? e.message : "Comparison failed");
    } finally {
      setComparing(false);
    }
  };

  // ── map layers ───────────────────────────────────────────────────────────

  const layers = useMemo(() => {
    const ls: Layer[] = [];

    const failedIds = new Set((detail?.events ?? []).map((e) => e.entity_id));
    const pickSubstations = drawMode?.kind === "fail" || drawMode?.kind === "whatif";

    if (scores) {
      ls.push(
        new ScatterplotLayer({
          id: "playground-substations",
          data: scores,
          getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
          getRadius: (d: { entity_id: number }) => (failedIds.has(d.entity_id) ? 600 : 250),
          radiusUnits: "meters",
          radiusMinPixels: pickSubstations ? 4 : 2,
          getFillColor: (d: { entity_id: number }) =>
            failedIds.has(d.entity_id) ? [239, 68, 68, 220] : [148, 163, 184, pickSubstations ? 200 : 110],
          getLineColor: [15, 23, 42, 200],
          lineWidthMinPixels: 1,
          stroked: pickSubstations,
          pickable: true,
          autoHighlight: pickSubstations,
          highlightColor: [56, 189, 248, 220],
          updateTriggers: {
            getRadius: [detail?.events],
            getFillColor: [detail?.events],
            getFillColor2: [pickSubstations],
          },
        }),
      );
    }

    if (geojson) {
      ls.push(
        new GeoJsonLayer({
          id: "playground-assets",
          data: geojson as never,
          stroked: true,
          filled: true,
          pointType: "circle",
          getPointRadius: 220,
          pointRadiusUnits: "meters",
          pointRadiusMinPixels: 5,
          getFillColor: (f: { properties: Record<string, string> }) => {
            const [r, g, b] = ASSET_COLORS[f.properties.asset_type] ?? [148, 163, 184];
            return [r, g, b, 200];
          },
          getLineColor: (f: { properties: Record<string, string> }) => {
            const [r, g, b] = ASSET_COLORS[f.properties.asset_type] ?? [148, 163, 184];
            return [r, g, b, 255];
          },
          getLineWidth: 5,
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 2,
          pickable: true,
        }),
      );
    }

    if (drawPoints.length) {
      ls.push(
        new PathLayer<{ path: Coord[] }>({
          id: "playground-draw-path",
          data: [{ path: drawPoints }],
          getPath: (d) => d.path as unknown as number[],
          getColor: drawMode?.kind === "asset" ? [...ASSET_COLORS[drawMode.assetType], 255] as [number, number, number, number] : [255, 255, 255, 255],
          getWidth: 4,
          widthUnits: "pixels",
        }),
      );
      ls.push(
        new ScatterplotLayer({
          id: "playground-draw-points",
          data: drawPoints,
          getPosition: (d: Coord) => d,
          getRadius: 5,
          radiusUnits: "pixels",
          getFillColor: [255, 255, 255, 255],
        }),
      );
    }

    return ls;
  }, [scores, geojson, drawPoints, drawMode, detail?.events]);

  const getTooltip = (info: PickingInfo) => {
    if (info.layer?.id === "playground-substations") {
      const d = info.object as { name?: string; composite_score?: number; entity_id?: number } | undefined;
      if (!d) return null;
      return tip(
        [
          ["Composite score", fmtNum(d.composite_score, 2)],
          ["Entity ID", String(d.entity_id)],
        ],
        d.name ?? "Substation",
      );
    }
    if (info.layer?.id === "playground-assets") {
      const p = (info.object as { properties?: Record<string, unknown> })?.properties;
      if (!p) return null;
      return tip(
        [["Op", String(p.op)], ["Asset ID", String(p.asset_id)]],
        String(p.asset_type),
      );
    }
    return null;
  };

  // ── derived scorecard data ──────────────────────────────────────────────

  const result = detail?.latest_result;
  const breakdown = result?.objective_breakdown as
    | { assets?: Array<Record<string, unknown>>; totals?: Record<string, number> }
    | undefined;
  const delta = result?.resilience_delta as
    | {
        baseline_composite_total?: number;
        scenario_composite_total?: number;
        delta?: number;
        touched_substations?: Array<{ entity_id: number; name: string | null; before: number; after: number; interventions: string[] }>;
        downstream_footprint?: { people: number; hospitals: number; water_plants: number; barrios: number };
      }
    | undefined;

  const otherScenarios = (scenarios ?? []).filter((s) => s.scenario_id !== activeScenarioId);

  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas layers={layers} getTooltip={getTooltip} onClick={handleMapClick}>
          <div className="pointer-events-none absolute left-4 top-4 rounded-lg border border-border/70 bg-card/85 px-4 py-3 shadow-lg backdrop-blur">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              <FlaskConical className="h-3.5 w-3.5" /> Playground
            </div>
            <div className="mt-0.5 text-sm">{detail?.name ?? "No scenario selected"}</div>
          </div>

          {drawMode && (
            <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2 rounded-lg border border-primary/30 bg-card/90 px-4 py-2 text-xs shadow-lg backdrop-blur">
              {drawMode.kind === "asset" && drawMode.geometry === "point" && "Click the map to place this asset"}
              {drawMode.kind === "asset" && drawMode.geometry === "line" &&
                `Click to add points (${drawPoints.length} placed) — use "Finish line" when done`}
              {drawMode.kind === "fail" && "Click a substation to add a failure event to this scenario"}
              {drawMode.kind === "whatif" && "Click a substation for an instant downstream-failure check"}
            </div>
          )}

          {whatifLoading && (
            <div className="absolute bottom-6 left-4 rounded-lg border border-border/70 bg-card/90 px-4 py-2 text-xs shadow-lg backdrop-blur">
              Computing downstream footprint…
            </div>
          )}
          {whatifResult && (
            <div className="absolute bottom-6 left-4 max-w-xs rounded-lg border border-border/70 bg-card/90 p-3 text-xs shadow-lg backdrop-blur">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                If entity {whatifResult.entity_id} fails
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <div>People affected: <span className="tnum font-medium">{fmtInt(whatifResult.people)}</span></div>
                <div>Barrios: <span className="tnum font-medium">{whatifResult.barrios}</span></div>
                <div>Hospitals: <span className="tnum font-medium">{whatifResult.hospitals}</span></div>
                <div>Water plants: <span className="tnum font-medium">{whatifResult.water_plants}</span></div>
              </div>
            </div>
          )}
          {whatifError && (
            <div className="absolute bottom-6 left-4 rounded-lg border border-destructive/40 bg-card/90 px-4 py-2 text-xs text-destructive shadow-lg backdrop-blur">
              {whatifError}
            </div>
          )}
        </MapCanvas>
      </div>

      <aside className="flex w-full flex-col border-t border-border/70 bg-card/30 md:w-[420px] md:shrink-0 md:border-l md:border-t-0">
        <div className="border-b border-border/70 p-4">
          <h2 className="text-sm font-semibold">Playground</h2>
          <p className="text-xs text-muted-foreground">
            Sketch infrastructure onto the live model — never touches base data.
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* scenario picker */}
          <div className="space-y-2">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Scenario</div>
            {scenariosLoading && <LoadingBlock label="Loading scenarios" />}
            <div className="flex items-center gap-2">
              <Select
                value={activeScenarioId ? String(activeScenarioId) : ""}
                onValueChange={(v) => setScenarioId(Number(v))}
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="Select a scenario" />
                </SelectTrigger>
                <SelectContent>
                  {scenarios?.map((s) => (
                    <SelectItem key={s.scenario_id} value={String(s.scenario_id)}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {activeScenarioId && (
                <Button size="icon" variant="outline" onClick={() => handleDeleteScenario(activeScenarioId)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New scenario name…"
                className="h-9 flex-1 rounded-md border border-border bg-card px-3 text-sm"
                onKeyDown={(e) => e.key === "Enter" && handleCreateScenario()}
              />
              <Button size="sm" onClick={handleCreateScenario} disabled={creating || !newName.trim()}>
                <Plus className="h-3.5 w-3.5" /> New
              </Button>
            </div>
          </div>

          {!activeScenarioId && (
            <p className="text-xs text-muted-foreground">
              Create a scenario to start sketching infrastructure.
            </p>
          )}

          {activeScenarioId && (
            <>
              {/* asset palette */}
              <div className="space-y-2">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Draw a new asset
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {assetTypes?.map((at) => {
                    const Icon = ASSET_ICONS[at.icon] ?? Building2;
                    const active = drawMode?.kind === "asset" && drawMode.assetType === at.asset_type;
                    return (
                      <button
                        key={at.asset_type}
                        onClick={() => selectAssetType(at)}
                        className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                          active ? "border-primary bg-primary/10 text-primary" : "border-border/60 hover:bg-accent/40"
                        }`}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="capitalize">{at.asset_type}</span>
                      </button>
                    );
                  })}
                </div>

                {drawMode?.kind === "asset" && (
                  <div className="space-y-2 rounded-lg border border-border/60 bg-background/30 p-3">
                    <ParamForm
                      schema={assetTypes!.find((a) => a.asset_type === drawMode.assetType)!}
                      params={drawParams}
                      onChange={setDrawParams}
                    />
                    <div className="flex gap-2">
                      {drawMode.geometry === "line" && (
                        <Button size="sm" onClick={finishLine} disabled={drawPoints.length < 2}>
                          Finish line
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={cancelDraw}>
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>

              {/* what-if / fail */}
              <div className="space-y-2">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Substation failure
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={drawMode?.kind === "whatif" ? "default" : "outline"}
                    onClick={() => setDrawMode((m) => (m?.kind === "whatif" ? null : { kind: "whatif" }))}
                  >
                    Quick check
                  </Button>
                  <Button
                    size="sm"
                    variant={drawMode?.kind === "fail" ? "default" : "outline"}
                    onClick={() => setDrawMode((m) => (m?.kind === "fail" ? null : { kind: "fail" }))}
                  >
                    <Ban className="h-3.5 w-3.5" /> Add to scenario
                  </Button>
                </div>
              </div>

              {/* drafted assets / events */}
              {detail && (detail.assets.length > 0 || detail.events.length > 0) && (
                <div className="space-y-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    In this scenario
                  </div>
                  <div className="space-y-1.5">
                    {detail.assets.map((a) => (
                      <div key={a.asset_id} className="flex items-center justify-between rounded-md border border-border/60 bg-background/30 px-2.5 py-1.5 text-xs">
                        <span className="capitalize">{a.asset_type} · {a.op}</span>
                        <button onClick={() => handleDeleteAsset(a.asset_id)} className="text-muted-foreground hover:text-destructive">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                    {detail.events.map((ev) => (
                      <div key={ev.event_id} className="flex items-center justify-between rounded-md border border-destructive/30 bg-destructive/5 px-2.5 py-1.5 text-xs">
                        <span>Fail entity {ev.entity_id}</span>
                        <button onClick={() => handleDeleteEvent(ev.event_id)} className="text-muted-foreground hover:text-destructive">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* evaluate */}
              <div className="space-y-2">
                <Button onClick={handleEvaluate} disabled={evaluating || detailLoading} className="w-full">
                  {evaluating ? "Evaluating…" : "Evaluate scenario"}
                </Button>
                {evalError && <ErrorBlock error={new Error(evalError)} />}
              </div>

              {/* scorecard */}
              {result && (
                <div className="space-y-3">
                  <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-primary/80">
                      Objective value (lower = better)
                    </div>
                    <div className="mt-1 text-lg font-semibold tnum">
                      {fmtUsd(breakdown?.totals?.objective_value)}
                    </div>
                    <div className="mt-1 text-[11px] text-muted-foreground">{result.headline}</div>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Construction</div>
                      <div className="mt-0.5 text-sm font-semibold tnum">{fmtUsd(breakdown?.totals?.construction_usd)}</div>
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/40 p-2.5">
                      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Maintenance (NPV)</div>
                      <div className="mt-0.5 text-sm font-semibold tnum">{fmtUsd(breakdown?.totals?.maintenance_npv_usd)}</div>
                    </div>
                  </div>

                  {breakdown?.assets?.map((a) => {
                    const fi = a.failure_impact as
                      | { people_affected: number; critical_facilities: number; is_single_point_of_failure: boolean; notes: string }
                      | undefined;
                    return (
                      <div key={String(a.asset_id)} className="rounded-lg border border-border/60 bg-background/30 p-2.5 text-xs">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="font-medium capitalize">{String(a.asset_type)}</span>
                          <Badge variant="muted">{String(a.geometry)}</Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-1 text-muted-foreground">
                          <span>Construction: <span className="tnum text-foreground">{fmtUsd(a.construction_usd as number)}</span></span>
                          <span>Maintenance: <span className="tnum text-foreground">{fmtUsd(a.maintenance_npv_usd as number)}</span></span>
                          {a.total_km != null && <span>Length: <span className="tnum text-foreground">{(a.total_km as number).toFixed(2)} km</span></span>}
                          {a.flood_fraction != null && <span>Flood exposure: <span className="tnum text-foreground">{((a.flood_fraction as number) * 100).toFixed(0)}%</span></span>}
                          {a.capacity != null && <span>Capacity: <span className="tnum text-foreground">{fmtInt(a.capacity as number)}</span></span>}
                        </div>
                        {fi && (
                          <div className="mt-1.5 border-t border-border/50 pt-1.5 text-muted-foreground">
                            <div className="flex items-center justify-between">
                              <span>If this fails: <span className="tnum text-foreground">{fmtInt(fi.people_affected)}</span> people affected</span>
                              {fi.is_single_point_of_failure && <Badge variant="danger">SPOF</Badge>}
                            </div>
                            {fi.notes && <div className="mt-0.5 text-[11px] italic">{fi.notes}</div>}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {delta && (delta.touched_substations?.length ?? 0) > 0 && (
                    <div className="rounded-lg border border-border/60 bg-background/30 p-3">
                      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Resilience delta
                      </div>
                      <div className="mb-2 text-xs">
                        Composite total: <span className="tnum">{delta.baseline_composite_total?.toFixed(2)}</span>
                        {" → "}
                        <span className="tnum">{delta.scenario_composite_total?.toFixed(2)}</span>
                        {" "}
                        <Badge variant={(delta.delta ?? 0) < 0 ? "success" : (delta.delta ?? 0) > 0 ? "danger" : "muted"}>
                          {(delta.delta ?? 0) < 0 ? "improves" : (delta.delta ?? 0) > 0 ? "worsens" : "no change"} {Math.abs(delta.delta ?? 0).toFixed(2)}
                        </Badge>
                      </div>
                      <div className="space-y-1">
                        {delta.touched_substations?.map((t) => (
                          <div key={t.entity_id} className="flex items-center justify-between text-xs">
                            <span className="truncate">{t.name ?? `entity ${t.entity_id}`}</span>
                            <span className="tnum text-muted-foreground">{t.before.toFixed(2)} → {t.after.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                      {delta.downstream_footprint && (
                        <div className="mt-2 grid grid-cols-2 gap-1.5 border-t border-border/50 pt-2 text-xs">
                          <span>People: <span className="tnum font-medium">{fmtInt(delta.downstream_footprint.people)}</span></span>
                          <span>Barrios: <span className="tnum font-medium">{delta.downstream_footprint.barrios}</span></span>
                          <span>Hospitals: <span className="tnum font-medium">{delta.downstream_footprint.hospitals}</span></span>
                          <span>Water plants: <span className="tnum font-medium">{delta.downstream_footprint.water_plants}</span></span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* comparison */}
              {otherScenarios.length > 0 && (
                <div className="space-y-2 rounded-lg border border-border/60 bg-background/30 p-3">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <Sparkles className="h-3.5 w-3.5" /> Compare with another scenario
                  </div>
                  <div className="flex items-center gap-2">
                    <Select
                      value={compareTargetId ? String(compareTargetId) : ""}
                      onValueChange={(v) => setCompareTargetId(Number(v))}
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue placeholder="Choose scenario" />
                      </SelectTrigger>
                      <SelectContent>
                        {otherScenarios.map((s) => (
                          <SelectItem key={s.scenario_id} value={String(s.scenario_id)}>{s.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button size="sm" variant="outline" disabled={!compareTargetId || comparing} onClick={handleCompare}>
                      {comparing ? "Comparing…" : "Compare"}
                    </Button>
                  </div>
                  {compareError && <p className="text-xs text-destructive">{compareError}</p>}
                  {compareNarrative && (
                    <NarrativePanel
                      markdown={compareNarrative.markdown}
                      modelUsed={compareNarrative.model}
                      generatedAt={compareNarrative.generatedAt}
                      status={compareNarrative.status}
                    />
                  )}
                </div>
              )}

              {/* commit as reference */}
              {detail && (
                <div className="space-y-2 rounded-lg border border-border/60 bg-background/30 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      <Milestone className="h-3.5 w-3.5" /> Commit as reference
                    </div>
                    {detail.is_reference && <Badge variant="success">Reference</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Materializes drafted rail lines as permanent station entities (+ SERVES links to
                    the nearest barrio) in the knowledge graph. The only Playground action that
                    writes to the live model.
                  </p>
                  <Button size="sm" variant="outline" disabled={committing} onClick={handleCommit}>
                    {committing ? "Committing…" : detail.is_reference ? "Re-commit reference" : "Commit as reference"}
                  </Button>
                  {commitResult && (
                    <p className="text-xs text-muted-foreground">
                      {commitResult.stations_created} station{commitResult.stations_created === 1 ? "" : "s"} created,{" "}
                      {commitResult.serves_created} SERVES link{commitResult.serves_created === 1 ? "" : "s"} created.
                    </p>
                  )}
                  {commitError && <p className="text-xs text-destructive">{commitError}</p>}
                </div>
              )}

              <InfoPanel
                sections={[
                  {
                    title: "What this is",
                    body: "A sandbox to sketch any infrastructure asset onto the live PRISM model and see its cost, capacity, and resilience impact — without touching the underlying simulation data.",
                  },
                  {
                    title: "How it's calculated",
                    body: "Each asset uses the same construction/maintenance/capacity/failure models as the rest of PRISM (prism/assets/*). Lines are segmented against the corridor cost surface for terrain-aware costing and flood exposure. Substations near a drafted asset, or named in a failure event, get a before/after resilience composite using the Phase-4 intervention-factor model.",
                  },
                  {
                    title: "Data sources & accuracy",
                    body: "Evaluation runs as a background job and reads the same PostGIS tables as the rest of the app (read-only) — scenarios are stored separately and never modify base data. Planning-level estimates only.",
                  },
                ]}
              />
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
