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

  const namePart = `${advisory.storm_name ?? "Unnamed storm"} advisory #${advisory.advisory_num}`;
  const title = `${advisory.replay ? "Replay: " : ""}${namePart} — Storm · PRISM`;
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
