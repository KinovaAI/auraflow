# No migrations — the schema is built by a single file

The complete database schema is built from `infra/docker/postgres/init.sql`, which the
Postgres entrypoint runs on a fresh `docker compose up`. That single file creates
everything: `af_global`, a complete `provision_tenant_schema()` (every tenant table),
config seed, and a demo tenant. There is no incremental Alembic migration chain.
