# Research spike — external address-enrichment sources for Puerto Rico

**For:** PRISM — Puerto Rico Infrastructure Simulation Model
**Re:** F9b B5 — can an external address source fix CRIM addresses that don't geocode, or does
parcel geometry stay the canonical locator?
**Date:** 2026-07-09
**Type:** research memo, no code · **Verdict:** see §5

---

## 1. The question, precisely

F9b B2 shipped a `display_address()` composer (`prism/crim/normalize.py`) that strips CRIM
placeholder junk (`, ,., PR, Puerto Rico, 00000`), injects the municipio, and keeps only real ZIPs.
That makes the address *readable*. It does **not** make it *geocodable*: a repaired CRIM address
still may not resolve to a point on Google/Apple/Census. This spike evaluates whether an external
source — DOT National Address Database (NAD), OpenAddresses, Census TIGER/Line, USPS — can close that
gap, and recommends go/no-go on adopting one.

The load-bearing realization up front: **for PR this is not primarily a missing-dataset problem, it
is a structural-ambiguity problem.** That reframes every source below.

## 2. Why PR addresses resist geocoding (the structural constraint)

The U.S. Census Bureau has documented PR addressing at length; the facts that matter here:

- **~30% of PR dwellings have no formal address at all.** No amount of address data fixes a place
  that was never assigned an address.
- **Addresses are not unique without the *urbanización*.** The same street name + house number +
  ZIP recur across different urbanizaciones in the same postal code; the urbanización name is the
  required disambiguator. Standard `street, city, ZIP` geocoders have nothing to key on.
- **The Census Bureau has no spatial boundaries for urbanizaciones**, so even it cannot fully
  resolve urbanización-scoped addresses to geography.
