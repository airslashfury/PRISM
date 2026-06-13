"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import DeckGL from "@deck.gl/react";
import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";
import { Map } from "react-map-gl/maplibre";

// CARTO dark-matter basemap — free, no API key, matches the command-center theme.
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// Esri World Imagery — free raster satellite basemap, no API key (attribution required).
const SATELLITE_TILES = [
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
];
const SATELLITE_ATTRIBUTION = "Esri, Maxar, Earthstar Geographics, and the GIS User Community";

// Terrain tile requests must go through the Next.js proxy (/api/…) so they are
// same-origin — MapLibre loads tiles directly from the browser, bypassing fetch,
// so an absolute API URL would hit CORS from any host other than localhost.
const TILE_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export const PR_VIEW: MapViewState = {
  longitude: -66.45,
  latitude: 18.22,
  zoom: 8.3,
  pitch: 0,
  bearing: 0,
};

const TOOLTIP_STYLE = {
  backgroundColor: "#0b0f17",
  color: "#e2e8f0",
  border: "1px solid #1e293b",
  borderRadius: "8px",
  fontSize: "12px",
  padding: "0",
  boxShadow: "0 12px 40px -8px rgba(0,0,0,.7)",
} as const;

/** Build a styled dark tooltip from label/value rows. */
export function tip(rows: [string, string][], title?: string) {
  const body = rows
    .map(
      ([k, v]) =>
        `<div style="display:flex;gap:16px;justify-content:space-between;padding:1px 0">
           <span style="color:#94a3b8">${k}</span>
           <span style="font-variant-numeric:tabular-nums;color:#e2e8f0">${v}</span>
         </div>`,
    )
    .join("");
  return {
    html: `<div style="padding:8px 10px;min-width:170px">${
      title ? `<div style="font-weight:600;margin-bottom:5px;color:#f1f5f9">${title}</div>` : ""
    }${body}</div>`,
    style: TOOLTIP_STYLE,
  };
}

/** Imperative API handed to the parent once the underlying MapLibre map has loaded. */
export interface PrismMapApi {
  /** Elevation (m) of the rendered terrain mesh at a lng/lat, or null if terrain isn't active/loaded. */
  getTerrainElevation: (lng: number, lat: number) => number | null;
}

export interface PrismMapProps {
  layers: Layer[];
  getTooltip?: (info: PickingInfo) => null | string | { html?: string; text?: string; style?: object };
  onClick?: (info: PickingInfo) => void;
  onHover?: (info: PickingInfo) => void;
  initialViewState?: MapViewState;
  children?: React.ReactNode;
  /** Enable MapLibre 3D terrain from locally-mirrored USGS 3DEP DEM. */
  terrain?: boolean;
  /** Vertical exaggeration applied to the terrain mesh (1-3, default 1.7). */
  exaggeration?: number;
  /** Show Esri World Imagery satellite raster instead of the dark-matter basemap. */
  satellite?: boolean;
  /** When set, drives the camera directly (e.g. a fly-through tour) — applied with no transition. */
  viewStateOverride?: MapViewState | null;
  /** Called once the map (and its API) is ready. */
  onMapReady?: (api: PrismMapApi) => void;
  /** Called once the terrain DEM tiles for the current view have finished loading. */
  onTerrainTilesLoaded?: () => void;
}

