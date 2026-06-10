# ui-ux — PRISM interface writing skill

Use this skill when adding page descriptions, metric glosses, or "so what" framing to any PRISM dashboard page. It encodes the judgment needed to write copy that serves a planner, official, or resident — not a data engineer.

---

## North star

**"The objective is not to make decisions — it is to make the consequences of decisions easy to see."**

Every description, label, and aside should serve that goal. A number without consequence is noise. A consequence without a number is opinion. Give both.

---

## Rules

### 1. Lead with consequence, not metric

Bad: "Composite score: 84.10"
Good: "This substation's failure would cut power to ~88K people and 2 hospitals — the highest-risk node on the island."

Bad: "SVI: 0.83"
Good: "High vulnerability — this community has limited capacity to self-recover from disruption."

### 2. Answer "why should I care?" in the first sentence of any panel description

The first sentence of every page framing block or sidebar header should answer what's at stake for a real person, not describe the computation.

### 3. Pair every technical term with its plain-language meaning the first time it appears

Required glosses on first use:

| Term | Plain-language gloss |
|------|----------------------|
| SVI | Social Vulnerability Index — a composite of poverty rate, elderly share, disability rate, flood exposure, and terrain slope |
| VOLL | Value of Lost Load — estimated economic cost per person per year of power outage ($2,389/person over 30yr NPV) |
| Composite score | Risk score = hazard probability × cascade impact × (1 + network centrality) |
| Betweenness | How many shortest paths in the grid pass through this node — high = critical connector |
| Articulation point / SPOF | A node whose removal disconnects the grid — removing it isolates downstream facilities with no alternate path |
| NPV | Net Present Value — 30-year cost in today's dollars, accounting for discount rate |
| Objective score | Construction + maintenance (30yr NPV) + flood risk premium − SVI-weighted population value served. Lower = better societal value |
| ILP | Integer Linear Programming — exact optimization (not heuristic) that finds the best combination of interventions within a budget |

Use inline parentheticals or subtitle text for these glosses — not tooltips alone, which disappear on mobile and are easy to miss.

### 4. Use real named places and numbers, not abstractions

PRISM resolves entity names (substations, barrios, municipalities). Always cite real names when available:
- "PALO SECO SP TC (entity 915)" → prefer "Palo Seco"
- "barrio_id=883" → prefer the resolved barrio name

### 5. Tie back to the objective function on every score or ranking

Whenever a score, rank, or leaderboard appears, name which component of the objective drives it. The objective is:
minimize: construction + maintenance + property impact + environmental impact + disaster vulnerability
maximize: population benefit + economic benefit

Example: "Alt 1 ranks best because it has the lowest construction cost while serving 1.02M people — the population term outweighs Alt 3's 40% shorter distance through tunnel terrain."

### 6. "So what" framing on comparison tables and leaderboards

Don't leave the comparison implicit. After a ranking, add a one-liner that says what the difference means in human terms:
- "The top-ranked route costs $4.5B less than Alt 3 and serves 420K more people."
- "Equity-weighted allocation shifts 3 substations vs. the cost-only run — all 3 serve barrios with SVI > 0.9."
- "Every dollar of the $200M budget buys 2.5× more resilience uplift in the hardening category than in relocation."

---

## Per-page guidance

### Overview (`/`)
- Hero text should reference Puerto Rico by name and name the systems modeled.
- The "highest consequence node" card must cite downstream hospitals and people, not just the score.
- Module cards: lead with what a viewer discovers there, not what the module computes.

### Resilience (`/resilience`)
- Sidebar framing: explain that composite score = P(failure|event) × cascade × centrality. One sentence.
- Top-list callout: after the #1 entry, note how many hospitals and people it serves.
- Scenario toggle: explain briefly what Cat-3, SLR-2ft, and Combined mean in terms of the hazard type.

### Portfolio (`/portfolio`)
- Intervention types need inline glosses (elevation / hardening / relocation — what each does physically and when ILP prefers it).
- Efficiency frontier: label the axes "dollars deployed" and "resilience points gained" and add a note on what a resilience point is.
- Items table: after the top 5, note how many people are protected by the first $100M deployed.

### Economy (`/economy`)
- Sidebar header: explain VOLL and why circle size = risk exposure, not poverty.
- Map overlay: explain SVI components (5 factors) in the subtitle rather than just "mean · N tracts".
- High-SVI count line should say what it means to be at SVI ≥ 0.75.

### Corridor (`/corridor`)
- Objective score box already has "construction + maintenance + flood risk − population value served" — keep and extend.
- Terrain composition: explain *why* tunnel is 8× more expensive than standard (hard rock excavation vs. grading).
- "Best" badge: add a one-liner on what makes it best (e.g., "lowest cost per person served").

### Sync (`/sync`)
- Lead with why syncing matters to the model: stale flood zones = stale risk scores.
- "Triggered rescore" column: explain what a rescore does (re-evaluates all 315 substations against the new hazard boundary).
- Last-sync timestamp: add context — "PRISM re-fetches flood zones every 24 h; roads every 7 days."

---

## What NOT to do

- Don't rewrite the whole UI or add new pages — this skill is for copy/microcopy only.
- Don't add marketing language ("powerful", "advanced", "state-of-the-art").
- Don't duplicate labels — if a chart axis already says "Capital deployed ($M)", the card title doesn't need to repeat it.
- Don't add acronym expansions that are already expanded in the same visible region.
- Don't fabricate numbers — only use values derivable from the live data or CLAUDE.md phase log.
