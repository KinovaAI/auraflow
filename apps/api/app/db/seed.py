"""AuraFlow — Seed Data Script

Creates demo data for testing/development. Idempotent — checks before inserting.
Creates a demo organization, membership types, instructors, class types, and members.

Usage:
    python -m app.db.seed
"""
import asyncio
import uuid

from app.core.logging import logger
from app.core.security import hash_password
from app.db.session import get_global_db, get_tenant_db


# ── Demo Data Definitions ─────────────────────────────────────────────────────

ORG_NAME = "Sunrise Yoga Studio"
ORG_SLUG = "sunrise-yoga"
SCHEMA_NAME = "af_tenant_sunrise_yoga"
DEFAULT_PASSWORD = "demo1234"

MEMBERSHIP_TYPES = [
    {
        "name": "Drop-in",
        "type": "day_pass",
        "price_cents": 2000,
        "billing_period": "one_time",
        "class_count": 1,
        "duration_days": 1,
    },
    {
        "name": "10-Class Pack",
        "type": "class_pack",
        "price_cents": 15000,
        "billing_period": "one_time",
        "class_count": 10,
        "duration_days": 90,
    },
    {
        "name": "Monthly Unlimited",
        "type": "unlimited",
        "price_cents": 9900,
        "billing_period": "monthly",
        "class_count": None,
        "duration_days": None,
    },
    {
        "name": "Annual Unlimited",
        "type": "unlimited",
        "price_cents": 89900,
        "billing_period": "yearly",
        "class_count": None,
        "duration_days": None,
    },
]

INSTRUCTORS = [
    {"display_name": "Maya Johnson", "email": "maya@example.com", "bio": "RYT-500 certified with 10 years of experience in Vinyasa and Yin yoga."},
    {"display_name": "Alex Rivera", "email": "alex@example.com", "bio": "Former athlete turned yoga teacher, specializing in Power Yoga and conditioning."},
    {"display_name": "Sam Patel", "email": "sam@example.com", "bio": "Meditation and mindfulness teacher with a background in Ayurveda."},
]

CLASS_TYPES = [
    {"name": "Vinyasa Flow", "duration_minutes": 60, "capacity": 25, "level": "all_levels", "color": "#4F46E5"},
    {"name": "Yin Yoga", "duration_minutes": 75, "capacity": 20, "level": "all_levels", "color": "#7C3AED"},
    {"name": "Power Yoga", "duration_minutes": 60, "capacity": 20, "level": "intermediate", "color": "#DC2626"},
    {"name": "Meditation", "duration_minutes": 45, "capacity": 30, "level": "all_levels", "color": "#059669"},
    {"name": "Beginner Yoga", "duration_minutes": 60, "capacity": 25, "level": "beginner", "color": "#2563EB"},
]

DEMO_MEMBERS = [
    {"first_name": "Alice", "last_name": "Demo"},
    {"first_name": "Bob", "last_name": "Demo"},
    {"first_name": "Carol", "last_name": "Demo"},
    {"first_name": "David", "last_name": "Demo"},
    {"first_name": "Eva", "last_name": "Demo"},
    {"first_name": "Frank", "last_name": "Demo"},
    {"first_name": "Grace", "last_name": "Demo"},
    {"first_name": "Henry", "last_name": "Demo"},
    {"first_name": "Iris", "last_name": "Demo"},
    {"first_name": "Jack", "last_name": "Demo"},
]


