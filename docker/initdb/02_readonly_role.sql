-- prism_ro: read-only role for the Data Lab (F13a). Runs automatically on a
-- fresh volume via docker-entrypoint-initdb.d. For an EXISTING volume, run
-- `make db-readonly-role` (idempotent — safe to re-run any time, including
-- after a new prism.* module adds a schema, since GRANTs are per-schema).
--
-- statement_timeout + default_transaction_read_only are set at the ROLE
-- level, not just enforced in application code, so they hold even if a bug
-- in api/deps.py or prism/lab/ tried to connect some other way.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'prism_ro') THEN
    CREATE ROLE prism_ro WITH LOGIN PASSWORD 'prism_ro';
  END IF;
END
$$;

ALTER ROLE prism_ro SET statement_timeout = '8s';
ALTER ROLE prism_ro SET default_transaction_read_only = on;
ALTER ROLE prism_ro SET idle_in_transaction_session_timeout = '30s';

GRANT CONNECT ON DATABASE prism TO prism_ro;

-- Grant USAGE + SELECT across every real schema (not pg_catalog/information_schema),
-- plus default privileges so a table `prism` creates tomorrow is readable by
-- prism_ro without a manual re-grant. Dynamic on purpose: hardcoding the schema
-- list is exactly the kind of thing that goes stale the next time a domain
-- module ships (see the Dockerfile COPY trap noted in ROADMAP.md F13).
DO $$
DECLARE s text;
BEGIN
  FOR s IN
    SELECT nspname FROM pg_namespace
    WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'
  LOOP
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO prism_ro', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO prism_ro', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO prism_ro', s);
  END LOOP;
END
$$;
