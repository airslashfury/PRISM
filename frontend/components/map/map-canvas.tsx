"use client";

import dynamic from "next/dynamic";

import { Spinner } from "@/components/query-state";

/** Deck.gl + MapLibre touch `window`, so the map is client-only (no SSR). */
export const MapCanvas = dynamic(
  () => import("./prism-map").then((m) => m.PrismMap),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-[#0a0e16]">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner /> Initializing map…
        </div>
      </div>
    ),
  },
);

export { tip, PR_VIEW } from "./prism-map";
export type { PrismMapApi } from "./prism-map";
