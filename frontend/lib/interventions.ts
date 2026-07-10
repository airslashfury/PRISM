/** Shared plain-language copy for portfolio intervention types (F9a chunk A3).
 *
 * The optimizer emits machine tokens ("elevation", "road_hardening") that mean
 * nothing to a resident. This map translates each one for humans: `title` is
 * the physical action, `what` is one sentence on what crews actually build,
 * `why` is what it means for the people nearby.
 *
 * Deliberately dependency-free — imported by /citizen today and by /portfolio
 * (F9c chunk C1). Keep entries in sync with the intervention types produced in
 * prism/optimize/catalog.py.
 */

export interface InterventionCopy {
  /** Plain action phrase, e.g. "Raise equipment above flood level". */
  title: string;
  /** One physical sentence: what crews actually do. */
  what: string;
  /** One "what it means for you" sentence. */
  why: string;
}

export const INTERVENTION_COPY: Record<string, InterventionCopy> = {
  elevation: {
    title: "Raise equipment above flood level",
    what: "Lifts transformers and control gear onto raised platforms so floodwater passes underneath.",
    why: "Your area is less likely to lose power when the substation's site floods.",
  },
  relocation: {
    title: "Move equipment to safer ground",
    what: "Rebuilds the substation on a new site outside the flood zone.",
    why: "Removes the flood risk at its source — reserved for the most exposed sites.",
  },
  hardening: {
    title: "Reinforce against storm and flood damage",
    what: "Adds flood barriers and structural reinforcement around the existing equipment.",
    why: "The substation is more likely to ride out a hurricane without an outage.",
  },
  road_hardening: {
    title: "Flood-proof the access road",
    what: "Upgrades the critical stretch of road so it stays passable in a flood.",
    why: "Ambulances and repair crews can still reach your area during and after a storm.",
  },
  redundant_feed: {
    title: "Add a backup power feed",
    what: "Connects the substation to a second transmission line so one failure doesn't cut service.",
    why: "If the main feed goes down in a storm, your area can switch to the backup instead of losing power.",
  },
  new_access_road: {
    title: "Build a new access road",
    what: "Adds a road connection to a site currently reachable only by a severely degraded route.",
    why: "Repair crews and emergency vehicles gain a way in when the existing route floods or fails.",
  },
};

/** Full copy entry for an intervention type, or null for unknown types. */
export function interventionCopy(type: string): InterventionCopy | null {
  return INTERVENTION_COPY[type] ?? null;
}

/** Plain-language title for an intervention type. Unknown types fall back to
 * title-casing the token ("new_access_road" → "New Access Road"). */
export function humanizeIntervention(type: string): string {
  const copy = INTERVENTION_COPY[type];
  if (copy) return copy.title;
  return type
    .split("_")
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}
