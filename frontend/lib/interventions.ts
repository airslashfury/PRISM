/** Shared plain-language copy for portfolio intervention types (F9a chunk A3).
 *
 * The optimizer emits machine tokens ("elevation", "road_hardening") that mean
 * nothing to a resident. This map translates each one for humans: `title` is
 * the physical action, `what` is one sentence on what crews actually build,
 * `why` is what it means for the people nearby.
 *
 * Deliberately dependency-free — imported by /citizen today and by /portfolio
 * (F9c chunk C1). Keep entries in sync with the intervention types produced in
 * prism/optimize/catalog.py. Locale-aware since F12a; `es-PR` entries use
 * `usted` register per ROADMAP.md item F12's dialect policy.
 */
import type { Locale } from "@/lib/i18n/locales";

export interface InterventionCopy {
  /** Plain action phrase, e.g. "Raise equipment above flood level". */
  title: string;
  /** One physical sentence: what crews actually do. */
  what: string;
  /** One "what it means for you" sentence. */
  why: string;
}

const EN: Record<string, InterventionCopy> = {
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

const ES_PR: Record<string, InterventionCopy> = {
  elevation: {
    title: "Elevar el equipo sobre el nivel de inundación",
    what: "Levanta los transformadores y el equipo de control sobre plataformas elevadas para que el agua de inundación pase por debajo.",
    why: "Es menos probable que su área pierda energía cuando se inunde el sitio de la subestación.",
  },
  relocation: {
    title: "Trasladar el equipo a terreno más seguro",
    what: "Reconstruye la subestación en un nuevo sitio fuera de la zona inundable.",
    why: "Elimina el riesgo de inundación en su origen — reservado para los sitios más expuestos.",
  },
  hardening: {
    title: "Reforzar contra daños de tormenta e inundación",
    what: "Añade barreras contra inundaciones y refuerzo estructural alrededor del equipo existente.",
    why: "Es más probable que la subestación resista un huracán sin una interrupción del servicio.",
  },
  road_hardening: {
    title: "Proteger la vía de acceso contra inundaciones",
    what: "Mejora el tramo crítico de la vía para que se mantenga transitable durante una inundación.",
    why: "Las ambulancias y las cuadrillas de reparación aún pueden llegar a su área durante y después de una tormenta.",
  },
  redundant_feed: {
    title: "Añadir un alimentador de respaldo",
    what: "Conecta la subestación a una segunda línea de transmisión para que una sola falla no corte el servicio.",
    why: "Si el alimentador principal falla en una tormenta, su área puede cambiar al respaldo en lugar de quedarse sin energía.",
  },
  new_access_road: {
    title: "Construir una nueva vía de acceso",
    what: "Añade una conexión vial a un sitio actualmente accesible solo por una ruta gravemente deteriorada.",
    why: "Las cuadrillas de reparación y los vehículos de emergencia ganan una entrada cuando la ruta existente se inunda o falla.",
  },
};

function tableFor(locale: Locale): Record<string, InterventionCopy> {
  return locale === "es-PR" ? ES_PR : EN;
}

/** Full copy entry for an intervention type, or null for unknown types. */
export function interventionCopy(type: string, locale: Locale = "en"): InterventionCopy | null {
  return tableFor(locale)[type] ?? null;
}

/** Plain-language title for an intervention type. Unknown types fall back to
 * title-casing the token ("new_access_road" → "New Access Road"). */
export function humanizeIntervention(type: string, locale: Locale = "en"): string {
  const copy = tableFor(locale)[type];
  if (copy) return copy.title;
  return type
    .split("_")
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}
