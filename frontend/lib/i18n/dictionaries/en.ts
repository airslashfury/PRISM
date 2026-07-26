/** English dictionary — the canonical key set. `es-PR.ts` is typed against
 * this file's inferred shape (`Messages`), so a missing or extra key is a
 * compile error rather than a silent English leak.
 *
 * Deliberately NOT `as const`: a const assertion would let TypeScript narrow
 * function return types to the literal union of *this file's* string
 * literals (e.g. `people: (n) => "person" | "people"`), which would then
 * reject `es-PR.ts`'s different return strings ("persona"/"personas") as a
 * type error. Plain inference widens these to `string`, which is what both
 * locales actually need to share. */
export const en = {
  nav: {
    overview: { label: "Overview", desc: "What's at stake across Puerto Rico's infrastructure" },
    ask: { label: "Ask PRISM", desc: "Ask a question in plain language and get an answer with confidence tiers, drawn from PRISM's models" },
    citizen: { label: "My Area", desc: "Pick your barrio for a plain-language card on power, flood risk, and emergency access" },
    weather: { label: "Weather", desc: "Puerto Rico's climate by municipio, plus a live-storm lens: the NHC forecast cone over PRISM's grid when a storm approaches" },
    resilience: { label: "Resilience", desc: "Which substations cut power to the most hospitals and people when they fail" },
    economy: { label: "Economy", desc: "Who's most vulnerable and how much it costs when the lights go out" },
    water: { label: "Water", desc: "Which water plants and pumps fail — and which barrios lose supply — when the power grid goes down" },
    telecom: { label: "Telecom", desc: "Which cell towers go dark — and which barrios lose coverage — when the power grid fails" },
    parcels: { label: "Parcels", desc: "Search any of Puerto Rico's 1.5M parcels by catastro, owner, or address — see ownership footprints and the full CRIM record plus what PRISM knows about that ground" },
    trends: { label: "Market Trends", desc: "Where Puerto Rico's property market is moving: hot-spot municipios by sales, the island-wide price trend, and month-over-month parcel changes" },
    sitefinder: { label: "Site Finder", desc: "Where to build: rank industrial-zoned parcels by access to cargo ports, the grid, water, and flood safety" },
    portfolio: { label: "Portfolio", desc: "The best combination of hardening investments within a fixed budget" },
    playground: { label: "Playground", desc: "Sketch infrastructure onto the live model and see cost, capacity, and resilience impact instantly" },
    assumptions: { label: "Assumptions", desc: "Push on the model's load-bearing assumptions — dial VOLL, hazard, or feeder confidence and see which rankings hold and which flip" },
    methods: { label: "Trust Center", desc: "Every model and data layer, with its method, confidence tier, and what would upgrade it" },
    corridor: { label: "Rail Corridor", desc: "Ranked routes balancing construction cost, terrain, and population served" },
  },

  sidebar: {
    modelOnline: "Model online",
    collapseNav: "Collapse navigation",
    expandNav: "Expand navigation",
    resizeNav: "Resize navigation",
    language: "Language",
    languageEnglish: "English",
    languageSpanish: "Español",
    modules: "Modules",
    // Keyed by the internal NavGroup literal ("Live"/"Explore"/"Decide"/
    // "Reference"), which also drives NAV filtering — this map translates the
    // *displayed* heading without touching the grouping key itself.
    groups: {
      Live: "Live",
      Explore: "Explore",
      Decide: "Decide",
      Reference: "Reference",
    },
  },

  citizen: {
    title: "What about my area?",
    subtitle: "Pick your barrio to see what PRISM's models say about power, flood risk, and emergency access where you live — in plain language, with a confidence label on every figure.",
    searchPlaceholder: 'Search for your barrio (e.g. "Playa", "Bayamón")',
    loadingBarrios: "Loading barrios",
    loadingCard: "Loading your civic card",
    infoPanel: {
      title: "About this card",
      whatThisIs: {
        title: "What this is",
        body: "A plain-language summary of PRISM's existing models for one barrio: which substation is estimated to serve it and what rides on it, what the island grid is doing right now, what a hurricane or earthquake could mean here, how this area's overall resilience compares to the rest of Puerto Rico, road access to the nearest hospital, flood exposure, and any investments already planned nearby.",
      },
      honest: {
        title: "Honest by construction",
        body: 'This is informational, not a prediction you should act on. The colored chip on each figure tells you how solid it is — "Proxy" means PRISM approximated something (like which substation serves this area) because the real data isn\'t public. Click a chip for details.',
      },
      notEmergency: {
        title: "Not an emergency notice",
        body: "This card does not come from your utility and is not a real-time outage report. For active outages or emergencies, contact LUMA / PREPA and your municipio's emergency management office directly.",
      },
    },
    // Function, not a bare suffix string — Spanish puts "Municipio" BEFORE
    // the name ("Municipio de Guayanilla"), English puts it after
    // ("Guayanilla Municipio"), so the word order itself differs by locale.
    municipioLabel: (name: string): string => `${name} Municipio`,
    cards: {
      power: "Power",
      communityResilience: "Community resilience",
      emergencyAccess: "Emergency access",
      floodRisk: "Flood risk",
      plannedNearby: "What's planned nearby",
    },
    resilienceSentence: {
      lead: "PRISM scores every barrio on a mix of social vulnerability, nearby infrastructure, and planned investment. This area ranks",
      higherThan: (pct: string): string => `higher than ${pct}`,
      ofBarrios: "of Puerto Rico's barrios on overall resilience",
      moreVulnerable: " — among the more vulnerable areas in PRISM's model",
      moreResilient: " — among the more resilient areas in PRISM's model",
    },
    access: {
      // Lead/mid/after around TWO bolded values (the hospital/clinic name,
      // then the minutes figure) — same three-way split as `power.drawsFrom*`,
      // needed here for the same reason: a single template-string function
      // would flatten both bold <span>s into plain text.
      hospitalLead: "The nearest hospital, ",
      hospitalMid: ", is roughly ",
      minutesUnit: " minutes",
      hospitalAfter: " away by road under normal conditions (assuming a flat 40 km/h average — real travel time varies with traffic and road damage).",
      noHospital: "No hospital is reachable by road from here in PRISM's model.",
      clinicLead: "The nearest community clinic, ",
      clinicMid: ", is roughly ",
      clinicAfter: " away by road — primary care, not emergency capacity.",
      noClinicEither: "No nearby community clinic was found either.",
    },
    floodCopy: {
      minimal: "This area has minimal mapped flood risk — little to none of it falls inside the FEMA 1%-annual-chance (100-year) flood zone.",
      low: "A small part of this area falls inside the FEMA 1%-annual-chance (100-year) flood zone.",
      moderate: "A moderate part of this area falls inside the FEMA 1%-annual-chance (100-year) flood zone.",
      high: "A large part of this area falls inside the FEMA 1%-annual-chance (100-year) flood zone — flooding is a serious risk here in major storms.",
    },
    plannedNearbyIntro: "From PRISM's current resilience investment plan, items affecting this area or its substation:",
    disclaimer: "This card is generated from PRISM's models for informational purposes only. It is not an official notice from LUMA, PREPA, PRASA, or your municipio.",
    power: {
      // Split into lead/after around the substation name so the name can
      // stay its own bold <span> in JSX — Spanish puts "subestación" BEFORE
      // the name ("la subestación PALO SECO") where English puts it after
      // ("the PALO SECO substation"), so the split point itself differs by
      // locale, not just the words.
      drawsFromLead: "Your area draws power from the ",
      drawsFromAfter: " substation",
      keepsRunningLead: " — the same grid section that keeps ",
      keepsRunningAfter: " running.",
      period: ".",
      about: "about",
      rightNow: "Right now",
      generatingLead: "the island grid is generating ",
      mwUnit: " MW",
      plantsOffline: (offline: number, total: number) => ` with ${offline} of ${total} plants offline`,
      live: (rel: string) => `(live, PREPA · ${rel})`,
      lumaReports: "LUMA reports",
      noOutages: "no customers without service island-wide",
      pctWithoutService: (pct: string) => `${pct}% of customers island-wide without service`,
      underPointOne: "under 0.1",
      liveDot: (rel: string) => `(live · ${rel}).`,
      cat3Lead: "In a Category 3 hurricane",
      cat3Mid: ", if that substation goes down, PRISM estimates it would cut power to",
      quakeLead: "In a major earthquake",
      // Lead/mid/after around the bolded "#{rank} of {total}" span — a plain
      // template function here would have flattened that bold span into text.
      quakeMid: ", this substation ranks",
      quakeRankOf: (rank: number, total: number): string => `#${rank} of ${total}`,
      quakeAfter: "island-wide on PRISM's risk list — a mix of how close it sits to mapped faults and how much depends on it.",
      estimatedNote: "Estimated from the local grid layout — the chip above says how solid this is.",
      people: (n: number): string => (n === 1 ? "person" : "people"),
      hospital: (n: number): string => (n === 1 ? "hospital" : "hospitals"),
      waterPlant: (n: number): string => (n === 1 ? "water treatment plant" : "water treatment plants"),
      and: " and ",
      listSep: ", ",
      /** ", and " — the water-treatment-plant clause in the Cat-3 sentence
       * always gets this prefix, whether or not a hospital clause preceded
       * it (mirrors the original hardcoded ", and" in the English JSX). */
      andComma: ", and ",
    },
  },
};

export type Messages = typeof en;
