"""Control-cluster merge over the PR corporations registry (ROADMAP F11d).

F11b already links a CRIM owner to the registry entity behind it by *name*.
This module asks a different question: do two (or more) registry entities —
possibly matched to two *different* CRIM owner_keys, which today look like
unrelated landowners — share the same controlling natural person? If so,
"Owner A" and "Owner B" may be the same operator working through separate
shell LLCs, which is exactly the pattern CRIM's owner-of-record field cannot
show.

**There is no `relatedEntities` field.** The roadmap item that scheduled this
work assumed the registry API exposed one; a full-key sweep of every mirrored
`raw` payload (`jsonb_object_keys(raw)` across a 5% sample and, separately,
`DISTINCT` over the whole mirror) turns up `officers`, `incorporators`,
`residentAgent`, and address blocks, but no `relatedEntities` key at any
nesting level. So the only structured control signal the mirror actually
carries is **individual officer/incorporator identity** — which is what the
roadmap itself named as the *primary* signal, with address as a corroborator,
so this is a narrowing of scope to what's real, not a design change.

**Naive transitive clustering does not work — measured, not assumed.** The
first cut unioned any two entities sharing one non-frequent-filer person (the
address layer's `AGENT_OFFICE_THRESHOLD` pattern, applied to names). Run
against the live mirror (2026-08 snapshot, ~386K entities) that produced a
2,317-entity connected component and a single cluster spanning 106 distinct
CRIM owner_keys — an accountant, notary, or secondary officer who sits on a
handful of unrelated boards bridges otherwise-unrelated corporate families
the moment transitive closure is taken across *any* shared person. Requiring
**two or more** shared, non-frequent-filer people between a pair of entities
before they are linked (`MIN_SHARED_PEOPLE`) collapsed the largest cluster to
13 entities and left 138 clusters that genuinely span more than one CRIM
owner_key — coherent groups ("MTPR WAREHOUSE ⋯" x6, "OLV / OLIVE VILLA /
O:LIVE HOTEL" x5) rather than name-collision noise. See
`config/anomalies.yml:control_cluster_single_officer_bridge` for the measured
before/after.

Everything here is `proxy` tier, one further inferential step past F11b's
already-`proxy` name match: two shell companies sharing two named individuals
is strong evidence of common control, not proof of it (the same two people
could legitimately co-found unrelated ventures). Copy must say "shares
officers with", never "is owned by" or "is the same as".
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.normalize import _NON_ALNUM, _WS, _fold_accents
from prism.crim.rce_match import MATCH_TIER

log = logging.getLogger(__name__)

CLUSTER_TIER = MATCH_TIER   # proxy — one inferential step past an already-proxy name match

# A person appearing as officer/incorporator on more mirrored entities than this
# is a professional filer/signer (a formation service's own staff, a repeat
# notary) — not a real principal. Mirrors `rce_match.AGENT_OFFICE_THRESHOLD`
# exactly, same reasoning, applied to a person instead of an address. Measured
# live: the two most frequent names sit at 1,098 and 743 mirrored entities —
# unmistakably a filing service, not a beneficial owner.
FREQUENT_FILER_THRESHOLD = 10

# Two entities are linked only when they share at least this many distinct,
# non-frequent-filer people. See the module docstring for the measured
# before/after that makes this a load-bearing constant rather than a tuning
# knob: 1 collapses unrelated corporate families into one blob, 2 does not.
MIN_SHARED_PEOPLE = 2


# ── Schema ──────────────────────────────────────────────────────────────────

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS crim",
    # One row per (entity, role, person) — the flattened individual signers.
    """
    CREATE TABLE IF NOT EXISTS crim.rce_person (
        registration_index TEXT NOT NULL,
        role                TEXT NOT NULL,   -- officer | incorporator
        person_key          TEXT NOT NULL,
        display_name        TEXT,
        PRIMARY KEY (registration_index, role, person_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rce_person_key ON crim.rce_person (person_key)",
    "CREATE INDEX IF NOT EXISTS idx_rce_person_idx ON crim.rce_person (registration_index)",
    # Per-person rollup — the frequent-filer flag, same shape as rce_address_entities.
    """
    CREATE TABLE IF NOT EXISTS crim.rce_person_entities (
        person_key         TEXT PRIMARY KEY,
        display_name        TEXT,
        entity_count         INTEGER NOT NULL,
        is_frequent_filer     BOOLEAN NOT NULL DEFAULT FALSE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rce_person_entities_count "
    "ON crim.rce_person_entities (entity_count DESC)",
    # The cluster assignment. Sparse by design: an entity with no qualifying
    # co-membership simply has no row (a "cluster of one" is not a cluster).
    """
    CREATE TABLE IF NOT EXISTS crim.control_clusters (
        registration_index TEXT PRIMARY KEY,
        cluster_id          TEXT NOT NULL,
        cluster_size         INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_control_clusters_cluster "
    "ON crim.control_clusters (cluster_id)",
    # One row per cluster — the rollup the read layer serves from.
    """
    CREATE TABLE IF NOT EXISTS crim.control_cluster_summary (
        cluster_id            TEXT PRIMARY KEY,
        entity_count           INTEGER NOT NULL,
        distinct_owner_count    INTEGER NOT NULL,
        spans_multiple_owners  BOOLEAN NOT NULL,
        shared_people          JSONB,
        address_corroborated  BOOLEAN NOT NULL DEFAULT FALSE,
        built_at               TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS crim.control_cluster_summary CASCADE",
    "DROP TABLE IF EXISTS crim.control_clusters CASCADE",
    "DROP TABLE IF EXISTS crim.rce_person_entities CASCADE",
    "DROP TABLE IF EXISTS crim.rce_person CASCADE",
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))


# ── Person key ──────────────────────────────────────────────────────────────

def person_key(first: str | None, middle: str | None, last: str | None) -> str | None:
    """Canonical identity key for one individual officer/incorporator name.

    Same accent-fold + punctuation-strip as `normalize_owner`, over the
    concatenated first/middle/last fields the registry publishes separately.
    Deliberately exact (no nickname/initial expansion, no fuzzy pass) — a
    missed middle name means two mentions of the same person split into two
    keys, which is the conservative failure (an under-clustered pair, not a
    false merge), matching this codebase's standing preference for that
    direction of error (`normalize_owner`, F1).
    """
    parts = [p for p in (first, middle, last) if p and p.strip()]
    if not parts:
        return None
    s = _fold_accents(" ".join(parts)).upper()
    s = s.replace(".", "")
    s = _NON_ALNUM.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s or None


# ── Build: person keys ───────────────────────────────────────────────────────

_PERSON_SQL = """
SELECT e.registration_index, :role AS role,
       o->'individualName'->>'firstName'  AS fn,
       o->'individualName'->>'middleName' AS mn,
       o->'individualName'->>'lastName'   AS ln
FROM (SELECT registration_index, raw FROM crim.rce_entities
      WHERE jsonb_typeof(raw->:field) = 'array') e,
     LATERAL jsonb_array_elements(e.raw->:field) o
WHERE jsonb_typeof(o) = 'object' AND o->>'isIndividual' = 'true'
"""


def build_person_keys(engine: Engine, *, batch: int = 10_000) -> int:
    """Flatten every individual officer/incorporator into `crim.rce_person`.

    Extraction (the JSONB unnest) runs in SQL; the name-folding logic runs in
    Python over the flattened rows, reusing `person_key()` so the build and any
    future audit code apply the identical function.
    """
    create_schema(engine)
    payload: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for role, field in (("officer", "officers"), ("incorporator", "incorporators")):
            rows = conn.execute(text(_PERSON_SQL), {"role": role, "field": field}).fetchall()
            for reg, _role, fn, mn, ln in rows:
                pk = person_key(fn, mn, ln)
                if pk is None:
                    continue
                display = " ".join(p for p in (fn, mn, ln) if p and p.strip())
                payload.append({"reg": reg, "role": role, "pk": pk, "disp": display or None})

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.rce_person"))
        for i in range(0, len(payload), batch):
            conn.execute(text("""
                INSERT INTO crim.rce_person (registration_index, role, person_key, display_name)
                VALUES (:reg, :role, :pk, :disp)
                ON CONFLICT (registration_index, role, person_key) DO NOTHING
            """), payload[i:i + batch])

        conn.execute(text("TRUNCATE crim.rce_person_entities"))
        conn.execute(text(f"""
            INSERT INTO crim.rce_person_entities (person_key, display_name, entity_count, is_frequent_filer)
            SELECT person_key, mode() WITHIN GROUP (ORDER BY display_name),
                   COUNT(DISTINCT registration_index),
                   COUNT(DISTINCT registration_index) > {FREQUENT_FILER_THRESHOLD}
            FROM crim.rce_person
            GROUP BY person_key
        """))
        n = conn.execute(text("SELECT COUNT(*) FROM crim.rce_person_entities")).scalar() or 0
        freq = conn.execute(text(
            "SELECT COUNT(*) FROM crim.rce_person_entities WHERE is_frequent_filer")).scalar() or 0

    log.info("crim.rce_person: %d rows | %d distinct people, %d frequent-filer (>%d entities)",
              len(payload), n, freq, FREQUENT_FILER_THRESHOLD)
    return len(payload)


# ── Build: clusters ───────────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb

    def groups(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for x in self._parent:
            out[self.find(x)].add(x)
        return out


def build_clusters(engine: Engine) -> dict[str, Any]:
    """Union entities into control clusters on shared non-frequent-filer people.

    Two entities are linked only once they share `MIN_SHARED_PEOPLE` or more
    distinct people — see the module docstring for why a lower bar collapses
    into one giant, meaningless component. Computed in Python: the entity
    count touched by qualifying people is in the tens of thousands, well
    within a single pass, and a graph problem like this is awkward in SQL.
    """
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.registration_index, p.person_key
            FROM crim.rce_person p
            JOIN crim.rce_person_entities e ON e.person_key = p.person_key
            WHERE NOT e.is_frequent_filer
        """)).fetchall()

    entity_people: dict[str, set[str]] = defaultdict(set)
    for reg, pk in rows:
        entity_people[reg].add(pk)

    people_entities: dict[str, set[str]] = defaultdict(set)
    for reg, people in entity_people.items():
        for pk in people:
            people_entities[pk].add(reg)

    pair_support: Counter[tuple[str, str]] = Counter()
    for pk, ents in people_entities.items():
        if len(ents) < 2:
            continue
        ordered = sorted(ents)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair_support[(ordered[i], ordered[j])] += 1

    uf = _UnionFind()
    for (a, b), support in pair_support.items():
        if support >= MIN_SHARED_PEOPLE:
            uf.union(a, b)

    groups = {root: members for root, members in uf.groups().items() if len(members) > 1}

    cluster_rows = []
    for root, members in groups.items():
        # Deterministic id independent of dict/set iteration order.
        cluster_id = min(members)
        for reg in members:
            cluster_rows.append({"reg": reg, "cid": cluster_id, "size": len(members)})

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.control_clusters"))
        for i in range(0, len(cluster_rows), 5000):
            conn.execute(text("""
                INSERT INTO crim.control_clusters (registration_index, cluster_id, cluster_size)
                VALUES (:reg, :cid, :size)
                ON CONFLICT (registration_index) DO NOTHING
            """), cluster_rows[i:i + 5000])

    max_size = max((len(m) for m in groups.values()), default=0)
    log.info("Control clusters: %d clusters, %d entities clustered, largest %d "
              "(min_shared_people=%d)", len(groups), len(cluster_rows), max_size, MIN_SHARED_PEOPLE)
    return {"clusters": len(groups), "entities_clustered": len(cluster_rows), "largest": max_size}


def build_cluster_summary(engine: Engine) -> dict[str, Any]:
    """Roll each cluster up: distinct owners it spans, the people forming it,
    and whether a non-agent-office address corroborates it.

    `spans_multiple_owners` is the headline signal — a cluster confined to one
    CRIM owner_key is real but unremarkable (a single owner's own shell
    companies, already visible on their own drawer); a cluster touching two or
    more owner_keys is the "these look like separate landowners but share
    control" finding this item exists to surface.
    """
    with engine.connect() as conn:
        cluster_members = conn.execute(text(
            "SELECT cluster_id, registration_index FROM crim.control_clusters"
        )).fetchall()
        owners = conn.execute(text(
            "SELECT DISTINCT registration_index, owner_key FROM crim.owner_rce_match "
            "WHERE registration_index IS NOT NULL"
        )).fetchall()
        people = conn.execute(text("""
            SELECT p.registration_index, p.person_key, p.display_name, p.role
            FROM crim.rce_person p
            JOIN crim.rce_person_entities e ON e.person_key = p.person_key
            WHERE NOT e.is_frequent_filer
        """)).fetchall()
        # Non-agent-office addresses only — an agent office shared by cluster
        # members carries no signal (same reasoning as the fuzzy-match demotion).
        addresses = conn.execute(text("""
            SELECT a.registration_index, a.address_key
            FROM crim.rce_addresses a
            JOIN crim.rce_address_entities ae ON ae.address_key = a.address_key
            WHERE NOT ae.is_agent_office
        """)).fetchall()

    reg_to_owners: dict[str, set[str]] = defaultdict(set)
    for reg, ok in owners:
        reg_to_owners[reg].add(ok)

    reg_to_people: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for reg, pk, disp, role in people:
        reg_to_people[reg].add((pk, disp or pk, role))

    reg_to_addresses: dict[str, set[str]] = defaultdict(set)
    for reg, addr_key in addresses:
        reg_to_addresses[reg].add(addr_key)

    members_by_cluster: dict[str, list[str]] = defaultdict(list)
    for cid, reg in cluster_members:
        members_by_cluster[cid].append(reg)

    payload = []
    for cid, members in members_by_cluster.items():
        owner_set: set[str] = set()
        person_counter: Counter[tuple[str, str, str]] = Counter()
        addr_counter: Counter[str] = Counter()
        for reg in members:
            owner_set |= reg_to_owners.get(reg, set())
            for p in reg_to_people.get(reg, set()):
                person_counter[p] += 1
            for a in reg_to_addresses.get(reg, set()):
                addr_counter[a] += 1

        # The people that actually explain the cluster: shared by >=2 members.
        shared_people = [
            {"person_key": pk, "display_name": disp, "role": role, "entities_in_cluster": n}
            for (pk, disp, role), n in person_counter.items() if n >= 2
        ]
        shared_people.sort(key=lambda p: -p["entities_in_cluster"])
        address_corroborated = any(n >= 2 for n in addr_counter.values())

        payload.append({
            "cid": cid,
            "n_entities": len(members),
            "n_owners": len(owner_set),
            "spans": len(owner_set) > 1,
            "people": json.dumps(shared_people),
            "addr_corr": address_corroborated,
        })

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE crim.control_cluster_summary"))
        for i in range(0, len(payload), 2000):
            conn.execute(text("""
                INSERT INTO crim.control_cluster_summary
                    (cluster_id, entity_count, distinct_owner_count, spans_multiple_owners,
                     shared_people, address_corroborated)
                VALUES (:cid, :n_entities, :n_owners, :spans, CAST(:people AS JSONB), :addr_corr)
                ON CONFLICT (cluster_id) DO NOTHING
            """), payload[i:i + 2000])

    spanning = sum(1 for p in payload if p["spans"])
    log.info("Cluster summary: %d clusters, %d span >1 CRIM owner_key, %d address-corroborated",
              len(payload), spanning, sum(1 for p in payload if p["addr_corr"]))
    return {"clusters": len(payload), "spanning_multiple_owners": spanning,
            "address_corroborated": sum(1 for p in payload if p["addr_corr"])}


def run(engine: Engine) -> dict[str, Any]:
    """Full offline pass: person keys -> clusters -> summary. Idempotent, like
    `rce_match.run` — safe to re-run as the F11a registry mirror grows or the
    F11b match set changes."""
    create_schema(engine)
    n_people = build_person_keys(engine)
    cluster_res = build_clusters(engine)
    summary_res = build_cluster_summary(engine)
    return {"person_rows": n_people, **cluster_res, **{f"summary_{k}": v for k, v in summary_res.items()}}


def stats(engine: Engine) -> dict[str, Any]:
    """The measured cluster yield — for `--cluster-stats` and the gate."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM crim.rce_person_entities)                          AS distinct_people,
              (SELECT COUNT(*) FROM crim.rce_person_entities WHERE is_frequent_filer)   AS frequent_filers,
              (SELECT COUNT(*) FROM crim.control_cluster_summary)                       AS clusters,
              (SELECT COUNT(*) FROM crim.control_clusters)                              AS clustered_entities,
              (SELECT MAX(cluster_size) FROM crim.control_clusters)                     AS largest_cluster,
              (SELECT COUNT(*) FROM crim.control_cluster_summary
                 WHERE spans_multiple_owners)                                           AS spanning_clusters,
              (SELECT COUNT(*) FROM crim.control_cluster_summary
                 WHERE address_corroborated)                                            AS address_corroborated
        """)).mappings().fetchone()
    d = {k: int(v or 0) for k, v in dict(row).items()}
    d["confidence_tier"] = CLUSTER_TIER
    d["min_shared_people"] = MIN_SHARED_PEOPLE
    d["frequent_filer_threshold"] = FREQUENT_FILER_THRESHOLD
    return d


