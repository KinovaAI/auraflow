"""AuraFlow — ClassPass Integration Service

Manages ClassPass connection, configuration, reservations, and sync.
"""
import uuid

from app.core.logging import logger
from app.db.session import get_tenant_db


_CLASSPASS_CONFIG_UPDATE_COLS = {
    "venue_id", "is_active", "credit_rate", "auto_confirm",
    "max_spots_per_class", "blackout_class_types",
}


class ClassPassService:

    # ── Connection / Config ──────────────────────────────────────────────

    async def connect(self, studio_id: str, venue_id: str) -> dict:
        config_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                INSERT INTO classpass_config
                    (id, studio_id, venue_id, is_active)
                VALUES ($1, $2, $3, TRUE)
                ON CONFLICT (studio_id)
                DO UPDATE SET venue_id = EXCLUDED.venue_id,
                              is_active = TRUE,
                              updated_at = NOW()
                RETURNING *
                """,
                config_id, studio_id, venue_id,
            )
            logger.info("ClassPass connected", studio_id=studio_id, venue_id=venue_id)
            return dict(row)

    async def disconnect(self, studio_id: str) -> bool:
        async with get_tenant_db() as db:
            result = await db.execute(
                """
                UPDATE classpass_config
                SET is_active = FALSE, updated_at = NOW()
                WHERE studio_id = $1
                """,
                studio_id,
            )
            return "UPDATE 1" in result

    async def get_config(self, studio_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                "SELECT * FROM classpass_config WHERE studio_id = $1",
                studio_id,
            )
            return dict(row) if row else None

    async def update_config(self, studio_id: str, data: dict) -> dict | None:
        data = {k: v for k, v in data.items() if k in _CLASSPASS_CONFIG_UPDATE_COLS}
        async with get_tenant_db() as db:
            sets, params, idx = [], [], 1
            for k, v in data.items():
                sets.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            if not sets:
                return await self.get_config(studio_id)
            sets.append(f"updated_at = NOW()")
            params.append(studio_id)
            query = f"UPDATE classpass_config SET {', '.join(sets)} WHERE studio_id = ${idx} RETURNING *"
            row = await db.fetchrow(query, *params)
            return dict(row) if row else None

    # ── Reservations ─────────────────────────────────────────────────────

    async def handle_reservation(self, data: dict) -> dict:
        """Process an incoming ClassPass reservation (webhook)."""
        res_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            # Check if class session exists and has spots
            if data.get("class_session_id"):
                session = await db.fetchrow(
                    "SELECT capacity, booked_count FROM class_sessions WHERE id = $1",
                    data["class_session_id"],
                )
                if not session:
                    raise ValueError("Class session not found")

                # Check max spots from classpass config
                config = await db.fetchrow(
                    "SELECT max_spots_per_class, blackout_class_types FROM classpass_config WHERE is_active = TRUE LIMIT 1"
                )
                if config:
                    # Check blackout
                    class_type = await db.fetchrow(
                        "SELECT class_type_id FROM class_sessions WHERE id = $1",
                        data["class_session_id"],
                    )
                    if class_type and config.get("blackout_class_types"):
                        if class_type["class_type_id"] in config["blackout_class_types"]:
                            raise ValueError("This class type is blocked from ClassPass bookings")

                    # Check max spots
                    cp_count = await db.fetchval(
                        """
                        SELECT COUNT(*) FROM classpass_reservations
                        WHERE class_session_id = $1 AND status IN ('reserved', 'confirmed')
                        """,
                        data["class_session_id"],
                    )
                    if cp_count >= config["max_spots_per_class"]:
                        raise ValueError("Maximum ClassPass spots reached for this class")

            row = await db.fetchrow(
                """
                INSERT INTO classpass_reservations
                    (id, classpass_reservation_id, class_session_id,
                     customer_name, customer_email, credits, status)
                VALUES ($1, $2, $3, $4, $5, $6, 'reserved')
                RETURNING *
                """,
                res_id, data["classpass_reservation_id"],
                data.get("class_session_id"),
                data.get("customer_name"),
                data.get("customer_email"),
                data.get("credits", 0),
            )
            logger.info(
                "ClassPass reservation created",
                reservation_id=res_id,
                cp_id=data["classpass_reservation_id"],
            )
            return dict(row)

    async def handle_cancellation(self, classpass_reservation_id: str) -> dict | None:
        async with get_tenant_db() as db:
            row = await db.fetchrow(
                """
                UPDATE classpass_reservations
                SET status = 'cancelled', updated_at = NOW()
                WHERE classpass_reservation_id = $1 AND status IN ('reserved', 'confirmed')
                RETURNING *
                """,
                classpass_reservation_id,
            )
            if row:
                logger.info(
                    "ClassPass reservation cancelled",
                    cp_id=classpass_reservation_id,
                )
            return dict(row) if row else None

    async def list_reservations(
        self,
        class_session_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        async with get_tenant_db() as db:
            conditions = []
            params = []
            idx = 1
            if class_session_id:
                conditions.append(f"class_session_id = ${idx}")
                params.append(class_session_id)
                idx += 1
            if status:
                conditions.append(f"status = ${idx}")
                params.append(status)
                idx += 1
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)
            rows = await db.fetch(
                f"""
                SELECT * FROM classpass_reservations
                {where}
                ORDER BY created_at DESC
                LIMIT ${idx}
                """,
                *params,
            )
            return [dict(r) for r in rows]
