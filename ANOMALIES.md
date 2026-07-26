<!-- GENERATED FROM config/anomalies.yml — DO NOT EDIT. Run `make anomalies`. -->

# PRISM — Excluded and Anomalous Data

Every place PRISM excludes, filters, caps, or sets aside source data before it
reaches a view or a calculation. Each entry names what is excluded, why, the code
path that enforces it, which parts of the product are affected, the measured size
of the exclusion, and — where there is one — what the source institution would
have to fix.

The exclusions are individually defensible. Together they are a data-quality
report: 23 of the 35 entries below describe a defect in
published government data rather than a modelling choice, and each of those names
the institution that could close it.

**PRISM's rule:** when data is set aside, it is said out loud. Some of what
follows genuinely does bound what PRISM can claim — the entries marked *high*
say so in as many words. This is the accounting that lets a reader tell which
figures those are, instead of having to take all of them on faith.

Counts measured 2026-07-26. This file is generated from
[`config/anomalies.yml`](config/anomalies.yml) by `make anomalies` — edit the
registry, not this file.

## Summary

| Severity | Entries |
|---|---|
| High — materially affects conclusions PRISM draws | 7 |
| Medium — narrows or biases a figure | 16 |
| Low — cosmetic or well-bounded | 12 |
| **Total active** | **35** |