# ── Read: per-entity cluster info ───────────────────────────────────────────

def available(engine: Engine) -> bool:
    from prism.crim.query import _table_exists
    return _table_exists(engine, "crim.control_cluster_summary")


def get_clusters(engine: Engine, registration_indexes: list[str]) -> dict[str, dict[str, Any]]:
    """Cluster payload for each given registration_index that belongs to one.

    Returns only entries for entities in a real (size>1) cluster — the caller
    (F11c's `owner_registry`) treats absence as "no cluster", the same silent-
    when-nothing-to-say posture as every other enrichment in this codebase.
    Batches all lookups for the given entities in one round trip rather than
    querying per-entity, since callers pass an owner's full matched-entity set.
    """
    if not registration_indexes or not available(engine):
        return {}

    with engine.connect() as conn:
        own_clusters = conn.execute(text("""
            SELECT registration_index, cluster_id FROM crim.control_clusters
            WHERE registration_index = ANY(:regs)
        """), {"regs": registration_indexes}).fetchall()
        if not own_clusters:
            return {}
        cluster_ids = list({cid for _, cid in own_clusters})

        summaries = {
            r["cluster_id"]: dict(r) for r in conn.execute(text("""
                SELECT cluster_id, entity_count, distinct_owner_count,
                       spans_multiple_owners, shared_people, address_corroborated
                FROM crim.control_cluster_summary WHERE cluster_id = ANY(:cids)
            """), {"cids": cluster_ids}).mappings().fetchall()
        }
        members = conn.execute(text("""
            SELECT cc.cluster_id, cc.registration_index, r.corp_name, r.status_es,
                   m.owner_key, oe.display_name AS owner_display_name
            FROM crim.control_clusters cc
            JOIN crim.rce_match_key r ON r.registration_index = cc.registration_index
            LEFT JOIN crim.owner_rce_match m
              ON m.registration_index = cc.registration_index AND m.registration_index IS NOT NULL
            LEFT JOIN crim.owner_entities oe ON oe.owner_key = m.owner_key
            WHERE cc.cluster_id = ANY(:cids)
        """), {"cids": cluster_ids}).mappings().fetchall()

    members_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in members:
        members_by_cluster[m["cluster_id"]].append(dict(m))

    out: dict[str, dict[str, Any]] = {}
    for reg, cid in own_clusters:
        summ = summaries.get(cid)
        if not summ:
            continue
        siblings = [
            {
                "registration_index": m["registration_index"],
                "corp_name": m["corp_name"],
                "status_es": m["status_es"],
                "owner_key": m["owner_key"],
                "owner_display_name": m["owner_display_name"],
            }
            for m in members_by_cluster.get(cid, []) if m["registration_index"] != reg
        ]
        out[reg] = {
            "cluster_id": cid,
            "entity_count": summ["entity_count"],
            "distinct_owner_count": summ["distinct_owner_count"],
            "spans_multiple_owners": summ["spans_multiple_owners"],
            "shared_people": summ["shared_people"] or [],
            "address_corroborated": summ["address_corroborated"],
            "siblings": siblings,
            "confidence_tier": CLUSTER_TIER,
        }
    return out