- **The same address is written many ways** ("residents might write the same address six different
  ways") — free-text variance swamps naive matching.

Implication: an external *list of addresses* does not fix this. A geocoder that understands the PR
grammar (street + urb + municipio) helps at the margin, but the ceiling is set by the ~30% with no
address and the urbanización boundaries that don't exist. See §4.

## 3. Source-by-source assessment

### DOT National Address Database (NAD) — **no PR coverage**
USDOT compiles NAD from *voluntary* state/local/tribal submissions (~80M records). Participation is
uneven ("fully participating, partially participating, and non-participating"), and there is **no
evidence PR or any US territory submits or is covered** — territories do not appear in participation
listings. License is open government data (USDOT, no-warranty disclaimer), so it would be *usable* if
it existed — but there is nothing to pull for PR today. **Verdict: no value now.** Worth a re-check
only if the PR Address Data Working Group (a federal effort referenced by Census) later lands PR into
NAD.

### OpenAddresses — **loops back to CRIM**
Global open-address aggregator, coverage tracks government open-data releases. PR coverage is
effectively nil. The single PR issue in the project ([#2894](https://github.com/openaddresses/openaddresses/issues/2894),
opened 2017, **still open, no data merged**) identifies exactly one class of source: the CRIM/CRIMPR
ArcGIS cadastral services (`Tasaciones`, `ParcelasEtiquetas`) — **the same cadastral fabric PRISM
already mirrors as `crim.parcelas`.** So OpenAddresses would, at best, hand us back our own data.
**Verdict: no net-new. No adoption.**

### Census TIGER/Line address ranges — **public domain, coarse fallback**
TIGER/Line carries interpolated *address ranges* along PR road segments (public domain, already in
PRISM's federal-complement orbit). Useful only as a *street-level interpolation* fallback (place a
point somewhere along the correct block), not rooftop accuracy, and it inherits the urbanización
ambiguity. **Verdict: keep as a known fallback, not a primary fix.**

### Census Geocoder (PR-aware endpoint) — **the one genuinely useful net-new asset**
Census runs a **PR-specific geocoding endpoint** (`geocoding.geo.census.gov/geocoder/locations/addressPR`)
that accepts the PR grammar — minimum `street`, `urb`, `municipio` — and returns a point. Free,
keyless HTTP, public domain, no mirroring burden (call-time lookup). It is purpose-built for exactly
the repaired-address shape B2 now produces. It won't beat the structural ceiling (§2), but for the
subset of parcels that *do* carry a real street + urb it can attach a validated point and canonical
urb. **Verdict: viable as an optional, on-demand enrichment — not a spatial backbone.**

### USPS (AMS API / address data) — **license-incompatible, hard no**
USPS address matching (AMS API) requires a **signed annual paid license**, imposes **field-of-use
restrictions**, and **explicitly prohibits** using the data "to create a database … for third party
usage" or to "resell or license … the data." PRISM's model is *mirror everything locally and surface
it publicly with provenance* — categorically incompatible with those terms, before cost even enters.
**Verdict: hard no. Do not pursue.**

## 4. What this means for PRISM's locator strategy

PRISM already holds **1.53M CRIM parcel polygons with centroids at EPSG:32161** (`crim.parcelas`).
A parcel centroid is a *more reliable* "where is this ground" than any text-address geocode, because
it sidesteps the entire urbanización-ambiguity problem — it is authoritative geometry, not an
interpolated or matched guess. The text address is only needed as a *human-readable label*, which is
exactly what B2's `display_address()` already produces.

So the geocoding gap is narrower than it first looked: PRISM does not need to geocode addresses to
*place* things (it has the polygon). It would only benefit from geocoding to (a) let a user paste a
street address into search and land on the right parcel, and (b) validate/standardize the urb on a
display address. Both are enrichments on top of a locator that already works — not a foundation
PRISM is missing.

## 5. Recommendation (go/no-go)

**NO-GO on adopting any external address *database* as a new mirrored source.**
None of NAD, OpenAddresses, or USPS clears the bar: NAD has no PR coverage, OpenAddresses routes back
to the CRIM data PRISM already has, and USPS is license-incompatible with PRISM's open, locally
mirrored model. And none of them defeats the structural ambiguity (§2) that is the real cause of PR
geocoding failure.

**Parcel geometry (CRIM) stays the canonical locator** — confirmed, not merely defaulted-to. The
1.53M parcel polygons/centroids are the authoritative "where"; `display_address()` remains the right
approach for the readable label. This is the primary decision B5 was asked to make, and the answer is
**yes, parcel geometry is canonical.**

**CONDITIONAL GO — later, BACKLOG, optional:** the **Census PR geocoder** is the single worthwhile
external asset — free, keyless, public domain, PR-grammar-aware, no mirror burden. Recommend parking
it in `BACKLOG.md` as a *call-time enrichment* (address-paste search → nearest parcel; urb
validation on display), explicitly **not** as a spatial backbone and **not** F9b-blocking. TIGER/Line
address ranges are the coarse interpolation fallback if the geocoder misses.

**Re-check trigger:** if the federal *PR Address Data Working Group* (Census-referenced) later lands
PR into NAD with real coverage, re-evaluate NAD as a mirrored complement — until then it is empty for
PR.

## 6. Sources

- Census — [Street Addresses Are Simple, Right? Not in Puerto Rico](https://www.census.gov/library/stories/2020/01/street-addresses-are-simple-not-in-puerto-rico.html) (30%-no-address, urbanización uniqueness, six-ways variance)
- Census — [Creating Boundaries for Puerto Rico Urbanizaciones](https://www.census.gov/newsroom/blogs/random-samplings/2016/05/simple-tools-great-solutions-creating-boundaries-for-puerto-rico-urbanizaciones.html) (no urbanización spatial boundaries)
- Census — [Local Address Data in Puerto Rico / Opportunity Project](https://opportunity.census.gov/data/addressing/) (PR Address Data Working Group, federal initiatives)
- Census — [PR-parsed geocoder endpoint](https://geocoding.geo.census.gov/geocoder/locations/addressPR) (street+urb+municipio)
- USDOT — [National Address Database overview](https://www.transportation.gov/gis/national-address-database) (voluntary participation, uneven coverage)
- OpenAddresses — [PR sources issue #2894](https://github.com/openaddresses/openaddresses/issues/2894) (open since 2017, routes back to CRIM/CRIMPR)
- USPS — [AMS API licensing fees](https://postalpro.usps.com/ams-api/AMS_API_FEES) and [license agreement](https://postalpro.usps.com/ams-api/License_Agreement) (paid, signed, no-third-party-database, no-resell)
