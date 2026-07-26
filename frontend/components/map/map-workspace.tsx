"use client";

import type { Layer, MapViewState, PickingInfo } from "@deck.gl/core";

import { MapCanvas, type PrismMapApi } from "@/components/map/map-canvas";
import { WorkspaceAside } from "@/components/ui/resizable-pane";

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
  /**
   * Starting width (px) of the sidebar on md+ screens. The user's dragged width
   * (F14a) overrides it once set, so this is a default, not a fixed size.
   * Accepts the pre-F14a Tailwind class form (`"md:w-[360px]"`) for callers that
   * still pass one — the pixel value is parsed out of it.
   */
  sidebarWidth?: number | string;
  /**
   * localStorage key for this route's pane width. Defaults to a shared key, so
   * pass a distinct one per route to have widths remembered independently.
   */
  paneKey?: string;
  /** Pane name used in the resize/collapse aria labels. */
  paneLabel?: string;
}

const DEFAULT_SIDEBAR_WIDTH = 380;

/** Tolerates the legacy `"md:w-[360px]"` prop form alongside a plain number. */
function toPx(value: number | string | undefined): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const m = value.match(/(\d+)px/);
    if (m) return Number(m[1]);
  }
  return DEFAULT_SIDEBAR_WIDTH;
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
  sidebarWidth,
  paneKey = "workspace",
  paneLabel = "panel",
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

      <WorkspaceAside
        storageKey={paneKey}
        defaultWidth={toPx(sidebarWidth)}
        label={paneLabel}
      >
        {sidebar}
      </WorkspaceAside>
    </div>
  );
}
