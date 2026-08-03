/** Honest "what this estimate includes / excludes" copy per asset type
 * (F9c chunk C2). Sourced from the cost-basis docstrings in prism/assets/*.py
 * and prism/corridor/cost_surface.py — none of those models price right-of-way
 * acquisition, permitting, or geotechnical survey, so that exclusion is a
 * clean, honest claim, not a caveat papering over something the model secretly
 * assumes. Keep in sync if a cost model's basis changes. Locale-aware since
 * F12b, mirroring lib/interventions.ts's EN/ES-PR table pattern. */
import type { Locale } from "@/lib/i18n/locales";

export interface EstimateScope {
  includes: string[];
  excludes: string[];
}

const EN: Record<string, EstimateScope> = {
  rail: {
    includes: [
      "Parametric $/km by terrain tier (standard, elevated, tunnel) from DTOP/FTA PRIITS 2024 references",
      "Annual maintenance modeled as a 30-year NPV at 5%",
    ],
    excludes: ["Right-of-way acquisition", "Permitting", "Geotechnical survey"],
  },
  road: {
    includes: [
      "Parametric $/km — hardening an existing road or building a new corridor (FEMA BRIC + DTOP references)",
      "Annual maintenance modeled as a 30-year NPV at 5%",
    ],
    excludes: ["Right-of-way acquisition", "Permitting", "Geotechnical survey"],
  },
  transmission: {
    includes: [
      "Flat per-intervention cost by type (hardening, redundant feed, elevation, relocation — FEMA BRIC/PREPA/EPRI references, ±40% accuracy)",
    ],
    excludes: ["Right-of-way acquisition", "Permitting", "Geotechnical survey"],
  },
  bridge: {
    includes: ["Span-tiered cost model (FEMA BRIC/DTOP/FHWA references)"],
    excludes: ["Right-of-way acquisition", "Permitting", "Geotechnical survey"],
  },
  substation: {
    includes: ["Flat per-intervention cost by type (same basis as transmission)"],
    excludes: ["Right-of-way acquisition", "Permitting", "Geotechnical survey"],
  },
};

const ES_PR: Record<string, EstimateScope> = {
  rail: {
    includes: [
      "Costo paramétrico $/km por nivel de terreno (estándar, elevado, túnel) de referencias DTOP/FTA PRIITS 2024",
      "Mantenimiento anual modelado como un VPN a 30 años al 5%",
    ],
    excludes: ["Adquisición de derecho de vía", "Permisos", "Estudio geotécnico"],
  },
  road: {
    includes: [
      "Costo paramétrico $/km — reforzar una carretera existente o construir un nuevo corredor (referencias FEMA BRIC + DTOP)",
      "Mantenimiento anual modelado como un VPN a 30 años al 5%",
    ],
    excludes: ["Adquisición de derecho de vía", "Permisos", "Estudio geotécnico"],
  },
  transmission: {
    includes: [
      "Costo fijo por intervención según el tipo (refuerzo, alimentador de respaldo, elevación, reubicación — referencias FEMA BRIC/PREPA/EPRI, precisión ±40%)",
    ],
    excludes: ["Adquisición de derecho de vía", "Permisos", "Estudio geotécnico"],
  },
  bridge: {
    includes: ["Modelo de costo por nivel de luz (referencias FEMA BRIC/DTOP/FHWA)"],
    excludes: ["Adquisición de derecho de vía", "Permisos", "Estudio geotécnico"],
  },
  substation: {
    includes: ["Costo fijo por intervención según el tipo (misma base que transmisión)"],
    excludes: ["Adquisición de derecho de vía", "Permisos", "Estudio geotécnico"],
  },
};

export function estimateScopeFor(assetType: string, locale: Locale = "en"): EstimateScope | undefined {
  return (locale === "es-PR" ? ES_PR : EN)[assetType];
}
