import type { Metadata } from "next";

import { fetchJson } from "@/lib/server-api";
import type { ConsequenceSummary } from "@/lib/api";
import ResiliencePage from "./resilience-client";

const GENERIC_TITLE = "Grid resilience — which substations matter most · PRISM";
const GENERIC_DESC =
  "Every Puerto Rico substation ranked by consequence: what breaks downstream if it fails, and whether there's a backup path.";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: { [key: string]: string | string[] | undefined };
}): Promise<Metadata> {
  const sel = typeof searchParams.sel === "string" ? searchParams.sel : null;
  const scenario = typeof searchParams.scenario === "string" ? searchParams.scenario : null;

  const ogParams = new URLSearchParams();
  if (sel) ogParams.set("sel", sel);
  if (scenario) ogParams.set("scenario", scenario);
  const ogQuery = ogParams.toString();

  if (!sel) {
    return {
      title: GENERIC_TITLE,
      description: GENERIC_DESC,
      openGraph: { images: ["/og/resilience"] },
      twitter: { card: "summary_large_image" },
    };
  }

  const entityId = Number(sel);
  const consequence = Number.isFinite(entityId)
    ? await fetchJson<ConsequenceSummary>(`/network/consequence/${entityId}`, { revalidate: 300 })
    : null;

  if (!consequence) {
    return {
      title: GENERIC_TITLE,
      description: GENERIC_DESC,
      openGraph: { images: [`/og/resilience${ogQuery ? `?${ogQuery}` : ""}`] },
      twitter: { card: "summary_large_image" },
    };
  }

  const title = `${consequence.name ?? `Substation ${consequence.entity_id}`} — Resilience · PRISM`;
  return {
    title,
    description: consequence.headline,
    openGraph: {
      title,
      description: consequence.headline,
      images: [`/og/resilience${ogQuery ? `?${ogQuery}` : ""}`],
    },
    twitter: { card: "summary_large_image" },
  };
}

export default function Page() {
  return <ResiliencePage />;
}