async def seed() -> None:
    """Create all demo data. Idempotent."""
    pw_hash = hash_password(DEFAULT_PASSWORD)

    # ── 1. Organization ───────────────────────────────────────────────────
    async with get_global_db() as db:
        existing_org = await db.fetchrow(
            "SELECT id FROM af_global.organizations WHERE slug = $1", ORG_SLUG,
        )
        if existing_org:
            org_id = str(existing_org["id"])
            logger.info(f"Organization '{ORG_NAME}' already exists (id={org_id})")
        else:
            org_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO af_global.organizations
                    (id, slug, name, schema_name, status, timezone, country, currency)
                VALUES ($1, $2, $3, $4, 'active', 'America/Los_Angeles', 'US', 'USD')
                """,
                org_id, ORG_SLUG, ORG_NAME, SCHEMA_NAME,
            )
            logger.info(f"Created organization '{ORG_NAME}' (id={org_id})")

            # Provision tenant schema
            await db.execute(
                "SELECT af_global.provision_tenant_schema($1, $2::uuid)",
                SCHEMA_NAME, org_id,
            )
            logger.info(f"Provisioned tenant schema '{SCHEMA_NAME}'")

    # ── 2. Owner user account ─────────────────────────────────────────────
    owner_email = "owner@sunrise-yoga.example.com"
    async with get_global_db() as db:
        existing_owner = await db.fetchrow(
            "SELECT id FROM af_global.users WHERE email = $1", owner_email,
        )
        if existing_owner:
            owner_user_id = str(existing_owner["id"])
        else:
            owner_user_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO af_global.users
                    (id, email, password_hash, first_name, last_name, is_active)
                VALUES ($1, $2, $3, 'Studio', 'Owner', TRUE)
                """,
                owner_user_id, owner_email, pw_hash,
            )
            await db.execute(
                """
                INSERT INTO af_global.organization_users
                    (id, organization_id, user_id, role, is_active, joined_at)
                VALUES ($1, $2, $3, 'owner', TRUE, NOW())
                ON CONFLICT DO NOTHING
                """,
                str(uuid.uuid4()), org_id, owner_user_id,
            )
            logger.info(f"Created owner user '{owner_email}'")

    # ── 3. Studio ─────────────────────────────────────────────────────────
    async with get_tenant_db(schema_override=SCHEMA_NAME) as db:
        existing_studio = await db.fetchrow("SELECT id FROM studios LIMIT 1")
        if existing_studio:
            studio_id = str(existing_studio["id"])
            logger.info(f"Studio already exists (id={studio_id})")
        else:
            studio_id = str(uuid.uuid4())
            await db.execute(
                """
                INSERT INTO studios
                    (id, organization_id, name, slug, city, state, timezone, is_active)
                VALUES ($1, $2, $3, $4, 'Portland', 'OR', 'America/Los_Angeles', TRUE)
                """,
                studio_id, org_id, ORG_NAME, ORG_SLUG,
            )
            logger.info(f"Created studio '{ORG_NAME}' (id={studio_id})")

    # ── 4. Membership Types ───────────────────────────────────────────────
    async with get_tenant_db(schema_override=SCHEMA_NAME) as db:
        for mt in MEMBERSHIP_TYPES:
            existing = await db.fetchrow(
                "SELECT id FROM membership_types WHERE name = $1 AND studio_id = $2",
                mt["name"], studio_id,
            )
            if existing:
                logger.info(f"Membership type '{mt['name']}' already exists")
                continue
            await db.execute(
                """
                INSERT INTO membership_types
                    (id, studio_id, name, type, price_cents, billing_period,
                     class_count, duration_days, is_active, is_public)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE, TRUE)
                """,
                str(uuid.uuid4()), studio_id, mt["name"], mt["type"],
                mt["price_cents"], mt["billing_period"],
                mt["class_count"], mt["duration_days"],
            )
            logger.info(f"Created membership type '{mt['name']}'")

    # ── 5. Instructors ────────────────────────────────────────────────────
    async with get_tenant_db(schema_override=SCHEMA_NAME) as db:
        for instr in INSTRUCTORS:
            existing = await db.fetchrow(
                "SELECT id FROM instructors WHERE display_name = $1",
                instr["display_name"],
            )
            if existing:
                logger.info(f"Instructor '{instr['display_name']}' already exists")
                continue

            # Create user account for instructor
            user_id = str(uuid.uuid4())
            async with get_global_db() as gdb:
                existing_user = await gdb.fetchrow(
                    "SELECT id FROM af_global.users WHERE email = $1",
                    instr["email"],
                )
                if existing_user:
                    user_id = str(existing_user["id"])
                else:
                    await gdb.execute(
                        """
                        INSERT INTO af_global.users
                            (id, email, password_hash, first_name, last_name, is_active)
                        VALUES ($1, $2, $3, $4, $5, TRUE)
                        """,
                        user_id, instr["email"], pw_hash,
                        instr["display_name"].split()[0],
                        instr["display_name"].split()[-1],
                    )
                    await gdb.execute(
                        """
                        INSERT INTO af_global.organization_users
                            (id, organization_id, user_id, role, is_active, joined_at)
                        VALUES ($1, $2, $3, 'instructor', TRUE, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        str(uuid.uuid4()), org_id, user_id,
                    )

            await db.execute(
                """
                INSERT INTO instructors
                    (id, user_id, display_name, bio, email, is_active)
                VALUES ($1, $2, $3, $4, $5, TRUE)
                """,
                str(uuid.uuid4()), user_id,
                instr["display_name"], instr["bio"], instr["email"],
            )
            logger.info(f"Created instructor '{instr['display_name']}'")

    # ── 6. Class Types ────────────────────────────────────────────────────
    async with get_tenant_db(schema_override=SCHEMA_NAME) as db:
        for ct in CLASS_TYPES:
            existing = await db.fetchrow(
                "SELECT id FROM class_types WHERE name = $1 AND studio_id = $2",
                ct["name"], studio_id,
            )
            if existing:
                logger.info(f"Class type '{ct['name']}' already exists")
                continue
            await db.execute(
                """
                INSERT INTO class_types
                    (id, studio_id, name, duration_minutes, capacity, level,
                     color, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
                """,
                str(uuid.uuid4()), studio_id, ct["name"],
                ct["duration_minutes"], ct["capacity"], ct["level"],
                ct["color"],
            )
            logger.info(f"Created class type '{ct['name']}'")

    # ── 7. Demo Members ───────────────────────────────────────────────────
    async with get_tenant_db(schema_override=SCHEMA_NAME) as db:
        for i, m in enumerate(DEMO_MEMBERS, start=1):
            email = f"demo{i}@example.com"
            existing = await db.fetchrow(
                "SELECT id FROM members WHERE email = $1", email,
            )
            if existing:
                logger.info(f"Member '{email}' already exists")
                continue

            member_id = str(uuid.uuid4())
            user_id = str(uuid.uuid4())

            # Create user account
            async with get_global_db() as gdb:
                existing_user = await gdb.fetchrow(
                    "SELECT id FROM af_global.users WHERE email = $1", email,
                )
                if existing_user:
                    user_id = str(existing_user["id"])
                else:
                    await gdb.execute(
                        """
                        INSERT INTO af_global.users
                            (id, email, password_hash, first_name, last_name,
                             is_active, force_password_reset)
                        VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
                        """,
                        user_id, email, pw_hash,
                        m["first_name"], m["last_name"],
                    )
                    await gdb.execute(
                        """
                        INSERT INTO af_global.organization_users
                            (id, organization_id, user_id, role, is_active, joined_at)
                        VALUES ($1, $2, $3, 'member', TRUE, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        str(uuid.uuid4()), org_id, user_id,
                    )

            await db.execute(
                """
                INSERT INTO members
                    (id, user_id, first_name, last_name, email,
                     is_active, joined_at)
                VALUES ($1, $2, $3, $4, $5, TRUE, NOW())
                """,
                member_id, user_id, m["first_name"], m["last_name"], email,
            )
            logger.info(f"Created member '{m['first_name']} {m['last_name']}' ({email})")

    logger.info("Seed data complete.")


if __name__ == "__main__":
    asyncio.run(seed())
