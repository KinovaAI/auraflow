"""
AuraFlow — Tenant Context

Uses Python's contextvars for async-safe per-request tenant isolation.
Each async request gets its own context — no cross-request leakage.
"""
from contextvars import ContextVar
from typing import Optional
from dataclasses import dataclass


@dataclass
class TenantContext:
    organization_id: str
    schema_name: str
    slug: str
    plan_id: Optional[str] = None


_tenant_context: ContextVar[Optional[TenantContext]] = ContextVar(
    "tenant_context", default=None
)


def set_tenant_context(
    organization_id: str,
    schema_name: str,
    slug: str,
    plan_id: Optional[str] = None,
) -> None:
    _tenant_context.set(TenantContext(
        organization_id=organization_id,
        schema_name=schema_name,
        slug=slug,
        plan_id=plan_id,
    ))


def get_tenant_context() -> Optional[TenantContext]:
    return _tenant_context.get()


def clear_tenant_context() -> None:
    _tenant_context.set(None)


def require_tenant_context() -> TenantContext:
    """Use in endpoints that require a tenant. Raises if no context set."""
    ctx = _tenant_context.get()
    if ctx is None:
        raise RuntimeError("No tenant context — TenantMiddleware may not have run")
    return ctx


async def set_tenant_context_from_schema(schema_name: str) -> TenantContext:
    """Resolve org_id/slug from af_global.organizations and set the context.

    Use in Celery / background tasks that loop over tenant schemas. Avoids
    the trap of `set_tenant_context(organization_id="", ...)` — that empty
    string silently breaks any downstream code that calls
    get_organization_id() (e.g. emails, audit log writes, Stripe lookups).
    """
    from app.db.session import get_global_db
    async with get_global_db() as db:
        org = await db.fetchrow(
            "SELECT id, slug, plan_id FROM af_global.organizations WHERE schema_name = $1",
            schema_name,
        )
    if not org:
        raise RuntimeError(f"No organization found for schema {schema_name!r}")
    set_tenant_context(
        organization_id=str(org["id"]),
        schema_name=schema_name,
        slug=org["slug"],
        plan_id=str(org["plan_id"]) if org["plan_id"] else None,
    )
    return require_tenant_context()


def get_schema_name() -> str:
    """Shortcut to get the current tenant's schema name."""
    return require_tenant_context().schema_name


def get_organization_id() -> str:
    """Shortcut to get the current organization ID."""
    return require_tenant_context().organization_id
