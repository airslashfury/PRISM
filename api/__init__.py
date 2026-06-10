"""PRISM HTTP API — a thin FastAPI shell over the PostGIS model.

Business logic lives in `prism/`. This layer only projects already-computed
tables to the wire as typed JSON / GeoJSON for the Next.js frontend.
"""
