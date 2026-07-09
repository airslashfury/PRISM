/** Honest "what this estimate includes / excludes" copy per asset type
 * (F9c chunk C2). Sourced from the cost-basis docstrings in prism/assets/*.py
 * and prism/corridor/cost_surface.py — none of those models price right-of-way
 * acquisition, permitting, or geotechnical survey, so that exclusion is a
 * clean, honest claim, not a caveat papering over something the model secretly
 * assumes. Keep in sync if a cost model's basis changes. */

export interface EstimateScope {
  includes: string[];
  excludes: string[];
}

export const ESTIMATE_SCOPE: Record<string, EstimateScope> = {
  rail: {
    includes: [
      "Parametric $/km by terrain tier (standard, elevated, tunnel) from DTOP/FTA PRIITS 2024 references",
      "Annual maintenance modeled as a 15-year NPV",
    ],
    excludes: ["Right-of-way acquisition", "Permitting", "Geotechnical survey"],
  },
  road: {
    includes: [
      "Parametric $/km — hardening an existing road or building a new corridor (FEMA BRIC + DTOP references)",
      "Annual maintenance cost",
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
