"""AuraFlow — Custom Domain Service

Manages custom domain configuration for organizations.
Handles domain registration, DNS verification, and status tracking.
"""
import socket
from datetime import datetime, timezone

from app.core.logging import logger
from app.db.session import get_global_db

# The CNAME target that custom domains should point to
CNAME_TARGET = "app.auraflow.fit"


class CustomDomainService:

    async def request_custom_domain(self, org_id: str, domain: str) -> dict:
        """Register a custom domain for an organization. Sets status to pending_verification."""
        domain = domain.strip().lower()

        # Basic validation
        if not domain or "." not in domain or len(domain) > 255:
            raise ValueError("Invalid domain name")

        # Check if domain is already in use by another org
        async with get_global_db() as db:
            existing = await db.fetchrow(
                """
                SELECT id FROM af_global.organizations
                WHERE custom_domain = $1 AND id != $2
                """,
                domain, org_id,
            )
            if existing:
                raise ValueError("This domain is already in use by another organization")

            row = await db.fetchrow(
                """
                UPDATE af_global.organizations
                SET custom_domain = $1,
                    custom_domain_status = 'pending_verification',
                    custom_domain_verified_at = NULL,
                    updated_at = NOW()
                WHERE id = $2
                RETURNING id, custom_domain, custom_domain_status, custom_domain_verified_at
                """,
                domain, org_id,
            )

        if not row:
            raise ValueError("Organization not found")

        logger.info(
            "Custom domain requested",
            org_id=org_id,
            domain=domain,
        )
        return dict(row)

    async def verify_domain(self, org_id: str) -> dict:
        """Verify that the custom domain's DNS points to the AuraFlow CNAME target."""
        async with get_global_db() as db:
            org = await db.fetchrow(
                """
                SELECT custom_domain, custom_domain_status
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )

        if not org or not org["custom_domain"]:
            raise ValueError("No custom domain configured for this organization")

        domain = org["custom_domain"]
        verified = False

        try:
            # Resolve the domain and check if it points to our target
            results = socket.getaddrinfo(domain, None)
            target_results = socket.getaddrinfo(CNAME_TARGET, None)

            domain_ips = {r[4][0] for r in results}
            target_ips = {r[4][0] for r in target_results}

            # Domain is verified if it resolves to the same IPs as our target
            verified = bool(domain_ips & target_ips)
        except socket.gaierror:
            # DNS resolution failed — domain not configured yet
            verified = False
        except Exception as e:
            logger.warning(
                "DNS verification error",
                domain=domain,
                error=str(e),
            )
            verified = False

        now = datetime.now(timezone.utc)

        if verified:
            async with get_global_db() as db:
                row = await db.fetchrow(
                    """
                    UPDATE af_global.organizations
                    SET custom_domain_status = 'verified',
                        custom_domain_verified_at = $2,
                        updated_at = NOW()
                    WHERE id = $1
                    RETURNING id, custom_domain, custom_domain_status, custom_domain_verified_at
                    """,
                    org_id, now,
                )
            logger.info("Custom domain verified", org_id=org_id, domain=domain)
            return dict(row)
        else:
            return {
                "id": org_id,
                "custom_domain": domain,
                "custom_domain_status": "pending_verification",
                "custom_domain_verified_at": None,
                "message": f"DNS verification failed. Please create a CNAME record pointing {domain} to {CNAME_TARGET}",
            }

    async def get_domain_status(self, org_id: str) -> dict | None:
        """Get the current custom domain and its verification status."""
        async with get_global_db() as db:
            row = await db.fetchrow(
                """
                SELECT id, custom_domain, custom_domain_status, custom_domain_verified_at
                FROM af_global.organizations
                WHERE id = $1
                """,
                org_id,
            )
        if not row:
            return None
        return dict(row)

    async def remove_custom_domain(self, org_id: str) -> bool:
        """Remove the custom domain configuration from an organization."""
        async with get_global_db() as db:
            result = await db.execute(
                """
                UPDATE af_global.organizations
                SET custom_domain = NULL,
                    custom_domain_status = NULL,
                    custom_domain_verified_at = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """,
                org_id,
            )

        if "UPDATE 0" in result:
            return False

        logger.info("Custom domain removed", org_id=org_id)
        return True