export function PrismMap({
  layers,
  getTooltip,
  onClick,
  onHover,
  initialViewState = PR_VIEW,
  children,
  terrain = false,
  exaggeration = 1.7,
  satellite = false,
  viewStateOverride = null,
  onMapReady,
  onTerrainTilesLoaded,
}: PrismMapProps) {
  const mapRef = useRef<any>(null);
  const terrainActive = useRef(false);
  const [viewState, setViewState] = useState<MapViewState>(initialViewState);

  const applyTerrainLayers = useCallback((map: any, exag: number) => {
    if (!map.getSource("prism-dem")) {
      map.addSource("prism-dem", {
        type: "raster-dem",
        tiles: [`${TILE_BASE}/terrain/tiles/{z}/{x}/{y}.png`],
        tileSize: 256,
        minzoom: 4,
        maxzoom: 13,
        attribution: "USGS 3DEP 1/3 arc-sec",
      });
    }
    map.setTerrain({ source: "prism-dem", exaggeration: exag });
    if (!map.getLayer("hillshade")) {
      map.addLayer({
        id: "hillshade",
        type: "hillshade",
        source: "prism-dem",
        paint: {
          "hillshade-exaggeration": 0.25,
          "hillshade-shadow-color": "#060a10",
          "hillshade-highlight-color": "#1e3a5f",
        },
      });
    }
    terrainActive.current = true;
  }, []);

  // Esri World Imagery, inserted just above the style's background layer so the
  // dark-matter vector layers (labels, roads) still render on top.
  const applySatelliteLayer = useCallback((map: any) => {
    if (!map.getSource("esri-satellite")) {
      map.addSource("esri-satellite", {
        type: "raster",
        tiles: SATELLITE_TILES,
        tileSize: 256,
        attribution: SATELLITE_ATTRIBUTION,
      });
    }
    if (!map.getLayer("esri-satellite-layer")) {
      const styleLayers = map.getStyle()?.layers ?? [];
      const beforeId = styleLayers[1]?.id;
      map.addLayer(
        { id: "esri-satellite-layer", type: "raster", source: "esri-satellite" },
        beforeId,
      );
    }
  }, []);

  const setSatelliteVisible = useCallback(
    (map: any, visible: boolean) => {
      if (!map.getLayer("esri-satellite-layer")) {
        if (!visible) return;
        applySatelliteLayer(map);
      }
      map.setLayoutProperty("esri-satellite-layer", "visibility", visible ? "visible" : "none");
      const bg = map.getStyle()?.layers?.[0];
      if (bg?.type === "background") {
        map.setPaintProperty(bg.id, "background-opacity", visible ? 0 : 1);
      }
    },
    [applySatelliteLayer],
  );

  const removeTerrainLayers = useCallback((map: any) => {
    try { map.setTerrain(null); } catch { /* already removed */ }
    try {
      if (map.getLayer("hillshade")) map.removeLayer("hillshade");
    } catch { /* already removed */ }
    terrainActive.current = false;
  }, []);

  // Drive pitch through DeckGL's controlled viewState — not map.flyTo() which DeckGL overrides.
  useEffect(() => {
    const map = mapRef.current?.getMap?.() ?? mapRef.current;
    if (terrain && !terrainActive.current) {
      if (map && typeof map.isStyleLoaded === "function" && map.isStyleLoaded()) {
        applyTerrainLayers(map, exaggeration);
        map.once("idle", () => onTerrainTilesLoaded?.());
      }
      setViewState((vs) => ({
        ...vs,
        pitch: 50,
        transitionDuration: 800,
      }));
    } else if (!terrain && terrainActive.current) {
      if (map && typeof map.isStyleLoaded === "function" && map.isStyleLoaded()) {
        removeTerrainLayers(map);
      }
      setViewState((vs) => ({
        ...vs,
        pitch: 0,
        bearing: 0,
        transitionDuration: 600,
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terrain, applyTerrainLayers, removeTerrainLayers]);

  // Live-update exaggeration without a full terrain teardown/rebuild.
  useEffect(() => {
    const map = mapRef.current?.getMap?.() ?? mapRef.current;
    if (terrainActive.current && map?.getSource?.("prism-dem")) {
      map.setTerrain({ source: "prism-dem", exaggeration });
    }
  }, [exaggeration]);

  // Drive the camera directly when a fly-through tour supplies a frame.
  useEffect(() => {
    if (viewStateOverride) {
      setViewState({ ...viewStateOverride, transitionDuration: 0 });
    }
  }, [viewStateOverride]);

  // Toggle the satellite raster layer.
  useEffect(() => {
    const map = mapRef.current?.getMap?.() ?? mapRef.current;
    if (map && typeof map.isStyleLoaded === "function" && map.isStyleLoaded()) {
      setSatelliteVisible(map, satellite);
    }
  }, [satellite, setSatelliteVisible]);

  const handleMapLoad = useCallback(
    (event: { target: any }) => {
      const map = event.target;
      mapRef.current = { getMap: () => map };
      if (terrain) {
        applyTerrainLayers(map, exaggeration);
        map.once("idle", () => onTerrainTilesLoaded?.());
      }
      if (satellite) setSatelliteVisible(map, true);
      onMapReady?.({
        getTerrainElevation: (lng, lat) => {
          if (!terrainActive.current) return null;
          try {
            const elev = map.queryTerrainElevation([lng, lat]);
            return elev ?? null;
          } catch {
            return null;
          }
        },
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  return (
    <div className="relative h-full w-full overflow-hidden">
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs, interactionState }) => {
          // Only track user gestures — not DeckGL's sync callbacks that fire when
          // we set a new viewState prop, which would instantly override our target pitch.
          if (
            (interactionState as Record<string, boolean>)?.isPanning ||
            (interactionState as Record<string, boolean>)?.isZooming ||
            (interactionState as Record<string, boolean>)?.isRotating
          ) {
            setViewState(vs as MapViewState);
          }
        }}
        controller={{
          doubleClickZoom: true,
          dragRotate: terrain,
          touchRotate: terrain,
        }}
        layers={layers}
        getTooltip={getTooltip as never}
        onClick={onClick}
        onHover={onHover}
        style={{ position: "absolute", inset: "0" }}
      >
        <Map mapStyle={MAP_STYLE} attributionControl={false} reuseMaps onLoad={handleMapLoad} />
      </DeckGL>
      {children}
    </div>
  );
}
