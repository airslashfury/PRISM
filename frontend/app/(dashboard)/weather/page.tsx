import type { Metadata } from "next";

import { fetchJson } from "@/lib/server-api";
import type { StormResponse } from "@/lib/api";
import WeatherPage from "./weather-client";

const GENERIC_TITLE = "Weather — Climate · PRISM";
const GENERIC_DESC =
  "Puerto Rico's climate by municipio — average rain days, temperature, and estimated workable construction days from NOAA's 1991-2020 normals. Includes the live storm lens.";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: { lens?: string };
}): Promise<Metadata> {
  if (searchParams?.lens === "storm") {
    const data = await fetchJson<StormResponse>("/network/storm", { revalidate: 300 });
    const advisory = data?.advisory ?? null;

    if (!advisory) {
      return {
        title: "Live storm — Weather · PRISM",
        description: GENERIC_DESC,
        openGraph: { images: ["/og/weather?lens=storm"] },
        twitter: { card: "summary_large_image" },
      };
    }

    const namePart = `${advisory.storm_name ?? "Unnamed storm"}${advisory.replay ? " (demo)" : ""} advisory #${advisory.advisory_num}`;
    const title = `${namePart} — Weather · PRISM`;
    const description = data?.consequence?.headline ?? GENERIC_DESC;

    return {
      title,
      description,
      openGraph: { title, description, images: ["/og/weather?lens=storm"] },
      twitter: { card: "summary_large_image" },
    };
  }

  return {
    title: GENERIC_TITLE,
    description: GENERIC_DESC,
    openGraph: { images: ["/og/weather"] },
    twitter: { card: "summary_large_image" },
  };
}

export default function Page() {
  return <WeatherPage />;
}
