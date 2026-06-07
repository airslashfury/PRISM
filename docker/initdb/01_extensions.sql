-- Runs once on first DB init (new data directory only).
-- For existing containers, install manually: apt-get install postgresql-16-pgrouting
-- then run: CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pgrouting CASCADE;
