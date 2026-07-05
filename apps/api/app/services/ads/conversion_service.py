"""AuraFlow — Google Ads Conversion Tracking Service

Hooks into existing booking/payment/registration flows to capture
gclid-based conversions and store them for daily upload to Google Ads.
"""
from typing import Optional

from app.core.logging import logger
from app.db.session import get_tenant_db


class ConversionTracker:
    """Track Google Ads conversions from studio events."""

    async def track_conversion(
        self,
        conversion_type: str,
        gclid: Optional[str],
        conversion_value_cents: int = 0,
        metadata: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Record a conversion event for later upload to Google Ads.

        Args:
            conversion_type: trial_signup | membership_purchase | class_booking
            gclid: Google click ID from the ad (captured from URL params)
            conversion_value_cents: dollar value of the conversion
            metadata: additional context (member_id, booking_id, etc.)

        Returns:
            Conversion ID if tracked, None if no gclid (organic traffic)
        """
        if not gclid:
            return None

        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO google_ads_conversions
                    (conversion_type, gclid, conversion_value_cents)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                conversion_type, gclid, conversion_value_cents,
            )

        conversion_id = str(row["id"])
        logger.info(
            "Conversion tracked",
            conversion_type=conversion_type,
            gclid=gclid[:10] + "...",
            value_cents=conversion_value_cents,
        )
        return conversion_id

    async def track_trial_signup(self, gclid: Optional[str]) -> Optional[str]:
        """Track a trial sign-up conversion."""
        return await self.track_conversion("trial_signup", gclid, conversion_value_cents=0)

    async def track_membership_purchase(
        self, gclid: Optional[str], price_cents: int
    ) -> Optional[str]:
        """Track a membership purchase conversion."""
        return await self.track_conversion("membership_purchase", gclid, conversion_value_cents=price_cents)

    async def track_class_booking(
        self, gclid: Optional[str], price_cents: int = 0
    ) -> Optional[str]:
        """Track a class booking conversion (micro-conversion)."""
        return await self.track_conversion("class_booking", gclid, conversion_value_cents=price_cents)


conversion_tracker = ConversionTracker()
