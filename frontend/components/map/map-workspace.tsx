"use client";

import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";

import { MapCanvas, type PrismMapApi } from "@/components/map/map-canvas";
import { cn } from "@/lib/utils";

/**
 * Shared map-left / sidebar-right shell (extracted from resilience/page.tsx
 * and storm/page.tsx, which hand-rolled the same structure). Callers own all
 * state; this component just renders the frame.
 */
export interface MapWorkspaceProps {
  layers: Layer[];
  getTooltip?: (info: PickingInfo) => null | string | { html?: string; text?: string; style?: object };
  onClick?: (info: PickingInfo) => void;
  onHover?: (info: PickingInfo) => void;
  initialViewState?: MapViewState;
  onViewChange?: (viewState: MapViewState) => void;
  /** Called once the map (and its imperative API — easeTo, getTerrainElevation) is ready. */
  onMapReady?: (api: PrismMapApi) => void;
  /** Rendered as MapCanvas children — overlaid on top of the map (banner/legend/layer control). */
  overlays?: React.ReactNode;
  sidebar: React.ReactNode;
  /** Tailwind width class for the sidebar on md+ screens. Defaults to the resilience/storm width. */
  sidebarWidth?: string;
}

export function MapWorkspace({
  layers,
  getTooltip,
  onClick,
  onHover,
  initialViewState,
  onViewChange,
  onMapReady,
  overlays,
  sidebar,
  sidebarWidth = "md:w-[380px]",
}: MapWorkspaceProps) {
  return (
    <div className="flex h-full flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="relative h-[55vh] shrink-0 md:h-full md:flex-1">
        <MapCanvas
          layers={layers}
          getTooltip={getTooltip}
          onClick={onClick}
          onHover={onHover}
          initialViewState={initialViewState}
          onViewChange={onViewChange}
          onMapReady={onMapReady}
        >
          {overlays}
        </MapCanvas>
      </div>

      <aside
        className={cn(
          "flex w-full flex-col border-t border-border/70 bg-card/30 md:shrink-0 md:border-l md:border-t-0",
          sidebarWidth,
        )}
      >
        {sidebar}
      </aside>
    </div>
  );
}
