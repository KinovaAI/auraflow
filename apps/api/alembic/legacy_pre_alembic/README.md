# Legacy pre-alembic schema files

The 2 files in this directory **were never proper alembic migrations**.
Each has a docstring with `Revision ID:` / `Revises:` lines but no
top-level `revision = "..."` Python statement and no `upgrade()` /
`downgrade()` functions — just `TENANT_SQL` / `GLOBAL_SQL` constant
strings.

The schema they describe is what gets created for new tenants by
`infra/docker/postgres/init.sql` at db-init time. Existing tenants got
this schema applied historically via that init.sql + manual SQL.

They were originally placed in `alembic/versions/` but that broke
alembic — alembic walks every file in `versions/` and refused to load
anything because these have no `revision = ...` declaration. Moving
them here makes alembic functional again.

A few well-formed migrations declare these revision IDs as
`down_revision` parents (`enterprise_features_001`). Sibling files
named `*_stub.py` in `versions/` provide proper alembic shells (root
revisions with empty upgrade/downgrade) so the chain stays valid.

Don't delete these files — they document what's in the historical
schema and are useful for reading even though alembic doesn't run them.
