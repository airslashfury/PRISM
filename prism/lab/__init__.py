"""F13a — Data Lab: a curated-query registry + raw-SQL escape hatch over `prism_ro`.

`queries.py` is the single-place `QuerySpec` registry (id, bind-param SQL,
declared source tables, result shape). `execute.py` runs a spec or an ad-hoc
`SELECT`, stamping every result with the weakest confidence tier among its
declared/detected source tables — the same "weakest required input" rule
`prism.provenance.catalog` already applies to derived tables.
"""
