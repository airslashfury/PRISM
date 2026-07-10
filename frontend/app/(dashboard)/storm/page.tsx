import type { Metadata } from "next";

import { fetchJson } from "@/lib/server-api";
import type { StormResponse } from "@/lib/api";
import StormPage from "./storm-client";

const GENERIC_TITLE = "Live storm — Storm · PRISM";
const GENERIC_DESC =
  "The live NHC forecast cone over PRISM's grid — which substations, hospitals, and people fall inside the probable track area.";

export async function generateMetadata(): Promise<Metadata> {
  const data = await fetchJson<StormResponse>("/network/storm", { revalidate: 300 });
  const advisory = data?.advisory ?? null;

  if (!advisory) {
    return {
      title: GENERIC_TITLE,
      description: GENERIC_DESC,
      openGraph: { images: ["/og/storm"] },
      twitter: { card: "summary_large_image" },
    };
  }

  // No REPLAY badge is possible in a plain <title>/og:title string, so a
  // replayed advisory is marked inline — matches the "(demo)" convention
  // used everywhere else a bare storm name renders (F9a A2).
  const namePart = `${advisory.storm_name ?? "Unnamed storm"}${advisory.replay ? " (demo)" : ""} advisory #${advisory.advisory_num}`;
  const title = `${namePart} — Storm · PRISM`;
  const description = data?.consequence?.headline ?? GENERIC_DESC;

  return {
    title,
    description,
    openGraph: { title, description, images: ["/og/storm"] },
    twitter: { card: "summary_large_image" },
  };
}

export default function Page() {
  return <StormPage />;
}
