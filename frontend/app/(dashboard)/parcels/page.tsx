import type { Metadata } from "next";

import { fetchJson } from "@/lib/server-api";
import type { ParcelDetail } from "@/lib/api";
import ParcelsPage from "./parcels-client";

const GENERIC_TITLE = "Parcels — search Puerto Rico's CRIM Catastro · PRISM";
const GENERIC_DESC =
  "Search any of Puerto Rico's 1.5M parcels by catastro, owner, or address — ownership footprints, CRIM records, and what PRISM knows about that ground.";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: { [key: string]: string | string[] | undefined };
}): Promise<Metadata> {
  const sel = typeof searchParams.sel === "string" ? searchParams.sel : null;

  if (!sel) {
    return {
      title: GENERIC_TITLE,
      description: GENERIC_DESC,
      openGraph: { images: ["/og/parcels"] },
      twitter: { card: "summary_large_image" },
    };
  }

  const ogQuery = new URLSearchParams({ sel }).toString();
  const detail = await fetchJson<ParcelDetail>(`/crim/parcel/${encodeURIComponent(sel)}`, {
    revalidate: 300,
  });

  if (!detail) {
    return {
      title: GENERIC_TITLE,
      description: GENERIC_DESC,
      openGraph: { images: [`/og/parcels?${ogQuery}`] },
      twitter: { card: "summary_large_image" },
    };
  }

  const title = `Parcel ${detail.num_catastro}${detail.municipio ? ` (${detail.municipio})` : ""} · PRISM`;
  const description =
    detail.crim.owner ??
    (detail.crim.total_value != null
      ? `Assessed value ${detail.crim.total_value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })}`
      : GENERIC_DESC);

  return {
    title,
    description,
    openGraph: { title, description, images: [`/og/parcels?${ogQuery}`] },
    twitter: { card: "summary_large_image" },
  };
}

export default function Page() {
  return <ParcelsPage />;
}
