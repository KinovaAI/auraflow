"""AuraFlow — Audit Logging Service

Records all sensitive admin actions to af_global.audit_log for compliance
and security forensics. Every mutation by a platform admin or studio admin
that affects users, organizations, or security settings is logged here.
"""
import json
import uuid
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_global_db


class AuditService:
    """Write audit records to af_global.audit_log."""

    async def log(
        self,
        *,
        user_id: str,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        organization_id: str | None = None,
        ip_address: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record an audit event.

        Parameters
        ----------
        user_id : str
            The admin performing the action.
        action : str
            Short verb, e.g. "user.deactivate", "org.status_change",
            "user.password_reset", "feature_flag.update".
        resource_type : str | None
            The kind of entity affected (user, organization, feature_flag …).
        resource_id : str | None
            Primary key of the affected entity.
        organization_id : str | None
            Org context, if applicable.
        ip_address : str | None
            Request source IP.
        metadata : dict | None
            Free-form details (old/new values, reason, etc.).
        """
        try:
            async with get_global_db() as db:
                await db.execute(
                    """
                    INSERT INTO af_global.audit_log
                        (id, user_id, action, resource_type, resource_id,
                         organization_id, ip_address, metadata)
                    VALUES ($1, $2::uuid, $3, $4, $5::uuid, $6::uuid, $7::inet, $8::jsonb)
                    """,
                    str(uuid.uuid4()),
                    user_id,
                    action,
                    resource_type,
                    resource_id,
                    organization_id,
                    ip_address,
                    json.dumps(metadata or {}),
                )
            logger.info(
                "Audit event recorded",
                action=action,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except Exception as e:
            # Audit logging must never break the request
            logger.error("Failed to record audit event", error=str(e), action=action)

    async def log_failed_login(
        self,
        *,
        email: str,
        ip_address: str | None = None,
        reason: str = "invalid_credentials",
    ) -> None:
        """Record a failed login attempt for compliance trail."""
        try:
            async with get_global_db() as db:
                await db.execute(
                    """
                    INSERT INTO af_global.audit_log
                        (id, action, resource_type, ip_address, metadata)
                    VALUES ($1, 'auth.login_failed', 'user', $2::inet, $3::jsonb)
                    """,
                    str(uuid.uuid4()),
                    ip_address,
                    json.dumps({"email": email, "reason": reason}),
                )
        except Exception as e:
            logger.error("Failed to record login failure audit", error=str(e))

    async def log_login_success(
        self,
        *,
        user_id: str,
        email: str,
        ip_address: str | None = None,
        mfa_used: bool = False,
    ) -> None:
        """Record a successful login."""
        try:
            async with get_global_db() as db:
                await db.execute(
                    """
                    INSERT INTO af_global.audit_log
                        (id, user_id, action, resource_type, resource_id,
                         ip_address, metadata)
                    VALUES ($1, $2::uuid, 'auth.login_success', 'user', $2::uuid,
                            $3::inet, $4::jsonb)
                    """,
                    str(uuid.uuid4()),
                    user_id,
                    ip_address,
                    json.dumps({"email": email, "mfa_used": mfa_used}),
                )
        except Exception as e:
            logger.error("Failed to record login success audit", error=str(e))

    async def query(
        self,
        *,
        action: str | None = None,
        resource_type: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        hours: int | None = None,
    ) -> list[dict]:
        """Query audit log with optional filters."""
        conditions = []
        params: list = []
        idx = 1

        if action:
            conditions.append(f"action = ${idx}")
            params.append(action)
            idx += 1
        if resource_type:
            conditions.append(f"resource_type = ${idx}")
            params.append(resource_type)
            idx += 1
        if user_id:
            conditions.append(f"user_id = ${idx}::uuid")
            params.append(user_id)
            idx += 1
        if hours:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            conditions.append(f"created_at >= ${idx}")
            params.append(cutoff)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        async with get_global_db() as db:
            rows = await db.fetch(f"""
                SELECT id, organization_id, user_id, action, resource_type,
                       resource_id, metadata, ip_address, created_at
                FROM af_global.audit_log
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
            """, *params)
            return [dict(r) for r in rows]


audit_service = AuditService()
