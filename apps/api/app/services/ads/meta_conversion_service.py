"""AuraFlow — Meta Conversions API (CAPI) Tracking Service

Hooks into existing booking/payment/registration flows to capture
fbclid/fbc/fbp-based conversions and store them for upload via CAPI.
"""
import hashlib
import uuid
from typing import Optional

from app.core.logging import logger
from app.db.session import get_tenant_db


def _sha256_hash(value: str) -> str:
    """SHA256 hash a value for CAPI (lowercase, stripped)."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


class MetaConversionTracker:
    """Track Meta Ads conversions from studio events."""

    async def track_conversion(
        self,
        conversion_type: str,
        event_name: str = "Lead",
        fbclid: Optional[str] = None,
        fbc: Optional[str] = None,
        fbp: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        conversion_value_cents: int = 0,
    ) -> Optional[str]:
        """
        Record a conversion event for later upload via Conversions API.

        Args:
            conversion_type: trial_signup | membership_purchase | class_booking
            event_name: Meta standard event (Lead, Purchase, CompleteRegistration, Schedule)
            fbclid: Facebook click ID from URL params
            fbc: _fbc cookie value
            fbp: _fbp cookie value
            email: User email (will be SHA256 hashed)
            phone: User phone (will be SHA256 hashed)
            conversion_value_cents: dollar value of the conversion

        Returns:
            Conversion ID if tracked, None if no identifiers available
        """
        # Need at least one identifier
        if not any([fbclid, fbc, fbp, email, phone]):
            return None

        email_hash = _sha256_hash(email) if email else None
        phone_hash = _sha256_hash(phone) if phone else None
        event_id = str(uuid.uuid4())

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO meta_ads_conversions
                    (conversion_type, event_name, fbclid, fbc, fbp,
                     email_hash, phone_hash, conversion_value_cents, event_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                conversion_type, event_name, fbclid, fbc, fbp,
                email_hash, phone_hash, conversion_value_cents, event_id,
            )

        conversion_id = str(row["id"])
        logger.info(
            "Meta conversion tracked",
            conversion_type=conversion_type,
            event_name=event_name,
            has_fbclid=bool(fbclid),
            value_cents=conversion_value_cents,
        )
        return conversion_id

    async def track_trial_signup(
        self, fbclid: Optional[str] = None, fbc: Optional[str] = None,
        fbp: Optional[str] = None, email: Optional[str] = None,
    ) -> Optional[str]:
        """Track a trial sign-up conversion."""
        return await self.track_conversion(
            "trial_signup", "Lead",
            fbclid=fbclid, fbc=fbc, fbp=fbp, email=email,
        )

    async def track_membership_purchase(
        self, price_cents: int,
        fbclid: Optional[str] = None, fbc: Optional[str] = None,
        fbp: Optional[str] = None, email: Optional[str] = None,
    ) -> Optional[str]:
        """Track a membership purchase conversion."""
        return await self.track_conversion(
            "membership_purchase", "Purchase",
            fbclid=fbclid, fbc=fbc, fbp=fbp, email=email,
            conversion_value_cents=price_cents,
        )

    async def track_class_booking(
        self, price_cents: int = 0,
        fbclid: Optional[str] = None, fbc: Optional[str] = None,
        fbp: Optional[str] = None, email: Optional[str] = None,
    ) -> Optional[str]:
        """Track a class booking conversion."""
        return await self.track_conversion(
            "class_booking", "Schedule",
            fbclid=fbclid, fbc=fbc, fbp=fbp, email=email,
            conversion_value_cents=price_cents,
        )


meta_conversion_tracker = MetaConversionTracker()
