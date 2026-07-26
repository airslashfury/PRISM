/** Puerto Rican Spanish dictionary (`es-PR`, not `es-ES` — see
 * ROADMAP.md item F12 for the register/dialect policy: RAE orthography and
 * grammar, `usted` throughout, PR institutional lexicon where it differs from
 * Peninsular vocabulary. Typed against `Messages` (inferred from `en.ts`) so a
 * missing, extra, or mismatched-shape key is a compile error. */
import type { Messages } from "./en";

export const esPR: Messages = {
  nav: {
    overview: { label: "Resumen", desc: "Lo que está en juego en la infraestructura de Puerto Rico" },
    ask: { label: "Preguntar a PRISM", desc: "Haga una pregunta en lenguaje sencillo y reciba una respuesta con niveles de confianza, basada en los modelos de PRISM" },
    citizen: { label: "Mi área", desc: "Seleccione su barrio para una tarjeta en lenguaje sencillo sobre energía eléctrica, riesgo de inundación y acceso de emergencia" },
    weather: { label: "Clima", desc: "El clima de Puerto Rico por municipio, más una vista de tormenta en vivo: el cono de pronóstico del NHC sobre la red de PRISM cuando se acerca una tormenta" },
    resilience: { label: "Resiliencia", desc: "Qué subestaciones cortan la energía a más hospitales y personas cuando fallan" },
    economy: { label: "Economía", desc: "Quién es más vulnerable y cuánto cuesta cuando se va la luz" },
    water: { label: "Agua", desc: "Qué plantas y bombas de agua fallan — y qué barrios pierden el suministro — cuando falla la red eléctrica" },
    telecom: { label: "Telecomunicaciones", desc: "Qué torres de celular se apagan — y qué barrios pierden cobertura — cuando falla la red eléctrica" },
    parcels: { label: "Parcelas", desc: "Busque cualquiera de las 1.5M parcelas de Puerto Rico por número de catastro, titular o dirección — vea las propiedades por titular y el expediente completo de CRIM, más lo que PRISM sabe sobre ese terreno" },
    trends: { label: "Tendencias del mercado", desc: "Hacia dónde se mueve el mercado de propiedades de Puerto Rico: municipios de mayor actividad por ventas, la tendencia de precios en toda la isla, y los cambios de parcelas mes a mes" },
    sitefinder: { label: "Buscador de sitios", desc: "Dónde construir: clasifique parcelas de zonificación industrial por acceso a puertos de carga, la red eléctrica, agua y seguridad ante inundaciones" },
    portfolio: { label: "Portafolio", desc: "La mejor combinación de inversiones de mitigación dentro de un presupuesto fijo" },
    playground: { label: "Zona de pruebas", desc: "Dibuje infraestructura sobre el modelo en vivo y vea el impacto en costo, capacidad y resiliencia al instante" },
    assumptions: { label: "Supuestos", desc: "Ajuste los supuestos fundamentales del modelo — VOLL, riesgo o confianza del alimentador — y vea qué clasificaciones se mantienen y cuáles cambian" },
    methods: { label: "Centro de confianza", desc: "Cada modelo y capa de datos, con su método, nivel de confianza y qué lo mejoraría" },
    corridor: { label: "Corredor ferroviario", desc: "Rutas clasificadas balanceando costo de construcción, terreno y población servida" },
  },

  sidebar: {
    modelOnline: "Modelo en línea",
    collapseNav: "Contraer navegación",
    expandNav: "Expandir navegación",
    resizeNav: "Redimensionar navegación",
    language: "Idioma",
    languageEnglish: "English",
    languageSpanish: "Español",
    modules: "Módulos",
    groups: {
      Live: "En vivo",
      Explore: "Explorar",
      Decide: "Decidir",
      Reference: "Referencia",
    },
  },

  citizen: {
    title: "¿Qué pasa con mi área?",
    subtitle: "Seleccione su barrio para ver qué dicen los modelos de PRISM sobre la energía eléctrica, el riesgo de inundación y el acceso de emergencia donde usted vive — en lenguaje sencillo, con una etiqueta de confianza en cada cifra.",
    searchPlaceholder: 'Busque su barrio (por ejemplo, "Playa", "Bayamón")',
    loadingBarrios: "Cargando barrios",
    loadingCard: "Cargando su tarjeta cívica",
    infoPanel: {
      title: "Sobre esta tarjeta",
      whatThisIs: {
        title: "Qué es esto",
        body: "Un resumen en lenguaje sencillo de los modelos existentes de PRISM para un barrio: qué subestación se estima que lo sirve y qué depende de ella, qué está haciendo la red eléctrica de la isla en este momento, qué podría significar aquí un huracán o un terremoto, cómo se compara la resiliencia general de esta área con el resto de Puerto Rico, el acceso por carretera al hospital más cercano, la exposición a inundaciones, y cualquier inversión ya planificada cerca.",
      },
      honest: {
        title: "Honesto por diseño",
        // Quotes the literal English word still shown on the chip itself
        // ("Proxy") rather than a translated "Aproximado" — ConfidenceChip's
        // tier labels come from a backend call with an English fallback and
        // are F12b's job, not F12a's. Translating this sentence without
        // translating the chip would have the honesty copy point at a label
        // that isn't on screen.
        body: 'Esto es informativo, no una predicción sobre la cual debe actuar. La etiqueta de color en cada cifra indica qué tan sólida es — la etiqueta "Proxy" significa que PRISM estimó algo (como qué subestación sirve esta área) porque el dato real no es público. Haga clic en una etiqueta para más detalles.',
      },
      notEmergency: {
        title: "No es un aviso de emergencia",
        body: "Esta tarjeta no proviene de su compañía de servicio eléctrico y no es un informe de interrupciones en tiempo real. Para interrupciones activas o emergencias, comuníquese directamente con LUMA / PREPA y con la oficina de manejo de emergencias de su municipio.",
      },
    },
    // "Municipio" comes BEFORE the name in Spanish ("Municipio de
    // Guayanilla"), opposite English's "Guayanilla Municipio".
    municipioLabel: (name) => `Municipio de ${name}`,
    cards: {
      power: "Energía eléctrica",
      communityResilience: "Resiliencia comunitaria",
      emergencyAccess: "Acceso de emergencia",
      floodRisk: "Riesgo de inundación",
      plannedNearby: "Qué hay planificado cerca",
    },
    resilienceSentence: {
      lead: "PRISM califica cada barrio según una combinación de vulnerabilidad social, infraestructura cercana e inversión planificada. Esta área se ubica",
      higherThan: (pct) => `más alto que el ${pct}`,
      ofBarrios: "de los barrios de Puerto Rico en resiliencia general",
      moreVulnerable: " — entre las áreas más vulnerables en el modelo de PRISM",
      moreResilient: " — entre las áreas más resilientes en el modelo de PRISM",
    },
    access: {
      hospitalLead: "El hospital más cercano, ",
      hospitalMid: ", está a unos ",
      minutesUnit: " minutos",
      hospitalAfter: " por carretera en condiciones normales (asumiendo un promedio fijo de 40 km/h — el tiempo real varía según el tráfico y los daños en las vías).",
      noHospital: "Según el modelo de PRISM, ningún hospital es accesible por carretera desde aquí.",
      clinicLead: "La clínica comunitaria más cercana, ",
      clinicMid: ", está a unos ",
      clinicAfter: " por carretera — atención primaria, no capacidad de emergencia.",
      noClinicEither: "Tampoco se encontró ninguna clínica comunitaria cercana.",
    },
    floodCopy: {
      minimal: "Esta área tiene un riesgo de inundación mínimo según los mapas — poca o ninguna parte cae dentro de la zona inundable de FEMA de 1% de probabilidad anual (100 años).",
      low: "Una pequeña parte de esta área cae dentro de la zona inundable de FEMA de 1% de probabilidad anual (100 años).",
      moderate: "Una parte moderada de esta área cae dentro de la zona inundable de FEMA de 1% de probabilidad anual (100 años).",
      high: "Una gran parte de esta área cae dentro de la zona inundable de FEMA de 1% de probabilidad anual (100 años) — las inundaciones son un riesgo serio aquí durante tormentas mayores.",
    },
    plannedNearbyIntro: "Del plan de inversión en resiliencia actual de PRISM, elementos que afectan esta área o su subestación:",
    disclaimer: "Esta tarjeta se genera a partir de los modelos de PRISM únicamente con fines informativos. No constituye un aviso oficial de LUMA, PREPA, PRASA ni de su municipio.",
    power: {
      // "subestación" comes BEFORE the name in Spanish ("la subestación
      // PALO SECO"), so the name-bolding split point sits earlier than in
      // English — everything after the name is empty here.
      drawsFromLead: "Su área recibe energía de la subestación ",
      drawsFromAfter: "",
      keepsRunningLead: " — el mismo sector de la red que también da servicio a ",
      keepsRunningAfter: ".",
      period: ".",
      about: "unas",
      rightNow: "En este momento",
      generatingLead: "la red eléctrica de la isla está generando ",
      mwUnit: " MW",
      plantsOffline: (offline, total) => ` con ${offline} de ${total} plantas fuera de servicio`,
      live: (rel) => `(en vivo, PREPA · ${rel})`,
      lumaReports: "LUMA reporta",
      noOutages: "ningún cliente sin servicio en toda la isla",
      pctWithoutService: (pct) => `${pct}% de los clientes sin servicio en toda la isla`,
      underPointOne: "menos de 0.1",
      liveDot: (rel) => `(en vivo · ${rel}).`,
      cat3Lead: "En un huracán categoría 3",
      cat3Mid: ", si esa subestación falla, PRISM estima que dejaría sin energía a",
      quakeLead: "En un terremoto mayor",
      quakeMid: ", esta subestación ocupa el puesto",
      quakeRankOf: (rank, total) => `#${rank} de ${total}`,
      quakeAfter: "en la lista de riesgo de PRISM para toda la isla — una combinación de qué tan cerca está de fallas geológicas mapeadas y cuánto depende de ella.",
      estimatedNote: "Estimado a partir de la configuración local de la red — la etiqueta de arriba indica qué tan sólido es este dato.",
      people: (n) => (n === 1 ? "persona" : "personas"),
      hospital: (n) => (n === 1 ? "hospital" : "hospitales"),
      waterPlant: (n) => (n === 1 ? "planta de tratamiento de agua" : "plantas de tratamiento de agua"),
      and: " y ",
      listSep: ", ",
      // No comma before "y" in a simple enumeration — RAE grammar, unlike
      // English's Oxford-comma "and". This is the majority case (population +
      // water, with no hospital clause, is the most common shape), so getting
      // it right here matters more than in `and`/`listSep` above.
      andComma: " y ",
    },
  },
};