| # | Exclusion | Dataset | Severity |
|---|---|---|---|
| 1 | [Two thirds of recorded "ownership changes" are the same owner written differently](#crim-owner-change-formatting-churn) | `crim.parcel_deltas (change_type='owner_change')` | high |
| 2 | [196,132 duplicate parcel rows are collapsed by "highest objectid wins"](#crim-parcel-dedup-collapse) | `crim.parcelas -> crim.parcelas_dedup` | high |
| 3 | [Implausible sale amounts and dates are excluded from every sale figure](#crim-sales-amount-outliers) | `crim.parcelas_history.salesamt / .salesdttm` | high |
| 4 | [Point facilities are still attached to substations by proximity, not by conductor](#point-facilities-keep-voronoi-powers) | `graph.relationships (POWERS, method IN ('nearest_dist_sub','voronoi'))` | high |
| 5 | [The registry mirror is a partial walk, so a missing match is not proof of no registration](#rce-registry-mirror-incomplete) | `crim.rce_entities` | high |
| 6 | [542 of 961 substations power nothing in the graph](#substations-without-distribution-capability) | `graph.relationships (POWERS) / resilience.cascade_scores` | high |
| 7 | [Most water sources serve no barrios in the graph, so they score zero consequence](#water-wells-zero-criticality) | `resilience.water_scores` | high |
| 8 | [Fifteen barrios have no reachable hospital in the road graph](#barrios-without-routable-hospital) | `transport.road_access_cost` | medium |
| 9 | [A third of bridges have no measured span, and nothing costs them](#bridge-missing-span-defaulted) | `transport.bridge_inventory.span_m` | medium |
| 10 | [Layer checksums detect added or removed features, not edited ones](#checksum-is-count-based) | `catalog/metadata.json` | medium |
| 11 | [Placeholder address segments are stripped before an address is displayed](#crim-address-placeholder-junk) | `crim.parcelas.direccion_fisica` | medium |
| 12 | [Parcel rows with no catastro number are dropped from every derived view](#crim-null-catastro-rows) | `crim.parcelas -> crim.parcelas_dedup / crim.parcelas_history` | medium |
| 13 | [Only the five most recent records per parcel enter the sale history](#crim-sale-history-top5) | `crim.parcelas_history` | medium |
| 14 | [Substation-to-barrio links below a real service share are dropped](#feeder-secondary-sliver-edges-dropped) | `graph.relationships (POWERS, method='feeder_topology')` | medium |
| 15 | [Barrios whose measured substation is missing from the transmission graph keep the Voronoi proxy](#feeds-isolated-substations-keep-voronoi) | `graph.relationships (POWERS, method LIKE 'voronoi%')` | medium |
| 16 | [Transmission links with equal or missing voltage produce no FEEDS edge](#feeds-voltage-hierarchy-dropout) | `graph.relationships (FEEDS)` | medium |
| 17 | [Anything short of a single exact geocoder match is treated as no match](#geocode-ambiguous-match-rejected) | `crim.geocode_cache` | medium |
| 18 | [Hospital access routes only to true hospitals, excluding clinics that carry a hospital kind](#hospital-access-clasif-filter) | `transport.road_access_cost` | medium |
| 19 | [Shared contracts are flagged, never divided between co-contractors](#ocpr-shared-contracts-not-divided) | `ocpr.contract_contractors` | medium |
| 20 | [Approximate addresses can only cite numbered state highways](#proposed-address-no-local-street-layer) | `crim.parcel_proposed_address (Tier B)` | medium |
| 21 | [Placeholder registry addresses are excluded from the address layer](#rce-address-sentinels) | `crim.rce_addresses` | medium |
| 22 | [A plausible-but-unconfirmed registry match is recorded as no match](#rce-ambiguous-match-withdrawn) | `crim.owner_rce_match` | medium |
| 23 | [Twenty substations sit too far from any transmission line to join the graph](#substations-beyond-transmission-attach-radius) | `graph.relationships (CONNECTS_TO)` | medium |
| 24 | [Ask PRISM only excludes government owners when explicitly asked to](#ask-government-owner-filter-opt-in) | `crim.parcelas_dedup (via the Ask SQL tool)` | low |
| 25 | [The ACS mirror is skipped without an API key](#census-acs-requires-api-key) | `Census ACS 5-year estimates` | low |
| 26 | [Assessed-value changes under $1 are not recorded as deltas](#crim-reassessment-noise-floor) | `crim.parcel_deltas` | low |
| 27 | [CRIM's unknown-owner placeholder is filtered out of owner intelligence](#crim-unknown-owner-sentinel) | `crim.owner_entities` | low |
| 28 | [Fourteen substations have a bare number where a name should be](#hifld-unnamed-substations) | `graph.entities (kind='substation')` | low |
| 29 | [The investment plan can only choose from the worst 200 substations and 100 barrios](#ilp-catalog-top-n-cap) | `optimize.portfolio_runs (via the intervention catalog)` | low |
| 30 | [Public bodies are excluded from the contractor-owner ranking unless toggled on](#ocpr-government-excluded-by-default) | `ocpr.government_keys` | low |
| 31 | [Reported generation capacity excludes PPOA renewables](#prepa-capacity-excludes-ppoa) | `sync.generation_status` | low |
| 32 | [High-density addresses are flagged as agent offices, not treated as shared control](#rce-agent-office-addresses) | `crim.rce_address_entities` | low |
| 33 | [Registry rows named "UNKNOWN ENTITY" are excluded from owner matching](#rce-unknown-entity-sentinel) | `crim.rce_entities -> crim.owner_rce_match` | low |
| 34 | [Fiber conduits are mirrored but excluded from every telecom view](#telecom-no-fiber-layer) | `g37_telecom_conductos_fibra_optica_act_2012` | low |
| 35 | [Telecom assets carry zero cascade weight by design](#telecom-zero-cascade-criticality) | `graph.entities (telecom kinds)` | low |

## High — materially affects conclusions PRISM draws

### Two thirds of recorded "ownership changes" are the same owner written differently

<a id="crim-owner-change-formatting-churn"></a>

- **id** `crim_owner_change_formatting_churn`
- **Dataset** `crim.parcel_deltas (change_type='owner_change')`
- **Source** CRIM
- **Enforced at** `prism/report/monthly.py:classify_owner_change`

**What is excluded.** The monthly delta records an ownership change whenever the raw `contact` string differs at all, so a removed trailing space counts as a transfer. The monthly change report classifies every one with `normalize_owner()` — PRISM's canonical owner key — and reports only genuinely different names as ownership changes; the rest are broken out as spacing/punctuation-only or the same name reordered.

**Why.** Reporting the raw count would overstate transfers by roughly a factor of three. Deleting the cosmetic rows would be worse — they are evidence of how the register is maintained — so they are classified and shown, not dropped.

**Affects.**
- the monthly change report's ownership section (headline + per-municipio)
- WhatsNew crim_delta headlines, which still quote the raw delta count

**How much.** 2026-07 delta, a true partition of 7,722 owner-field changes: 2,178 substantive + 242 first-recorded (the 2,420 headline) + 2,598 spacing/punctuation-only + 2,704 the same name reordered. Of the reordered, 1,005 are the JOHN DOE unknown-owner sentinel rewritten (`JOHN DOE` -> `DOE JOHN`), which is placeholder churn rather than any kind of transfer — see `crim_unknown_owner_sentinel`.

```sql
-- Whitespace/case equality alone finds 2,550; the registered 2,598 also -- folds punctuation and legal suffixes, matching normalize_owner(), so -- the authoritative count comes from -- prism/report/monthly.py:classify_owner_change rather than from SQL. SELECT count(*) FROM crim.parcel_deltas WHERE change_type = 'owner_change' AND regexp_replace(upper(btrim(old_value)), '\s+', ' ', 'g') = regexp_replace(upper(btrim(new_value)), '\s+', ' ', 'g')
```

**What would fix it** (CRIM — Centro de Recaudación de Ingresos Municipales). CRIM: the owner field is not normalized at entry, so the same person is stored with varying spacing and with surname and given name in either order. Anyone differencing successive published snapshots — which is the only way to observe transfers, since the register publishes current state only — will read roughly three times as many transfers as occurred.

---

### 196,132 duplicate parcel rows are collapsed by "highest objectid wins"

<a id="crim-parcel-dedup-collapse"></a>

- **id** `crim_parcel_dedup_collapse`
- **Dataset** `crim.parcelas -> crim.parcelas_dedup`
- **Source** CRIM
- **Enforced at** `prism/crim/schema.py:_MATVIEW_DDL`

**What is excluded.** The published fabric carries several rows per catastro number. The dedup view keeps exactly one — `DISTINCT ON (num_catastro) ... ORDER BY num_catastro, objectid DESC` — so 1,497,850 keyed rows become 1,301,718. "Highest objectid" is PRISM's own definition of which row is current; CRIM publishes no explicit current-record flag.

**Why.** Every owner, valuation and search surface needs one row per parcel. Without a published currency flag, the highest objectid is the only ordering available, and it matches the ordering the sale-history view already uses.

**Affects.**
- every /parcels surface, and the ~1.5M parcel figure (1.30M is what is served)
- the monthly change report — snapshots and deltas are taken over the deduped view, so this convention decides what counts as a change
- owner intelligence and the corporate-registry match

**How much.** 196,132 of 1,497,850 keyed rows collapsed (13.1%)

```sql
SELECT (SELECT count(*) FROM crim.parcelas WHERE num_catastro IS NOT NULL) - (SELECT count(*) FROM crim.parcelas_dedup)
```

**What would fix it** (CRIM — Centro de Recaudación de Ingresos Municipales). CRIM: the published fabric contains ~196K duplicate catastro rows with no field marking which is current, so any consumer must invent a tie-break. A currency flag, or a de-duplicated publication, would make every downstream count reproducible instead of convention-dependent.

---

### Implausible sale amounts and dates are excluded from every sale figure

<a id="crim-sales-amount-outliers"></a>

- **id** `crim_sales_amount_outliers`
- **Dataset** `crim.parcelas_history.salesamt / .salesdttm`
- **Source** CRIM
- **Enforced at** `prism/crim/trends.py:_SANE`

**What is excluded.** `/trends` counts a recorded sale only when `salesamt` is between $1,000 and $50,000,000 AND `salesdttm` falls between 1980-01-01 and today. The bound applies to the sale COUNTS as well as to the medians — sales outside it are absent from "N sales in the last 12 months", from municipio momentum, and from the market context on the parcel card, not merely from the price.

**Why.** The raw column carries corrupt values — single "sales" of $10^13 — so sums and averages on it are meaningless, and a row whose amount is impossible is not evidence that a transaction occurred either. 288 sales island-wide exceed $50M and every one inspected is a data error.

**Affects.**
- /trends sale COUNTS (sales_12mo, sales_total) — not only the medians
- /trends median sale price, momentum, hot-spot municipios
- municipio market context on the parcel card and /economy
- the monthly report's sales figures

**How much.** 570,923 of the 836,108 rows carrying a sale amount survive both bounds, so 265,185 recorded sales (31.7%) are excluded from every sale figure PRISM prints. The sub-counts overlap and do not partition it: 257,559 fail the amount bound, 18,596 carry a date outside the window, and a further tranche carry no sale date at all, which the BETWEEN also excludes.

```sql
SELECT count(*) FILTER (WHERE salesamt BETWEEN 1000 AND 50000000 AND salesdttm BETWEEN DATE '1980-01-01' AND CURRENT_DATE) AS counted, count(*) AS with_amount FROM crim.parcelas_history WHERE salesamt IS NOT NULL
```

**What would fix it** (CRIM — Centro de Recaudación de Ingresos Municipales). CRIM: roughly a third of recorded sale amounts are outside any plausible range — a mix of $0/$1 nominal transfers and corrupt magnitudes. A validation rule at entry, and a flag distinguishing nominal transfers from arm's-length sales, would make the price series usable as published.

---

### Point facilities are still attached to substations by proximity, not by conductor

<a id="point-facilities-keep-voronoi-powers"></a>

- **id** `point_facilities_keep_voronoi_powers`
- **Dataset** `graph.relationships (POWERS, method IN ('nearest_dist_sub','voronoi'))`
- **Source** PRISM-derived (proxy)
- **Enforced at** `prism/graph/relationships.py`

**What is excluded.** Hospitals, water plants, telecom towers and other point facilities are linked to the nearest distribution substation by distance. Only barrio population was switched to the measured feeder network (F11f).

**Why.** The feeder network gives conductor geometry, not service-point assignments, so which substation actually feeds a given building cannot be read off it. Distance is the honest available proxy and is tiered as one.

**Affects.**
- "serves N hospitals" figures throughout the cascade views
- /water and /telecom power-dependency scoring
- the citizen card's "same feed serves" line

**How much.** 3,251 of 4,419 POWERS edges (73.6%) attach a point facility by distance, written by two code paths: `nearest_dist_sub` (2,919 — 1,487 water pump stations, 798 telecom towers, 527 wells, 107 cell sites) and `voronoi` (332 — 139 water plants, 124 health centers, 69 hospitals). The hospitals and water plants named above are in the second group.

```sql
SELECT r.method, e2.kind, count(*) FROM graph.relationships r JOIN graph.entities e2 ON e2.entity_id = r.dst_entity WHERE r.rel_type = 'POWERS' AND r.method IN ('nearest_dist_sub','voronoi') GROUP BY 1, 2 ORDER BY 3 DESC
```

**What would fix it** (LUMA Energy). LUMA: a service-point-to-feeder mapping (which customer account sits on which circuit) is the single dataset that would convert most of PRISM's remaining proxy edges into measured ones.

---

### The registry mirror is a partial walk, so a missing match is not proof of no registration

<a id="rce-registry-mirror-incomplete"></a>

- **id** `rce_registry_mirror_incomplete`
- **Dataset** `crim.rce_entities`
- **Source** PR Department of State — corporations registry
- **Enforced at** `prism/sync/rcp.py`

**What is excluded.** The registry has no bulk export; PRISM walks it entity by entity under a self-imposed rate limit that respects the registry's own WAF. The mirror is therefore a snapshot of however far the walk has advanced, not the whole register.

**Why.** Rate-limited enumeration is the only access path available. The alternative — claiming completeness — would make "no registry record" read as "not incorporated" when it may only mean "not yet pulled".

**Affects.**
- the corporate-registry section on the owner drawer and parcel card (silent when there is no record, never asserting absence)
- the corporate-suffix match rate quoted for owner matching

**How much.** 324,281 entities mirrored of an estimated ~560,000

```sql
SELECT count(*) FROM crim.rce_entities
```

**What would fix it** (Departamento de Estado — corporations registry). PR Department of State: publishing a bulk export (or a documented paged API) would replace a multi-day rate-limited walk with a complete, verifiable snapshot — and would let anyone reproduce this analysis.

---

### 542 of 961 substations power nothing in the graph

<a id="substations-without-distribution-capability"></a>

- **id** `substations_without_distribution_capability`
- **Dataset** `graph.relationships (POWERS) / resilience.cascade_scores`
- **Source** HIFLD
- **Enforced at** `prism/graph/relationships.py:build_powers`

**What is excluded.** A substation only gets proximity-derived POWERS edges if its `cd_type` is Substation, Transmission Center or Generator AND its published `low_kv` is greater than zero. 559 of 961 fail one of those. 62 of the 559 still power barrios anyway, because F11f's measured feeder swap inserts `feeder_topology` edges without re-applying the capability filter — so the figure that matters is the 542 substations that end up with no POWERS edge at all. Only 422 are scored for cascade. The filter is repeated in three modules.

**Why.** A transmission-only or switching facility does not serve customers, and a substation with no published low-side voltage cannot be shown to. Attaching barrios to them would invent service that isn't there.

**Affects.**
- /resilience — 539 of 961 substations never appear in the cascade ranking
- every population-affected and hospitals-served figure
- the ILP portfolio (an unscored substation cannot be selected)
- /water and /telecom power-dependency scoring

**How much.** 402 of 961 substations pass the capability filter; 559 fail it, of which 62 nonetheless carry measured feeder edges. 542 end up with zero POWERS edges and 422 carry a cascade score. Of those failing, **69 pass the cd_type allowlist but carry low_kv 0 or NULL** — a published-field gap, not a real absence of distribution capability.

```sql
SELECT count(*) FROM graph.entities WHERE kind='substation' AND attrs->>'cd_type' IN ('Substation','Transmission Center','Generator') AND coalesce((attrs->>'low_kv')::float, 0) <= 0
```

**What would fix it** (HIFLD — Homeland Infrastructure Foundation-Level Data, LUMA Energy). HIFLD / LUMA: 69 substations are typed as distribution-capable yet publish a low-side voltage of zero or nothing at all. Each is a facility PRISM cannot connect to the customers it serves, and the gap is materially larger than the 14 unnamed substations already listed here. A populated `low_kv` would restore them to the cascade.

---

### Most water sources serve no barrios in the graph, so they score zero consequence

<a id="water-wells-zero-criticality"></a>

- **id** `water_wells_zero_criticality`
- **Dataset** `resilience.water_scores`
- **Source** PRASA/AAA network (PRISM-derived graph)
- **Enforced at** `prism/resilience/water.py`

**What is excluded.** The WATER_SERVES proxy graph has no service-area edges for wells or pump stations, so they carry criticality 0 and sink to the bottom of the water-risk ranking regardless of how much population actually depends on them. Wells are 43% of the affected set; pump stations are 57%.

**Why.** The mirrored network gives plant and source geometry but no service-area assignment for wells. PRISM scores consequence from measured service links and will not invent them.

**Affects.**
- /water source ranking and the water cascade
- water context on the parcel card and citizen card

**How much.** 1,234 of 2,153 scored water sources (57%) serve zero barrios: 706 pump stations, 527 wells, 1 plant

```sql
SELECT kind, count(*) FROM resilience.water_scores WHERE barrios_served = 0 GROUP BY 1 ORDER BY 2 DESC
```

**What would fix it** (AAA — Autoridad de Acueductos y Alcantarillados). AAA: a source-to-service-area mapping (which communities each well and intake supplies) is missing from the published network. Without it, more than half of the island's water sources cannot be ranked by who depends on them.

---

## Medium — narrows or biases a figure

### Fifteen barrios have no reachable hospital in the road graph

<a id="barrios-without-routable-hospital"></a>

- **id** `barrios_without_routable_hospital`
- **Dataset** `transport.road_access_cost`
- **Source** PRISM-derived (road graph)
- **Enforced at** `prism/transport/access.py`

**What is excluded.** Fifteen of 901 barrios return no nearest hospital: the islands (Vieques, Culebra) plus a handful of mainland barrios sitting on disconnected road-graph components. Nine of the fifteen have no reachable clinic either.

**Why.** Genuine graph disconnection, not a filter. The islands have no road link to the mainland; the mainland cases are gaps in the mirrored road network. PRISM shows a blank rather than routing to a hospital the resident cannot drive to.

**Affects.**
- citizen card emergency-access section for those barrios (shown blank, not zero)
- island-wide access statistics
- the ILP intervention catalog — a barrio with no travel time is skipped, so no road-access intervention can ever be proposed for it

**How much.** 15 of 901 barrios with no hospital route; 9 with neither hospital nor clinic

```sql
SELECT count(*) FROM transport.road_access_cost WHERE nearest_hosp_vid IS NULL
```

**What would fix it** (DTOP — Departamento de Transportación y Obras Públicas). DTOP: several mainland barrios sit on road-network components that are disconnected in the published centerline data — almost certainly a topology gap in the source rather than genuinely unreachable communities.

---

### A third of bridges have no measured span, and nothing costs them

<a id="bridge-missing-span-defaulted"></a>

- **id** `bridge_missing_span_defaulted`
- **Dataset** `transport.bridge_inventory.span_m`
- **Source** OpenStreetMap (FHWA NBI covers the rest)
- **Enforced at** `prism/assets/bridge.py:construction_cost`

**What is excluded.** 1,040 of 3,168 bridges carry no span. Two separate facts, and an earlier version of this entry conflated them: (a) the inventory's NULL spans have no consumer at all — nothing in `prism/` or `api/` joins `transport.bridge_inventory` to a cost model, so those bridges are absent from every cost estimate rather than priced badly; (b) the `Bridge` asset reachable through the Playground registry falls back to a 20 m span when a drawn bridge carries none (its form default is 30 m), which is an assumption on user input, not on this table.

**Why.** FHWA's NBI supplies a real span for the ~67% it covers; the rest are OSM geometries with no span tag, and PRISM will not invent one. Recorded here because a third of the island's mapped bridges being unmeasurable is a standing constraint on any future corridor costing, even though no live figure depends on it today.

**Affects.**
- the Playground's drawn-bridge cost estimate (a missing span reads as 20 m)
- nothing else — no corridor or portfolio figure reads this table today

**How much.** 1,040 of 3,168 bridges (33%) have a NULL span

```sql
SELECT count(*) FROM transport.bridge_inventory WHERE span_m IS NULL
```

**What would fix it** (FHWA — Federal Highway Administration (NBI), DTOP — Departamento de Transportación y Obras Públicas). FHWA / DTOP: a third of Puerto Rico's mapped bridges are absent from the National Bridge Inventory, so no published span exists for them. Extending NBI coverage — or publishing DTOP's own structure inventory — would replace the flat assumption with measurements.

---

### Layer checksums detect added or removed features, not edited ones

<a id="checksum-is-count-based"></a>

- **id** `checksum_is_count_based`
- **Dataset** `catalog/metadata.json`
- **Source** PRISM-derived (provenance)
- **Enforced at** `prism/sync/resync.py`

**What is excluded.** A mirrored layer's checksum is sha256("{layer}:{count}"), so a change that edits geometry or attributes without changing the feature count is not detected as a change.

**Why.** Full-content hashing across ~460 layers at every re-sync cost more than the cadence justified. Recorded here because it means "unchanged" is a weaker claim than it appears.

**Affects.**
- WhatsNew change detection and feed-freshness chips
- the auto-rescore trigger on hazard-layer change

**How much.** applies to all ~460 mirrored WFS layers

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Placeholder address segments are stripped before an address is displayed

<a id="crim-address-placeholder-junk"></a>

- **id** `crim_address_placeholder_junk`
- **Dataset** `crim.parcelas.direccion_fisica`
- **Source** CRIM
- **Enforced at** `prism/crim/normalize.py:_ADDR_JUNK_TOKENS`

**What is excluded.** Empty segments and the literal tokens ".", "PR", "PUERTO RICO", and the fake zip "00000" are removed from the comma-joined address template before display. A real 5-digit zip is always kept.

**Why.** CRIM writes the same placeholder template when a field is unset, producing strings like "BO CRUCES , ,., PR, Puerto Rico, 00000". Shown raw, they read as a corrupt product rather than a missing field.

**Affects.**
- every rendered parcel address (search rows, parcel card, owner drawer)
- the address string fed to the Census geocoder for the proposed-address label

**How much.** applies per-field across the fabric; not counted as a row exclusion

**What would fix it** (CRIM — Centro de Recaudación de Ingresos Municipales). CRIM: the physical-address field is populated with a placeholder template rather than left empty, which makes "has an address" indistinguishable from "has a blank address" without string inspection. Emitting NULL for unset fields would remove the ambiguity.

---

### Parcel rows with no catastro number are dropped from every derived view

<a id="crim-null-catastro-rows"></a>

- **id** `crim_null_catastro_rows`
- **Dataset** `crim.parcelas -> crim.parcelas_dedup / crim.parcelas_history`
- **Source** CRIM
- **Enforced at** `prism/crim/schema.py:_MATVIEW_DDL`

**What is excluded.** Rows in the raw parcel fabric where `num_catastro` is NULL. Both derived materialized views filter them (`WHERE num_catastro IS NOT NULL`), so they exist in the mirror but reach no view, no search, and no calculation.

**Why.** The catastro number is the join key for owners, valuation, sale history and every downstream table. A row without one cannot be attached to anything.

**Affects.**
- /parcels search, detail, and owner intelligence (everything reads the dedup view)
- /trends sales analytics
- monthly snapshots and parcel deltas
- the ~1.5M parcel count quoted on the landing page

**How much.** 38,229 of 1,536,079 raw parcel rows (2.5%)

```sql
SELECT count(*) FROM crim.parcelas WHERE num_catastro IS NULL
```

**What would fix it** (CRIM — Centro de Recaudación de Ingresos Municipales). CRIM: 38K parcel geometries in the published fabric carry no catastro number, so they cannot be joined to the valuation or ownership record. Assigning (or exposing) the catastro for these rows would recover them.

---

### Only the five most recent records per parcel enter the sale history

<a id="crim-sale-history-top5"></a>

- **id** `crim_sale_history_top5`
- **Dataset** `crim.parcelas_history`
- **Source** CRIM
- **Enforced at** `prism/crim/schema.py:_MATVIEW_DDL`

**What is excluded.** The history view keeps `sale_rank <= 5` — the five most recent records per catastro, ordered by objectid. Older records stay in `crim.parcelas` but reach no view.

**Why.** A bounded per-parcel history keeps the view small enough to index and serve; the parcel card shows recent transactions, not a full chain of title.

**Affects.**
- parcel-detail sale history
- /trends sales counts, medians, and municipio momentum
- the monthly report's recorded-sales section

**How much.** 138,216 records beyond rank 5 excluded (of 1,497,850 keyed rows)

```sql
SELECT count(*) FROM (SELECT row_number() OVER (PARTITION BY num_catastro ORDER BY objectid DESC) rk FROM crim.parcelas WHERE num_catastro IS NOT NULL) t WHERE rk > 5
```

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Substation-to-barrio links below a real service share are dropped

<a id="feeder-secondary-sliver-edges-dropped"></a>

- **id** `feeder_secondary_sliver_edges_dropped`
- **Dataset** `graph.relationships (POWERS, method='feeder_topology')`
- **Source** AEE/PREPA distribution feeder network
- **Enforced at** `prism/graph/feeders.py:SECONDARY_MIN_SHARE`

**What is excluded.** When the measured feeder network attaches a barrio to several substations, a secondary substation is kept only if its conductors carry at least 25% of the barrio's measured conductor length AND at least 1 km in absolute terms. Attachments below both thresholds are dropped.

**Why.** A barrio touches an average of 3.18 substations in the raw conductor data, much of it corner-clipping slivers. Without the floor, a peripheral substation is credited a barrio's entire population and its consequence score inflates.

**Affects.**
- substation consequence scores and /resilience rankings
- population-affected figures in every cascade view
- the ILP portfolio's protection-per-dollar ranking

**How much.** 1,036 of 4,419 POWERS edges are measured feeder topology

```sql
SELECT method, count(*) FROM graph.relationships WHERE rel_type='POWERS' GROUP BY 1
```

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Barrios whose measured substation is missing from the transmission graph keep the Voronoi proxy

<a id="feeds-isolated-substations-keep-voronoi"></a>

- **id** `feeds_isolated_substations_keep_voronoi`
- **Dataset** `graph.relationships (POWERS, method LIKE 'voronoi%')`
- **Source** PRISM-derived (proxy)
- **Enforced at** `prism/graph/feeders.py:swap_powers`

**What is excluded.** 19 substations are the measured primary feeder for at least one barrio yet have no FEEDS edge in the transmission graph. `swap_powers` skips those barrios, so their POWERS links stay on the Voronoi proxy — attached by nearest distance rather than by conductor. 101 barrios are affected, carrying 132 proxy edges from 39 distinct substations (the primaries plus the secondaries Voronoi also assigned).

**Why.** Swapping them would have dropped them out of upstream cascades entirely, trading a known proxy for a silent hole. Keeping the proxy is the lesser error, and it is labelled per-edge.

**Affects.**
- /resilience cascades through those 22 substations
- their barrios' civic-card power section
- any population-affected figure downstream of them

**How much.** 132 substation-to-barrio edges over 102 barrios remain Voronoi-derived (`voronoi_centroid` 102 + `voronoi_overlap` 30). The other 332 `voronoi`-method POWERS edges are point facilities and belong to `point_facilities_keep_voronoi_powers`, not here.

```sql
SELECT count(*) FROM graph.relationships r JOIN graph.entities e2 ON e2.entity_id = r.dst_entity WHERE r.rel_type = 'POWERS' AND e2.kind = 'barrio' AND r.method IN ('voronoi_centroid','voronoi_overlap')
```

**What would fix it** (LUMA Energy, AEE / PREPA — Autoridad de Energía Eléctrica). LUMA / AEE: 19 substations that PREPA's own conductor data shows feeding barrios do not appear in the published transmission topology, so their upstream connectivity cannot be established from public data — PRISM can see what they serve but not what serves them.

---

### Transmission links with equal or missing voltage produce no FEEDS edge

<a id="feeds-voltage-hierarchy-dropout"></a>

- **id** `feeds_voltage_hierarchy_dropout`
- **Dataset** `graph.relationships (FEEDS)`
- **Source** HIFLD
- **Enforced at** `prism/graph/relationships.py:build_feeds`

**What is excluded.** FEEDS edges are inferred by voltage hierarchy: a CONNECTS_TO pair whose two ends carry the same `high_kv`, or where either is missing, yields no directed edge — the code cannot tell which end feeds which.

**Why.** Direction is what makes a cascade traversable. Guessing it would send consequence flowing the wrong way through the grid, which is worse than a missing edge.

**Affects.**
- upstream cascade traversal from any affected substation
- the FEEDS-isolated substations (one of two causes — the other is the 200 m attach radius; `feeds_isolated_substations_keep_voronoi` describes the barrio-side consequence)

**How much.** 15 substations reach the transmission graph but never get a directed FEEDS edge, because the voltage on one or both ends of their CONNECTS_TO links is equal or missing. They are the minority of the 35 substations with no FEEDS edge at all — the other 20 never joined CONNECTS_TO (see `substations_beyond_transmission_attach_radius`).

```sql
SELECT count(*) FROM graph.entities e WHERE e.kind='substation' AND EXISTS (SELECT 1 FROM graph.relationships r WHERE r.rel_type='CONNECTS_TO' AND (r.src_entity = e.entity_id OR r.dst_entity = e.entity_id)) AND NOT EXISTS (SELECT 1 FROM graph.relationships r WHERE r.rel_type='FEEDS' AND (r.src_entity = e.entity_id OR r.dst_entity = e.entity_id))
```

**What would fix it** (HIFLD — Homeland Infrastructure Foundation-Level Data, LUMA Energy). HIFLD / LUMA: transmission line records do not state direction of flow, and voltage is missing on enough endpoints that it cannot always be inferred. A published from/to or a complete voltage field would remove the ambiguity.

---

### Anything short of a single exact geocoder match is treated as no match

<a id="geocode-ambiguous-match-rejected"></a>

- **id** `geocode_ambiguous_match_rejected`
- **Dataset** `crim.geocode_cache`
- **Source** US Census Bureau PR geocoder
- **Enforced at** `prism/crim/geocode.py`

**What is excluded.** Only the geocoder's single-exact-match tier is accepted. Zero matches and multiple/tie matches both collapse to an honest "no confident match" — PRISM never picks between candidates.

**Why.** Choosing among ties would silently put a resident on the wrong parcel. The cost of the strict policy is a lower hit rate, which is visible and recoverable; the cost of guessing is invisible and is not.

**Affects.**
- /parcels "search by address"
- the Tier A Census-matched proposed-address label

**How much.** 53 of 74 cached queries returned no confident match (72%)

```sql
SELECT count(*) FROM crim.geocode_cache WHERE match_tier <> 'match'
```

**What would fix it** (US Census Bureau, Junta de Planificación). Census Bureau / PR Planning Board: the PR geocoder resolves clean urban street addresses but misses urbanizacion- and barrio-style addressing, which is how a large share of the island is actually addressed.

---

### Hospital access routes only to true hospitals, excluding clinics that carry a hospital kind

<a id="hospital-access-clasif-filter"></a>

- **id** `hospital_access_clasif_filter`
- **Dataset** `transport.road_access_cost`
- **Source** PR Department of Health facility inventory
- **Enforced at** `prism/transport/access.py`

**What is excluded.** The destination set for hospital routing is `kind='hospital' AND clasif='HOSP'`. That excludes three rows carrying kind='hospital' with a primary-care clasif, and excludes kind='health_center' entirely (124 entities), which includes university and CDT campus clinics with no emergency capacity.

**Why.** Before the filter, a university campus clinic was "the nearest hospital" for 12 barrios. A resident told to drive there in an emergency would arrive somewhere that cannot admit them.

**Affects.**
- citizen card "nearest hospital" and drive time
- /resilience hospital-count consequence figures
- emergency-access inputs to the objective function

**How much.** 66 of 69 hospital-kind entities qualify; 124 health centers excluded from hospital routing

```sql
SELECT count(*) FROM graph.entities WHERE kind='hospital' AND attrs->>'clasif' = 'HOSP'
```

**What would fix it** (Departamento de Salud). PR Department of Health: three facilities are classified as hospitals in the inventory while carrying a primary-care classification, and the facility taxonomy does not distinguish emergency capacity from primary care in a single field.

---

### Shared contracts are flagged, never divided between co-contractors

<a id="ocpr-shared-contracts-not-divided"></a>

- **id** `ocpr_shared_contracts_not_divided`
- **Dataset** `ocpr.contract_contractors`
- **Source** Oficina del Contralor de Puerto Rico
- **Enforced at** `prism/ocpr/footprint.py`

**What is excluded.** When a contract lists several contractors, the register bills the full amount to each one. PRISM does not split the value; it flags the row and names the co-contractors instead.

**Why.** The register does not publish per-contractor shares, so any split would be invented. A flagged full amount is honest; an invented share is not. All aggregates are deduplicated on (contract_id, contractor_key) so one firm spelled two ways cannot double-bill a single key.

**Affects.**
- the government-contracts section on the owner drawer
- the contractor-owner ranking totals

**How much.** 12,395 of 1,141,257 contracts have more than one distinct contractor key (1.1%)

```sql
SELECT count(*) FROM (SELECT contract_id FROM ocpr.contract_contractors GROUP BY contract_id HAVING count(DISTINCT contractor_key) > 1) t
```

**What would fix it** (Oficina del Contralor de Puerto Rico). Oficina del Contralor: the register does not record each co-contractor's share of a joint contract, so joint-award totals cannot be attributed. A share or role field would make them attributable.

---

### Approximate addresses can only cite numbered state highways

<a id="proposed-address-no-local-street-layer"></a>

- **id** `proposed_address_no_local_street_layer`
- **Dataset** `crim.parcel_proposed_address (Tier B)`
- **Source** OGP WFS — state highway segments
- **Enforced at** `prism/crim/proposed_address.py`

**What is excluded.** When the Census geocoder does not match, the composed address can only name a numbered state route (PR-xx) within 3 km. Municipal and local streets are in the mirrored roads table with no usable name field, so a parcel off a numbered route falls back to barrio + municipio with no street at all.

**Why.** PRISM will not fabricate a street name. An approximate label that says "Bo. Bejucos, Isabela" is honest; one that guesses a street is not.

**Affects.**
- the "Census Proposed Address" label on the parcel card

**How much.** 40 of 44 computed proposed addresses fell to Tier B (approximate)

```sql
SELECT count(*) FROM crim.parcel_proposed_address WHERE tier <> 'census_matched'
```

**What would fix it** (Junta de Planificación). PR Planning Board / municipalities: no named local-street layer is published for Puerto Rico. It is the single missing dataset behind PRISM's inability to give most parcels a street address.

---

### Placeholder registry addresses are excluded from the address layer

<a id="rce-address-sentinels"></a>

- **id** `rce_address_sentinels`
- **Dataset** `crim.rce_addresses`
- **Source** PR Department of State — corporations registry
- **Enforced at** `prism/crim/rce_match.py:_ADDRESS_SENTINELS`

**What is excluded.** Address blocks whose whole line reads UNKNOWN, N A, NA, NONE, NO DISPONIBLE, or DESCONOCIDO.

**Why.** Tens of thousands of rows literally read "UNKNOWN". Without the filter they collapse into a single address_key apparently "shared" by tens of thousands of unrelated entities — harmless while nothing clusters on address, a serious false signal the moment control-cluster analysis (F11d) does.

**Affects.**
- the registry address layer (1.26M rows)
- address-corroborated fuzzy owner matching
- any future control-cluster / shared-officer analysis

**How much.** 1,259,212 address rows survive the filter; the sentinel block was measured at ~51K rows when the filter was written

```sql
SELECT count(*) FROM crim.rce_addresses
```

**What would fix it** (Departamento de Estado — corporations registry). PR Department of State: a registered agent address is a statutory requirement, yet tens of thousands of active registrations carry a literal "UNKNOWN" in that field.

---

### A plausible-but-unconfirmed registry match is recorded as no match

<a id="rce-ambiguous-match-withdrawn"></a>

- **id** `rce_ambiguous_match_withdrawn`
- **Dataset** `crim.owner_rce_match`
- **Source** PR Department of State — corporations registry
- **Enforced at** `prism/crim/rce_match.py:_MIN_SIMILARITY`

**What is excluded.** A CRIM owner is linked to a registry entity only on an exact key, a token-sorted key, or a fuzzy match at similarity ≥ 0.85 that a shared address corroborates. A fuzzy match nothing corroborates (`fuzzy_unconfirmed`) or one whose runner-up is within 0.05 (`ambiguous`) is stored with its candidates but reported as no match.

**Why.** The same never-guess policy as the address geocoder: naming the wrong company as the owner of a parcel is a worse error than saying nothing, and it is invisible to the reader. The candidates are kept so the decision is auditable rather than discarded.

**Affects.**
- the corporate-registry section on the owner drawer and parcel card
- the dissolved-companies-still-holding-parcels standing signal
- the monthly change report's corporate-status section

**How much.** 645 owners with a plausible registry hit are withheld — 525 `fuzzy_unconfirmed` and 120 `ambiguous`, against 10,405 accepted matches (exact 9,945, fuzzy 321, token_sorted 139)

```sql
SELECT method, count(*) FROM crim.owner_rce_match GROUP BY 1 ORDER BY 2 DESC
```

**What would fix it** (Departamento de Estado — corporations registry, CRIM — Centro de Recaudación de Ingresos Municipales). Departamento de Estado / CRIM: neither register carries the other's identifier, so a corporation must be matched to its property by name. A shared entity identifier — the registration index recorded on the deed, or an EIN on both sides — would make the join exact and retire the fuzzy tier entirely.

---

### Twenty substations sit too far from any transmission line to join the graph

<a id="substations-beyond-transmission-attach-radius"></a>

- **id** `substations_beyond_transmission_attach_radius`
- **Dataset** `graph.relationships (CONNECTS_TO)`
- **Source** HIFLD
- **Enforced at** `prism/graph/relationships.py:SUBSTATION_ATTACH_M`

**What is excluded.** A substation joins the transmission network only if it lies within 200 m of a transmission-line node. 20 of 961 do not, so they are structurally absent from `CONNECTS_TO` and can never receive a FEEDS edge — no cascade can reach them and none can start from them upstream.

**Why.** The attach radius is a spatial join tolerance, not a claim about the world: HIFLD publishes substation points and line geometries from different surveys, and beyond a couple of hundred metres a "nearest line" is a guess. Widening it would attach substations to lines that do not serve them.

**Affects.**
- upstream cascade traversal (these substations have no upstream at all)
- the FEEDS-orphan count — 20 of the 35 orphans originate here, not in the voltage-hierarchy inference
- /resilience rankings for anything downstream of them

**How much.** 941 of 961 substations are in CONNECTS_TO; 20 are not. Together with the 15 that attach but never resolve a direction, they make up the 35 substations with no FEEDS edge in either direction.

```sql
SELECT count(*) FROM graph.entities e WHERE e.kind='substation' AND NOT EXISTS (SELECT 1 FROM graph.relationships r WHERE r.rel_type='CONNECTS_TO' AND (r.src_entity = e.entity_id OR r.dst_entity = e.entity_id))
```

**What would fix it** (HIFLD — Homeland Infrastructure Foundation-Level Data, LUMA Energy). HIFLD / LUMA: substation points and transmission-line geometries are published from separate surveys and do not always coincide, so 20 substations cannot be spatially joined to the network they belong to. A published line-to-substation connectivity table would remove the need to infer the join from geometry at all.

---

## Low — cosmetic or well-bounded

### Ask PRISM only excludes government owners when explicitly asked to

<a id="ask-government-owner-filter-opt-in"></a>

- **id** `ask_government_owner_filter_opt_in`
- **Dataset** `crim.parcelas_dedup (via the Ask SQL tool)`
- **Source** PRISM-derived (query behaviour)
- **Enforced at** `prism/ask/tools.py:parcel_query`

**What is excluded.** The natural-language query tool injects NOT ILIKE filters for municipio / autoridad / gobierno / departamento / administracion / john doe only when the user's question explicitly asks to exclude government owners.

**Why.** Silently excluding public bodies would answer a different question than the one asked. The filter is opt-in so "largest owners" means what it says.

**Affects.**
- /ask answers over the parcel fabric

**How much.** applied per-query; not a standing exclusion

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### The ACS mirror is skipped without an API key

<a id="census-acs-requires-api-key"></a>

- **id** `census_acs_requires_api_key`
- **Dataset** `Census ACS 5-year estimates`
- **Source** US Census Bureau
- **Enforced at** `prism/mirror/complements/census_acs.py`

**What is excluded.** The ACS complement pull is skipped entirely when CENSUS_API_KEY is unset.

**Why.** The endpoint requires a key; the pull fails loudly rather than mirroring a partial file.

**Affects.**
- SVI and per-tract demographics (already mirrored; this affects refreshes)

**How much.** environment-dependent

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Assessed-value changes under $1 are not recorded as deltas

<a id="crim-reassessment-noise-floor"></a>

- **id** `crim_reassessment_noise_floor`
- **Dataset** `crim.parcel_deltas`
- **Source** CRIM
- **Enforced at** `prism/crim/snapshots.py:_VALUE_CHANGE_MIN`

**What is excluded.** Month-over-month assessed-value changes below $1.00 in absolute terms.

**Why.** Sub-dollar movement is rounding, not reassessment; recording it would bury real changes.

**Affects.**
- monthly parcel deltas and the monthly change report
- WhatsNew crim_delta events

**How much.** not separately counted — the floor is applied at delta computation

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### CRIM's unknown-owner placeholder is filtered out of owner intelligence

<a id="crim-unknown-owner-sentinel"></a>

- **id** `crim_unknown_owner_sentinel`
- **Dataset** `crim.owner_entities`
- **Source** CRIM
- **Enforced at** `prism/crim/owners.py:_JOHN_DOE`

**What is excluded.** Owner entities whose name matches "%JOHN DOE%" — CRIM's placeholder for a parcel whose owner of record is unknown, written as "<MUNICIPIO> JOHN DOE".

**Why.** It is a placeholder, not a person or a company. Left in, it ranks as one of the island's largest "owners" and corrupts every top-owner rollup.

**Affects.**
- /parcels owner-mode search and the owner drawer
- top-owners-by-municipio and by-barrio rollups
- Ask PRISM owner_lookup answers
- corporate-registry matching (filtered again on the CRIM side)

**How much.** 78 of 887,708 owner entities (0.009%)

```sql
SELECT count(*) FROM crim.owner_entities WHERE display_name ILIKE '%JOHN DOE%'
```

**What would fix it** (CRIM — Centro de Recaudación de Ingresos Municipales). CRIM: the parcels behind these entries have no owner of record. They are the cleanest possible worklist for a title-research pass — a small, bounded set whose ownership is formally unknown rather than merely misspelled.

---

### Fourteen substations have a bare number where a name should be

<a id="hifld-unnamed-substations"></a>

- **id** `hifld_unnamed_substations`
- **Dataset** `graph.entities (kind='substation')`
- **Source** HIFLD
- **Enforced at** `upstream — no filter in PRISM`

**What is excluded.** Fourteen substations carry a name that is only digits (e.g. "6774"). They are NOT excluded from any calculation — they score, rank, and cascade normally — but they are unidentifiable to a reader.

**Why.** Upstream data gap. PRISM does not invent a name, so the display falls back to the number.

**Affects.**
- /resilience rankings and drawer titles
- the ⌘K palette and any substation-by-name search

**How much.** 14 of 961 substations

```sql
SELECT count(*) FROM graph.entities WHERE kind='substation' AND name ~ '^[0-9]+$'
```

**What would fix it** (HIFLD — Homeland Infrastructure Foundation-Level Data, LUMA Energy). HIFLD / LUMA: fourteen transmission substations in the published dataset have no facility name, only an identifier.

---

### The investment plan can only choose from the worst 200 substations and 100 barrios

<a id="ilp-catalog-top-n-cap"></a>

- **id** `ilp_catalog_top_n_cap`
- **Dataset** `optimize.portfolio_runs (via the intervention catalog)`
- **Source** PRISM-derived (deliberate model boundary)
- **Enforced at** `prism/optimize/catalog.py:build_catalog`

**What is excluded.** `build_catalog` offers interventions for the top 200 substations by scenario score, and `build_transport_catalog` for the 100 worst-access barrios. Everything below those cuts is absent from the ILP's decision space — it cannot be selected at any budget, however cheap or effective it would be.

**Why.** The ILP is exact, not heuristic, so its cost scales with the catalog. The cut is far below the point where anything ranked lower would be selected at the budgets modelled ($50M–$2B). Recorded because it is a real bound on the answer, not a display limit.

**Affects.**
- /portfolio — 222 of the 422 cascade-scored substations can never be picked
- the protection-per-dollar ranking (it ranks what was offered, not everything)

**How much.** 200 of 422 scored substations and 100 of 901 barrios enter the catalog

```sql
SELECT count(*) FROM resilience.cascade_scores
```

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Public bodies are excluded from the contractor-owner ranking unless toggled on

<a id="ocpr-government-excluded-by-default"></a>

- **id** `ocpr_government_excluded_by_default`
- **Dataset** `ocpr.government_keys`
- **Source** Oficina del Contralor de Puerto Rico
- **Enforced at** `prism/ocpr/footprint.py:top_contractor_owners`

**What is excluded.** Owner keys identified as public bodies are filtered out of the contractor-owner ranking by default. A toggle in the UI includes them.

**Why.** Government agencies are simultaneously the island's largest landowners and its largest contract counterparties, so they occupy every top slot and hide the private signal the ranking exists to show. Excluded by default, never hidden: the toggle is on the page.

**Affects.**
- the contractor-owner ranking panel on /parcels

**How much.** 1,172 government owner keys

```sql
SELECT count(*) FROM ocpr.government_keys
```

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Reported generation capacity excludes PPOA renewables

<a id="prepa-capacity-excludes-ppoa"></a>

- **id** `prepa_capacity_excludes_ppoa`
- **Dataset** `sync.generation_status`
- **Source** PREPA
- **Enforced at** `prism/sync/prepa_ops.py`

**What is excluded.** PPOA (power purchase and operating agreement) renewable capacity is not counted in the capacity figure.

**Why.** The upstream feed reports it separately from dispatchable capacity.

**Affects.**
- the generation panel on the overview
- island generation context on the citizen card

**How much.** per-snapshot; not a row exclusion

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### High-density addresses are flagged as agent offices, not treated as shared control

<a id="rce-agent-office-addresses"></a>

- **id** `rce_agent_office_addresses`
- **Dataset** `crim.rce_address_entities`
- **Source** PR Department of State — corporations registry
- **Enforced at** `prism/crim/rce_match.py:AGENT_OFFICE_THRESHOLD`

**What is excluded.** Addresses hosting 10 or more distinct registered entities are flagged `is_agent_office` and are excluded from being read as evidence that those entities are related. They are kept and shown, not deleted.

**Why.** A law firm or registered-agent service is the address of record for hundreds of unrelated companies. Two or three entities at one address suggests a real shared principal; two hundred suggests a mailbox.

**Affects.**
- address-corroborated fuzzy owner matching
- any future control-cluster analysis (F11d, parked)

**How much.** 929 of 445,988 distinct addresses flagged, covering 25,447 entity registrations

```sql
SELECT count(*) FROM crim.rce_address_entities WHERE is_agent_office
```

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Registry rows named "UNKNOWN ENTITY" are excluded from owner matching

<a id="rce-unknown-entity-sentinel"></a>

- **id** `rce_unknown_entity_sentinel`
- **Dataset** `crim.rce_entities -> crim.owner_rce_match`
- **Source** PR Department of State — corporations registry
- **Enforced at** `prism/crim/rce_match.py:_REGISTRY_SENTINEL`

**What is excluded.** Registry entities whose corporate name begins with the literal "UNKNOWN ENTITY".

**Why.** The registry's own placeholder. Thousands of rows share the exact same string, so without an explicit filter they collapse into one match key that would "match" a large share of CRIM owners at once.

**Affects.**
- the corporate-registry section on the owner drawer and parcel card
- the dissolved-companies-still-holding-parcels standing signal
- WhatsNew registry status events

**How much.** 7,616 of 324,281 mirrored registry entities (2.3%)

```sql
SELECT count(*) FROM crim.rce_entities WHERE corp_name ILIKE 'UNKNOWN ENTITY%'
```

**What would fix it** (Departamento de Estado — corporations registry). PR Department of State: 7,616 register entries carry no entity name. They are real registration indices with an unusable name field.

---

### Fiber conduits are mirrored but excluded from every telecom view

<a id="telecom-no-fiber-layer"></a>

- **id** `telecom_no_fiber_layer`
- **Dataset** `g37_telecom_conductos_fibra_optica_act_2012`
- **Source** PRITS / OGP WFS
- **Enforced at** `not surfaced — BACKLOG "Fiber layer + real callsign coverage"`

**What is excluded.** The mirrored fiber-conduit layer is not surfaced on /telecom or used in any score.

**Why.** Fiber conduits have no power dependency in PRISM's cascade model, so drawing them would be decoration presented as analysis. Deferred deliberately rather than silently dropped from "towers/fiber".

**Affects.**
- /telecom (the layer is absent from the map and from coverage-loss scoring)

**How much.** 50 conduit MultiLineStrings mirrored, 0 surfaced

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

### Telecom assets carry zero cascade weight by design

<a id="telecom-zero-cascade-criticality"></a>

- **id** `telecom_zero_cascade_criticality`
- **Dataset** `graph.entities (telecom kinds)`
- **Source** PRISM-derived (deliberate model boundary)
- **Enforced at** `prism/graph/telecom.py`

**What is excluded.** Telecom towers and cell sites carry cascade CRITICALITY = 0, and downstream traversal follows FEEDS edges plus at most one POWERS hop.

**Why.** Telecom shares the POWERS relation with the power graph. Without the firewall, telecom assets would inflate substation and water consequence scores by being counted as downstream dependents of the grid. This is a modelling decision, not a data defect — recorded here because it is a real exclusion from a calculation.

**Affects.**
- substation consequence scores (/resilience)
- water-source power-dependency scoring

**How much.** 905 telecom entities scored on their own axis, excluded from power/water cascade weight

```sql
SELECT count(*) FROM resilience.telecom_scores
```

**What would fix it.** Nothing upstream — this is a PRISM modelling choice, recorded because it is a real exclusion from a calculation.

---

## For the institutions

Grouped by who could close the gap — which is not always the same body as the
one that publishes the affected dataset: several of these sit in PRISM-derived
tables whose root cause is a dataset another agency has never published.

### AAA — Autoridad de Acueductos y Alcantarillados

- **Most water sources serve no barrios in the graph, so they score zero consequence** — 1,234 of 2,153 scored water sources (57%) serve zero barrios: 706 pump stations, 527 wells, 1 plant.
  AAA: a source-to-service-area mapping (which communities each well and intake supplies) is missing from the published network. Without it, more than half of the island's water sources cannot be ranked by who depends on them.

### AEE / PREPA — Autoridad de Energía Eléctrica

- **Barrios whose measured substation is missing from the transmission graph keep the Voronoi proxy** — 132 substation-to-barrio edges over 102 barrios remain Voronoi-derived (`voronoi_centroid` 102 + `voronoi_overlap` 30). The other 332 `voronoi`-method POWERS edges are point facilities and belong to `point_facilities_keep_voronoi_powers`, not here..
  LUMA / AEE: 19 substations that PREPA's own conductor data shows feeding barrios do not appear in the published transmission topology, so their upstream connectivity cannot be established from public data — PRISM can see what they serve but not what serves them.

### CRIM — Centro de Recaudación de Ingresos Municipales

- **Two thirds of recorded "ownership changes" are the same owner written differently** — 2026-07 delta, a true partition of 7,722 owner-field changes: 2,178 substantive + 242 first-recorded (the 2,420 headline) + 2,598 spacing/punctuation-only + 2,704 the same name reordered. Of the reordered, 1,005 are the JOHN DOE unknown-owner sentinel rewritten (`JOHN DOE` -> `DOE JOHN`), which is placeholder churn rather than any kind of transfer — see `crim_unknown_owner_sentinel`..
  CRIM: the owner field is not normalized at entry, so the same person is stored with varying spacing and with surname and given name in either order. Anyone differencing successive published snapshots — which is the only way to observe transfers, since the register publishes current state only — will read roughly three times as many transfers as occurred.
- **196,132 duplicate parcel rows are collapsed by "highest objectid wins"** — 196,132 of 1,497,850 keyed rows collapsed (13.1%).
  CRIM: the published fabric contains ~196K duplicate catastro rows with no field marking which is current, so any consumer must invent a tie-break. A currency flag, or a de-duplicated publication, would make every downstream count reproducible instead of convention-dependent.
- **Implausible sale amounts and dates are excluded from every sale figure** — 570,923 of the 836,108 rows carrying a sale amount survive both bounds, so 265,185 recorded sales (31.7%) are excluded from every sale figure PRISM prints. The sub-counts overlap and do not partition it: 257,559 fail the amount bound, 18,596 carry a date outside the window, and a further tranche carry no sale date at all, which the BETWEEN also excludes..
  CRIM: roughly a third of recorded sale amounts are outside any plausible range — a mix of $0/$1 nominal transfers and corrupt magnitudes. A validation rule at entry, and a flag distinguishing nominal transfers from arm's-length sales, would make the price series usable as published.
- **Placeholder address segments are stripped before an address is displayed** — applies per-field across the fabric; not counted as a row exclusion.
  CRIM: the physical-address field is populated with a placeholder template rather than left empty, which makes "has an address" indistinguishable from "has a blank address" without string inspection. Emitting NULL for unset fields would remove the ambiguity.
- **Parcel rows with no catastro number are dropped from every derived view** — 38,229 of 1,536,079 raw parcel rows (2.5%).
  CRIM: 38K parcel geometries in the published fabric carry no catastro number, so they cannot be joined to the valuation or ownership record. Assigning (or exposing) the catastro for these rows would recover them.
- **A plausible-but-unconfirmed registry match is recorded as no match** — 645 owners with a plausible registry hit are withheld — 525 `fuzzy_unconfirmed` and 120 `ambiguous`, against 10,405 accepted matches (exact 9,945, fuzzy 321, token_sorted 139).
  Departamento de Estado / CRIM: neither register carries the other's identifier, so a corporation must be matched to its property by name. A shared entity identifier — the registration index recorded on the deed, or an EIN on both sides — would make the join exact and retire the fuzzy tier entirely.
- **CRIM's unknown-owner placeholder is filtered out of owner intelligence** — 78 of 887,708 owner entities (0.009%).
  CRIM: the parcels behind these entries have no owner of record. They are the cleanest possible worklist for a title-research pass — a small, bounded set whose ownership is formally unknown rather than merely misspelled.

### DTOP — Departamento de Transportación y Obras Públicas

- **Fifteen barrios have no reachable hospital in the road graph** — 15 of 901 barrios with no hospital route; 9 with neither hospital nor clinic.
  DTOP: several mainland barrios sit on road-network components that are disconnected in the published centerline data — almost certainly a topology gap in the source rather than genuinely unreachable communities.
- **A third of bridges have no measured span, and nothing costs them** — 1,040 of 3,168 bridges (33%) have a NULL span.
  FHWA / DTOP: a third of Puerto Rico's mapped bridges are absent from the National Bridge Inventory, so no published span exists for them. Extending NBI coverage — or publishing DTOP's own structure inventory — would replace the flat assumption with measurements.

### Departamento de Estado — corporations registry

- **The registry mirror is a partial walk, so a missing match is not proof of no registration** — 324,281 entities mirrored of an estimated ~560,000.
  PR Department of State: publishing a bulk export (or a documented paged API) would replace a multi-day rate-limited walk with a complete, verifiable snapshot — and would let anyone reproduce this analysis.
- **Placeholder registry addresses are excluded from the address layer** — 1,259,212 address rows survive the filter; the sentinel block was measured at ~51K rows when the filter was written.
  PR Department of State: a registered agent address is a statutory requirement, yet tens of thousands of active registrations carry a literal "UNKNOWN" in that field.
- **A plausible-but-unconfirmed registry match is recorded as no match** — 645 owners with a plausible registry hit are withheld — 525 `fuzzy_unconfirmed` and 120 `ambiguous`, against 10,405 accepted matches (exact 9,945, fuzzy 321, token_sorted 139).
  Departamento de Estado / CRIM: neither register carries the other's identifier, so a corporation must be matched to its property by name. A shared entity identifier — the registration index recorded on the deed, or an EIN on both sides — would make the join exact and retire the fuzzy tier entirely.
- **Registry rows named "UNKNOWN ENTITY" are excluded from owner matching** — 7,616 of 324,281 mirrored registry entities (2.3%).
  PR Department of State: 7,616 register entries carry no entity name. They are real registration indices with an unusable name field.

### Departamento de Salud

- **Hospital access routes only to true hospitals, excluding clinics that carry a hospital kind** — 66 of 69 hospital-kind entities qualify; 124 health centers excluded from hospital routing.
  PR Department of Health: three facilities are classified as hospitals in the inventory while carrying a primary-care classification, and the facility taxonomy does not distinguish emergency capacity from primary care in a single field.

### FHWA — Federal Highway Administration (NBI)

- **A third of bridges have no measured span, and nothing costs them** — 1,040 of 3,168 bridges (33%) have a NULL span.
  FHWA / DTOP: a third of Puerto Rico's mapped bridges are absent from the National Bridge Inventory, so no published span exists for them. Extending NBI coverage — or publishing DTOP's own structure inventory — would replace the flat assumption with measurements.

### HIFLD — Homeland Infrastructure Foundation-Level Data

- **542 of 961 substations power nothing in the graph** — 402 of 961 substations pass the capability filter; 559 fail it, of which 62 nonetheless carry measured feeder edges. 542 end up with zero POWERS edges and 422 carry a cascade score. Of those failing, **69 pass the cd_type allowlist but carry low_kv 0 or NULL** — a published-field gap, not a real absence of distribution capability..
  HIFLD / LUMA: 69 substations are typed as distribution-capable yet publish a low-side voltage of zero or nothing at all. Each is a facility PRISM cannot connect to the customers it serves, and the gap is materially larger than the 14 unnamed substations already listed here. A populated `low_kv` would restore them to the cascade.
- **Transmission links with equal or missing voltage produce no FEEDS edge** — 15 substations reach the transmission graph but never get a directed FEEDS edge, because the voltage on one or both ends of their CONNECTS_TO links is equal or missing. They are the minority of the 35 substations with no FEEDS edge at all — the other 20 never joined CONNECTS_TO (see `substations_beyond_transmission_attach_radius`)..
  HIFLD / LUMA: transmission line records do not state direction of flow, and voltage is missing on enough endpoints that it cannot always be inferred. A published from/to or a complete voltage field would remove the ambiguity.
- **Twenty substations sit too far from any transmission line to join the graph** — 941 of 961 substations are in CONNECTS_TO; 20 are not. Together with the 15 that attach but never resolve a direction, they make up the 35 substations with no FEEDS edge in either direction..
  HIFLD / LUMA: substation points and transmission-line geometries are published from separate surveys and do not always coincide, so 20 substations cannot be spatially joined to the network they belong to. A published line-to-substation connectivity table would remove the need to infer the join from geometry at all.
- **Fourteen substations have a bare number where a name should be** — 14 of 961 substations.
  HIFLD / LUMA: fourteen transmission substations in the published dataset have no facility name, only an identifier.

### Junta de Planificación

- **Anything short of a single exact geocoder match is treated as no match** — 53 of 74 cached queries returned no confident match (72%).
  Census Bureau / PR Planning Board: the PR geocoder resolves clean urban street addresses but misses urbanizacion- and barrio-style addressing, which is how a large share of the island is actually addressed.
- **Approximate addresses can only cite numbered state highways** — 40 of 44 computed proposed addresses fell to Tier B (approximate).
  PR Planning Board / municipalities: no named local-street layer is published for Puerto Rico. It is the single missing dataset behind PRISM's inability to give most parcels a street address.

### LUMA Energy

- **Point facilities are still attached to substations by proximity, not by conductor** — 3,251 of 4,419 POWERS edges (73.6%) attach a point facility by distance, written by two code paths: `nearest_dist_sub` (2,919 — 1,487 water pump stations, 798 telecom towers, 527 wells, 107 cell sites) and `voronoi` (332 — 139 water plants, 124 health centers, 69 hospitals). The hospitals and water plants named above are in the second group..
  LUMA: a service-point-to-feeder mapping (which customer account sits on which circuit) is the single dataset that would convert most of PRISM's remaining proxy edges into measured ones.
- **542 of 961 substations power nothing in the graph** — 402 of 961 substations pass the capability filter; 559 fail it, of which 62 nonetheless carry measured feeder edges. 542 end up with zero POWERS edges and 422 carry a cascade score. Of those failing, **69 pass the cd_type allowlist but carry low_kv 0 or NULL** — a published-field gap, not a real absence of distribution capability..
  HIFLD / LUMA: 69 substations are typed as distribution-capable yet publish a low-side voltage of zero or nothing at all. Each is a facility PRISM cannot connect to the customers it serves, and the gap is materially larger than the 14 unnamed substations already listed here. A populated `low_kv` would restore them to the cascade.
- **Barrios whose measured substation is missing from the transmission graph keep the Voronoi proxy** — 132 substation-to-barrio edges over 102 barrios remain Voronoi-derived (`voronoi_centroid` 102 + `voronoi_overlap` 30). The other 332 `voronoi`-method POWERS edges are point facilities and belong to `point_facilities_keep_voronoi_powers`, not here..
  LUMA / AEE: 19 substations that PREPA's own conductor data shows feeding barrios do not appear in the published transmission topology, so their upstream connectivity cannot be established from public data — PRISM can see what they serve but not what serves them.
- **Transmission links with equal or missing voltage produce no FEEDS edge** — 15 substations reach the transmission graph but never get a directed FEEDS edge, because the voltage on one or both ends of their CONNECTS_TO links is equal or missing. They are the minority of the 35 substations with no FEEDS edge at all — the other 20 never joined CONNECTS_TO (see `substations_beyond_transmission_attach_radius`)..
  HIFLD / LUMA: transmission line records do not state direction of flow, and voltage is missing on enough endpoints that it cannot always be inferred. A published from/to or a complete voltage field would remove the ambiguity.
- **Twenty substations sit too far from any transmission line to join the graph** — 941 of 961 substations are in CONNECTS_TO; 20 are not. Together with the 15 that attach but never resolve a direction, they make up the 35 substations with no FEEDS edge in either direction..
  HIFLD / LUMA: substation points and transmission-line geometries are published from separate surveys and do not always coincide, so 20 substations cannot be spatially joined to the network they belong to. A published line-to-substation connectivity table would remove the need to infer the join from geometry at all.
- **Fourteen substations have a bare number where a name should be** — 14 of 961 substations.
  HIFLD / LUMA: fourteen transmission substations in the published dataset have no facility name, only an identifier.

### Oficina del Contralor de Puerto Rico

- **Shared contracts are flagged, never divided between co-contractors** — 12,395 of 1,141,257 contracts have more than one distinct contractor key (1.1%).
  Oficina del Contralor: the register does not record each co-contractor's share of a joint contract, so joint-award totals cannot be attributed. A share or role field would make them attributable.

### US Census Bureau

- **Anything short of a single exact geocoder match is treated as no match** — 53 of 74 cached queries returned no confident match (72%).
  Census Bureau / PR Planning Board: the PR geocoder resolves clean urban street addresses but misses urbanizacion- and barrio-style addressing, which is how a large share of the island is actually addressed.
