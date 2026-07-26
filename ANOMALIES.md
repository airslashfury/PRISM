<!-- GENERATED FROM config/anomalies.yml — DO NOT EDIT. Run `make anomalies`. -->

# PRISM — Excluded and Anomalous Data

Every place PRISM excludes, filters, caps, or sets aside source data before it
reaches a view or a calculation. Each entry names what is excluded, why, the code
path that enforces it, which parts of the product are affected, the measured size
of the exclusion, and — where there is one — what the source institution would
have to fix.

The exclusions are individually defensible. Together they are a data-quality
report: 16 of the 27 entries below describe a defect in
published government data rather than a modelling choice, and each of those names
the institution that could close it.

**PRISM's rule:** when data is set aside, it is said out loud. Nothing here is a
reason to distrust a figure PRISM prints — it is the accounting behind why that
figure is what it is.

Counts measured 2026-07-26. This file is generated from
[`config/anomalies.yml`](config/anomalies.yml) by `make anomalies` — edit the
registry, not this file.

## Summary

| Severity | Entries |
|---|---|
| High — materially affects conclusions PRISM draws | 4 |
| Medium — narrows or biases a figure | 12 |
| Low — cosmetic or well-bounded | 11 |
| **Total active** | **27** |

| # | Exclusion | Dataset | Severity |
|---|---|---|---|
| 1 | [Implausible sale amounts and dates are excluded from every price figure](#crim-sales-amount-outliers) | `crim.parcelas_history.salesamt / .salesdttm` | high |
| 2 | [Point facilities are still attached to substations by proximity, not by conductor](#point-facilities-keep-voronoi-powers) | `graph.relationships (POWERS, method='nearest_dist_sub')` | high |
| 3 | [The registry mirror is a partial walk, so a missing match is not proof of no registration](#rce-registry-mirror-incomplete) | `crim.rce_entities` | high |
| 4 | [Wells serve no barrios in the graph, so they score zero consequence](#water-wells-zero-criticality) | `resilience.water_scores` | high |
| 5 | [Fifteen barrios have no reachable hospital in the road graph](#barrios-without-routable-hospital) | `transport.road_access_cost` | medium |
| 6 | [Layer checksums detect added or removed features, not edited ones](#checksum-is-count-based) | `catalog/metadata.json` | medium |
| 7 | [Placeholder address segments are stripped before an address is displayed](#crim-address-placeholder-junk) | `crim.parcelas.direccion_fisica` | medium |
| 8 | [Parcel rows with no catastro number are dropped from every derived view](#crim-null-catastro-rows) | `crim.parcelas -> crim.parcelas_dedup / crim.parcelas_history` | medium |
| 9 | [Only the five most recent records per parcel enter the sale history](#crim-sale-history-top5) | `crim.parcelas_history` | medium |
| 10 | [Substation-to-barrio links below a real service share are dropped](#feeder-secondary-sliver-edges-dropped) | `graph.relationships (POWERS, method='feeder_topology')` | medium |
| 11 | [Twenty-two substations missing from the transmission graph keep the Voronoi proxy](#feeds-isolated-substations-keep-voronoi) | `graph.relationships (POWERS, method LIKE 'voronoi%')` | medium |
| 12 | [Anything short of a single exact geocoder match is treated as no match](#geocode-ambiguous-match-rejected) | `crim.geocode_cache` | medium |
| 13 | [Hospital access routes only to true hospitals, excluding clinics that carry a hospital kind](#hospital-access-clasif-filter) | `transport.road_access_cost` | medium |
| 14 | [Shared contracts are flagged, never divided between co-contractors](#ocpr-shared-contracts-not-divided) | `ocpr.contract_contractors` | medium |
| 15 | [Approximate addresses can only cite numbered state highways](#proposed-address-no-local-street-layer) | `crim.parcel_proposed_address (Tier B)` | medium |
| 16 | [Placeholder registry addresses are excluded from the address layer](#rce-address-sentinels) | `crim.rce_addresses` | medium |
| 17 | [Ask PRISM only excludes government owners when explicitly asked to](#ask-government-owner-filter-opt-in) | `crim.parcelas_dedup (via the Ask SQL tool)` | low |
| 18 | [The ACS mirror is skipped without an API key](#census-acs-requires-api-key) | `Census ACS 5-year estimates` | low |
| 19 | [Assessed-value changes under $1 are not recorded as deltas](#crim-reassessment-noise-floor) | `crim.parcel_deltas` | low |
| 20 | [CRIM's unknown-owner placeholder is filtered out of owner intelligence](#crim-unknown-owner-sentinel) | `crim.owner_entities` | low |
| 21 | [Fourteen substations have a bare number where a name should be](#hifld-unnamed-substations) | `graph.entities (kind='substation')` | low |
| 22 | [Public bodies are excluded from the contractor-owner ranking unless toggled on](#ocpr-government-excluded-by-default) | `ocpr.government_keys` | low |
| 23 | [Reported generation capacity excludes PPOA renewables](#prepa-capacity-excludes-ppoa) | `sync.generation_status` | low |
| 24 | [High-density addresses are flagged as agent offices, not treated as shared control](#rce-agent-office-addresses) | `crim.rce_address_entities` | low |
| 25 | [Registry rows named "UNKNOWN ENTITY" are excluded from owner matching](#rce-unknown-entity-sentinel) | `crim.rce_entities -> crim.owner_rce_match` | low |
| 26 | [Fiber conduits are mirrored but excluded from every telecom view](#telecom-no-fiber-layer) | `g37_telecom_conductos_fibra_optica_act_2012` | low |
| 27 | [Telecom assets carry zero cascade weight by design](#telecom-zero-cascade-criticality) | `graph.entities (telecom kinds)` | low |

## High — materially affects conclusions PRISM draws

### Implausible sale amounts and dates are excluded from every price figure

<a id="crim-sales-amount-outliers"></a>

- **id** `crim_sales_amount_outliers`
- **Dataset** `crim.parcelas_history.salesamt / .salesdttm`
- **Source** CRIM
- **Enforced at** `prism/crim/trends.py:_SANE`

**What is excluded.** Price statistics only count sales with `salesamt` between $1,000 and $50,000,000 and `salesdttm` between 1980-01-01 and today. Everything outside those bounds is excluded from medians, momentum, and the market context on the parcel card.

**Why.** The raw column carries corrupt values — single "sales" of $10^13 — so sums and averages on it are meaningless. Only 287 sales island-wide exceed $50M and all inspected ones are data errors. Sale *counts* are clean and are not filtered.

**Affects.**
- /trends median sale price, momentum, hot-spot municipios
- municipio market context on the parcel card and /economy
- the monthly report's sales figures

**How much.** 257,559 of 836,108 rows with a sale amount fall outside the amount bounds (30.8%); 18,596 rows fall outside the date bounds

```sql
SELECT count(*) FROM crim.parcelas_history WHERE salesamt IS NOT NULL AND NOT (salesamt BETWEEN 1000 AND 50000000)
```

**What would fix it** (CRIM). CRIM: roughly a third of recorded sale amounts are outside any plausible range — a mix of $0/$1 nominal transfers and corrupt magnitudes. A validation rule at entry, and a flag distinguishing nominal transfers from arm's-length sales, would make the price series usable as published.

---

### Point facilities are still attached to substations by proximity, not by conductor

<a id="point-facilities-keep-voronoi-powers"></a>

- **id** `point_facilities_keep_voronoi_powers`
- **Dataset** `graph.relationships (POWERS, method='nearest_dist_sub')`
- **Source** PRISM-derived (proxy)
- **Enforced at** `prism/graph/relationships.py`

**What is excluded.** Hospitals, water plants, telecom towers and other point facilities are linked to the nearest distribution substation by distance. Only barrio population was switched to the measured feeder network (F11f).

**Why.** The feeder network gives conductor geometry, not service-point assignments, so which substation actually feeds a given building cannot be read off it. Distance is the honest available proxy and is tiered as one.

**Affects.**
- "serves N hospitals" figures throughout the cascade views
- /water and /telecom power-dependency scoring
- the citizen card's "same feed serves" line

**How much.** 2,919 of 4,419 POWERS edges (66%) are nearest-distance proxy

```sql
SELECT count(*) FROM graph.relationships WHERE rel_type='POWERS' AND method = 'nearest_dist_sub'
```

**What would fix it** (LUMA). LUMA: a service-point-to-feeder mapping (which customer account sits on which circuit) is the single dataset that would convert most of PRISM's remaining proxy edges into measured ones.

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

**What would fix it** (PR Department of State — corporations registry). PR Department of State: publishing a bulk export (or a documented paged API) would replace a multi-day rate-limited walk with a complete, verifiable snapshot — and would let anyone reproduce this analysis.

---

### Wells serve no barrios in the graph, so they score zero consequence

<a id="water-wells-zero-criticality"></a>

- **id** `water_wells_zero_criticality`
- **Dataset** `resilience.water_scores`
- **Source** PRASA/AAA network (PRISM-derived graph)
- **Enforced at** `prism/resilience/water.py`

**What is excluded.** The WATER_SERVES proxy graph has no well-to-barrio edges, so wells carry criticality 0 and sink to the bottom of the water-risk ranking regardless of how much population actually depends on them.

**Why.** The mirrored network gives plant and source geometry but no service-area assignment for wells. PRISM scores consequence from measured service links and will not invent them.

**Affects.**
- /water source ranking and the water cascade
- water context on the parcel card and citizen card

**How much.** 1,234 of 2,153 scored water sources serve zero barrios in the graph

```sql
SELECT count(*) FROM resilience.water_scores WHERE barrios_served = 0
```

**What would fix it** (AAA (Autoridad de Acueductos y Alcantarillados)). AAA: a source-to-service-area mapping (which communities each well and intake supplies) is missing from the published network. Without it, more than half of the island's water sources cannot be ranked by who depends on them.

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

**How much.** 15 of 901 barrios with no hospital route; 9 with neither hospital nor clinic

```sql
SELECT count(*) FROM transport.road_access_cost WHERE nearest_hosp_vid IS NULL
```

**What would fix it** (DTOP). DTOP: several mainland barrios sit on road-network components that are disconnected in the published centerline data — almost certainly a topology gap in the source rather than genuinely unreachable communities.

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

**What would fix it** (CRIM). CRIM: the physical-address field is populated with a placeholder template rather than left empty, which makes "has an address" indistinguishable from "has a blank address" without string inspection. Emitting NULL for unset fields would remove the ambiguity.

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

**What would fix it** (CRIM). CRIM: 38K parcel geometries in the published fabric carry no catastro number, so they cannot be joined to the valuation or ownership record. Assigning (or exposing) the catastro for these rows would recover them.

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

### Twenty-two substations missing from the transmission graph keep the Voronoi proxy

<a id="feeds-isolated-substations-keep-voronoi"></a>

- **id** `feeds_isolated_substations_keep_voronoi`
- **Dataset** `graph.relationships (POWERS, method LIKE 'voronoi%')`
- **Source** PRISM-derived (proxy)
- **Enforced at** `prism/graph/feeders.py:swap_powers`

**What is excluded.** Twenty-two source substations have no FEEDS edges in the transmission graph. Their barrio links were NOT swapped onto the measured feeder topology; they still use the Voronoi proxy, so their 102 barrios are attached by nearest- distance rather than by conductor.

**Why.** Swapping them would have dropped them out of upstream cascades entirely, trading a known proxy for a silent hole. Keeping the proxy is the lesser error, and it is labelled per-edge.

**Affects.**
- /resilience cascades through those 22 substations
- their barrios' civic-card power section
- any population-affected figure downstream of them

**How much.** 464 of 4,419 POWERS edges remain Voronoi-derived (voronoi/voronoi_centroid/voronoi_overlap)

```sql
SELECT count(*) FROM graph.relationships WHERE rel_type='POWERS' AND method LIKE 'voronoi%'
```

**What would fix it** (LUMA / AEE). LUMA / AEE: 22 substations appear in the facility inventory but not in the published transmission topology, so their upstream connectivity cannot be established from public data.

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

**What would fix it** (US Census Bureau / Junta de Planificación). Census Bureau / PR Planning Board: the PR geocoder resolves clean urban street addresses but misses urbanizacion- and barrio-style addressing, which is how a large share of the island is actually addressed.

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

**What would fix it** (PR Department of Health facility inventory). PR Department of Health: three facilities are classified as hospitals in the inventory while carrying a primary-care classification, and the facility taxonomy does not distinguish emergency capacity from primary care in a single field.

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

**What would fix it** (Junta de Planificación / municipalities). PR Planning Board / municipalities: no named local-street layer is published for Puerto Rico. It is the single missing dataset behind PRISM's inability to give most parcels a street address.

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

**What would fix it** (PR Department of State — corporations registry). PR Department of State: a registered agent address is a statutory requirement, yet tens of thousands of active registrations carry a literal "UNKNOWN" in that field.

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

**What would fix it** (CRIM). CRIM: the parcels behind these entries have no owner of record. They are the cleanest possible worklist for a title-research pass — a small, bounded set whose ownership is formally unknown rather than merely misspelled.

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

**What would fix it** (HIFLD). HIFLD / LUMA: fourteen transmission substations in the published dataset have no facility name, only an identifier.

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

**What would fix it** (PR Department of State — corporations registry). PR Department of State: 7,616 register entries carry no entity name. They are real registration indices with an unusable name field.

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

### AAA (Autoridad de Acueductos y Alcantarillados)

- **Wells serve no barrios in the graph, so they score zero consequence** — 1,234 of 2,153 scored water sources serve zero barrios in the graph.
  AAA: a source-to-service-area mapping (which communities each well and intake supplies) is missing from the published network. Without it, more than half of the island's water sources cannot be ranked by who depends on them.

### CRIM

- **Implausible sale amounts and dates are excluded from every price figure** — 257,559 of 836,108 rows with a sale amount fall outside the amount bounds (30.8%); 18,596 rows fall outside the date bounds.
  CRIM: roughly a third of recorded sale amounts are outside any plausible range — a mix of $0/$1 nominal transfers and corrupt magnitudes. A validation rule at entry, and a flag distinguishing nominal transfers from arm's-length sales, would make the price series usable as published.
- **Placeholder address segments are stripped before an address is displayed** — applies per-field across the fabric; not counted as a row exclusion.
  CRIM: the physical-address field is populated with a placeholder template rather than left empty, which makes "has an address" indistinguishable from "has a blank address" without string inspection. Emitting NULL for unset fields would remove the ambiguity.
- **Parcel rows with no catastro number are dropped from every derived view** — 38,229 of 1,536,079 raw parcel rows (2.5%).
  CRIM: 38K parcel geometries in the published fabric carry no catastro number, so they cannot be joined to the valuation or ownership record. Assigning (or exposing) the catastro for these rows would recover them.
- **CRIM's unknown-owner placeholder is filtered out of owner intelligence** — 78 of 887,708 owner entities (0.009%).
  CRIM: the parcels behind these entries have no owner of record. They are the cleanest possible worklist for a title-research pass — a small, bounded set whose ownership is formally unknown rather than merely misspelled.

### DTOP

- **Fifteen barrios have no reachable hospital in the road graph** — 15 of 901 barrios with no hospital route; 9 with neither hospital nor clinic.
  DTOP: several mainland barrios sit on road-network components that are disconnected in the published centerline data — almost certainly a topology gap in the source rather than genuinely unreachable communities.

### HIFLD

- **Fourteen substations have a bare number where a name should be** — 14 of 961 substations.
  HIFLD / LUMA: fourteen transmission substations in the published dataset have no facility name, only an identifier.

### Junta de Planificación / municipalities

- **Approximate addresses can only cite numbered state highways** — 40 of 44 computed proposed addresses fell to Tier B (approximate).
  PR Planning Board / municipalities: no named local-street layer is published for Puerto Rico. It is the single missing dataset behind PRISM's inability to give most parcels a street address.

### LUMA

- **Point facilities are still attached to substations by proximity, not by conductor** — 2,919 of 4,419 POWERS edges (66%) are nearest-distance proxy.
  LUMA: a service-point-to-feeder mapping (which customer account sits on which circuit) is the single dataset that would convert most of PRISM's remaining proxy edges into measured ones.

### LUMA / AEE

- **Twenty-two substations missing from the transmission graph keep the Voronoi proxy** — 464 of 4,419 POWERS edges remain Voronoi-derived (voronoi/voronoi_centroid/voronoi_overlap).
  LUMA / AEE: 22 substations appear in the facility inventory but not in the published transmission topology, so their upstream connectivity cannot be established from public data.

### Oficina del Contralor de Puerto Rico

- **Shared contracts are flagged, never divided between co-contractors** — 12,395 of 1,141,257 contracts have more than one distinct contractor key (1.1%).
  Oficina del Contralor: the register does not record each co-contractor's share of a joint contract, so joint-award totals cannot be attributed. A share or role field would make them attributable.

### PR Department of Health facility inventory

- **Hospital access routes only to true hospitals, excluding clinics that carry a hospital kind** — 66 of 69 hospital-kind entities qualify; 124 health centers excluded from hospital routing.
  PR Department of Health: three facilities are classified as hospitals in the inventory while carrying a primary-care classification, and the facility taxonomy does not distinguish emergency capacity from primary care in a single field.

### PR Department of State — corporations registry

- **The registry mirror is a partial walk, so a missing match is not proof of no registration** — 324,281 entities mirrored of an estimated ~560,000.
  PR Department of State: publishing a bulk export (or a documented paged API) would replace a multi-day rate-limited walk with a complete, verifiable snapshot — and would let anyone reproduce this analysis.
- **Placeholder registry addresses are excluded from the address layer** — 1,259,212 address rows survive the filter; the sentinel block was measured at ~51K rows when the filter was written.
  PR Department of State: a registered agent address is a statutory requirement, yet tens of thousands of active registrations carry a literal "UNKNOWN" in that field.
- **Registry rows named "UNKNOWN ENTITY" are excluded from owner matching** — 7,616 of 324,281 mirrored registry entities (2.3%).
  PR Department of State: 7,616 register entries carry no entity name. They are real registration indices with an unusable name field.

### US Census Bureau / Junta de Planificación

- **Anything short of a single exact geocoder match is treated as no match** — 53 of 74 cached queries returned no confident match (72%).
  Census Bureau / PR Planning Board: the PR geocoder resolves clean urban street addresses but misses urbanizacion- and barrio-style addressing, which is how a large share of the island is actually addressed.
