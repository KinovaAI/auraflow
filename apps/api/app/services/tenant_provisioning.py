"""
AuraFlow — Tenant Provisioning Service

Called when a new studio signs up. Creates their database schema,
seeds default configuration, and sets up their Stripe Connect account.
"""
import re
import uuid
from typing import Optional

from app.core.logging import logger
from app.db.session import get_global_db


class TenantProvisioningService:
    """
    Provisions a new studio tenant.

    This is one of the most critical operations in the platform.
    It must be idempotent — safe to retry if it fails partway through.
    """

    @staticmethod
    def generate_schema_name(slug: str) -> str:
        """Convert org slug to a safe PostgreSQL schema name."""
        safe = re.sub(r"[^a-z0-9_]", "_", slug.lower())
        return f"af_tenant_{safe}"

    async def provision(
        self,
        organization_name: str,
        slug: str,
        owner_email: str,
        owner_first_name: str,
        owner_last_name: str,
        plan_id: str = "trial",
        timezone: str = "America/Los_Angeles",
    ) -> dict:
        """
        Full provisioning flow for a new studio.
        Returns organization and user details on success.
        """
        schema_name = self.generate_schema_name(slug)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())

        async with get_global_db() as db:
            async with db.transaction():
                # 1. Create or find the user
                existing_user = await db.fetchrow(
                    "SELECT id FROM af_global.users WHERE email = $1",
                    owner_email
                )

                if existing_user:
                    user_id = str(existing_user["id"])
                else:
                    await db.execute(
                        """
                        INSERT INTO af_global.users
                            (id, email, first_name, last_name, email_verified)
                        VALUES ($1, $2, $3, $4, FALSE)
                        """,
                        user_id, owner_email, owner_first_name, owner_last_name
                    )
                    logger.info("Created new user", user_id=user_id, email=owner_email)

                # 2. Create the organization
                await db.execute(
                    """
                    INSERT INTO af_global.organizations
                        (id, slug, name, schema_name, status, plan_id, timezone)
                    VALUES ($1, $2, $3, $4, 'trial', $5, $6)
                    ON CONFLICT (slug) DO NOTHING
                    """,
                    org_id, slug, organization_name, schema_name, plan_id, timezone
                )

                # Check if slug was taken
                org = await db.fetchrow(
                    "SELECT id, schema_name FROM af_global.organizations WHERE slug = $1",
                    slug
                )
                if not org:
                    raise ValueError(f"Failed to create organization with slug '{slug}'")

                org_id = str(org["id"])
                schema_name = org["schema_name"]

                # 3. Link user as owner
                await db.execute(
                    """
                    INSERT INTO af_global.organization_users
                        (organization_id, user_id, role, joined_at)
                    VALUES ($1, $2, 'owner', NOW())
                    ON CONFLICT (organization_id, user_id) DO NOTHING
                    """,
                    org_id, user_id
                )

                # 4. Provision the tenant schema via our SQL function
                await db.execute(
                    "SELECT af_global.provision_tenant_schema($1, $2)",
                    schema_name, org_id
                )
                # 4b. Add EMR integration tables
                await db.execute(
                    "SELECT af_global.add_emr_tables_to_schema($1)",
                    schema_name,
                )
                # 4c. Add API keys table
                await db.execute(
                    "SELECT af_global.add_api_keys_table($1)",
                    schema_name,
                )
                # 4d. Add gift card tables
                await db.execute(
                    "SELECT af_global.add_gift_card_tables($1)",
                    schema_name,
                )
                # 4e. Add sub request tables
                await db.execute(
                    "SELECT af_global.add_sub_requests_table($1)",
                    schema_name,
                )
                # 4f. Add hiring / applicant-tracking + W-4 tables
                await db.execute(
                    "SELECT af_global.add_hiring_tables_to_schema($1)",
                    schema_name,
                )
                # 4g. Add per-tenant employer profile (onboarding settings)
                await db.execute(
                    "SELECT af_global.add_employer_profile_to_schema($1)",
                    schema_name,
                )
                # 4h. Add onboarding packet + documents tables
                await db.execute(
                    "SELECT af_global.add_onboarding_tables_to_schema($1)",
                    schema_name,
                )
                # 4i. Add DE-34 new-hire report filing tracker
                await db.execute(
                    "SELECT af_global.add_de34_filings_to_schema($1)",
                    schema_name,
                )
                # 4j. Add self-serve online-membership trial + standing-Zoom fields
                await db.execute(
                    "SELECT af_global.add_online_membership_trial_fields($1)",
                    schema_name,
                )
                # 4k. Add per-tenant Accounting module tables
                await db.execute(
                    "SELECT af_global.add_accounting_tables_to_schema($1)",
                    schema_name,
                )
                await db.execute(
                    "SELECT af_global.add_accounting_income_link_to_schema($1)",
                    schema_name,
                )
                await db.execute(
                    "SELECT af_global.add_acct_vendor_rules_to_schema($1)",
                    schema_name,
                )
                await db.execute(
                    "SELECT af_global.add_acct_owner_draws_to_schema($1)",
                    schema_name,
                )
                logger.info(
                    "Tenant schema provisioned",
                    schema=schema_name,
                    org_id=org_id
                )

                # 5. Seed feature flags for this tenant based on plan
                await self._seed_feature_flags(db, org_id, plan_id)

                # 6. Seed a default studio location
                await db.execute(
                    f"""
                    INSERT INTO "{schema_name}".studios
                        (organization_id, name, slug, timezone, is_active)
                    VALUES ($1, $2, 'main', $3, TRUE)
                    """,
                    org_id, organization_name, timezone
                )

                # 6b. Seed default liability waiver
                default_waiver = (
                    "LIABILITY WAIVER, RELEASE OF CLAIMS, AND ASSUMPTION OF RISK AGREEMENT\n\n"
                    "PLEASE READ THIS DOCUMENT CAREFULLY BEFORE SIGNING. BY SIGNING BELOW, YOU ARE WAIVING CERTAIN LEGAL RIGHTS, INCLUDING THE RIGHT TO SUE.\n\n\n"
                    "1. ACKNOWLEDGMENT OF RISK\n\n"
                    "I acknowledge that participation in yoga, fitness, wellness classes, workshops, private sessions, and use of studio facilities (collectively, \"Activities\") involves inherent risks of physical injury. These risks include, but are not limited to, muscle strains, ligament sprains, bone fractures, joint injuries, dislocation, cardiovascular events, overexertion, dehydration, falls, and contact with other participants or equipment.\n\n"
                    "I understand that these risks cannot be fully eliminated regardless of the care taken to avoid injury, and I voluntarily assume all such risks, both known and unknown.\n\n\n"
                    "2. MEDICAL REPRESENTATION\n\n"
                    "I represent and warrant that I am physically and mentally capable of participating in the Activities. I have no medical conditions, injuries, or disabilities that would prevent or limit my safe participation, or I have obtained clearance from a licensed physician.\n\n"
                    "I agree to disclose any relevant medical conditions, injuries, pregnancy, recent surgeries, or physical limitations to my instructor before each session. I understand that instructors are not medical professionals and their guidance does not constitute medical advice.\n\n\n"
                    "3. RELEASE AND WAIVER OF LIABILITY\n\n"
                    "In consideration of being permitted to participate in the Activities and to use the studio facilities, equipment, and services, I hereby voluntarily release, waive, discharge, and covenant not to sue the studio, its owners, operators, officers, directors, employees, instructors, agents, and independent contractors (collectively, \"Released Parties\") from any and all liability, claims, demands, actions, causes of action, costs, and expenses of any nature arising out of or relating to my participation in the Activities, including but not limited to personal injury, death, or property damage, whether caused by the negligence of the Released Parties or otherwise.\n\n\n"
                    "4. INDEMNIFICATION\n\n"
                    "I agree to indemnify, defend, and hold harmless the Released Parties from and against any and all claims, damages, losses, costs, and expenses (including reasonable attorney fees) arising out of or resulting from my participation in the Activities or my breach of any representation made in this Agreement.\n\n\n"
                    "5. PERSONAL PROPERTY\n\n"
                    "The studio is not responsible for any loss, theft, or damage to personal property brought onto the premises. I agree to secure my belongings and use any provided storage at my own risk.\n\n\n"
                    "6. PHOTOGRAPHY AND MEDIA CONSENT\n\n"
                    "I understand that photographs, video recordings, or other media may be captured during classes or events for promotional, educational, or marketing purposes. I consent to the use of my likeness in such media unless I provide written notice to the studio opting out of this consent.\n\n\n"
                    "7. STUDIO POLICIES\n\n"
                    "I agree to comply with all posted studio rules, policies, and guidelines, including but not limited to arriving on time, maintaining personal hygiene, treating studio equipment with care, following instructor guidance, and showing respect to staff and fellow participants. The studio reserves the right to refuse service or revoke access for failure to comply with these policies.\n\n\n"
                    "8. EMERGENCY MEDICAL AUTHORIZATION\n\n"
                    "In the event of a medical emergency during my participation in the Activities, I authorize the studio and its staff to contact emergency medical services and to take reasonable steps to provide or arrange for medical care on my behalf. I assume all costs associated with any emergency medical treatment.\n\n\n"
                    "9. GOVERNING LAW AND JURISDICTION\n\n"
                    "This Agreement shall be governed by and construed in accordance with the laws of the state in which the studio operates. Any disputes arising under or in connection with this Agreement shall be resolved exclusively in the courts of that jurisdiction.\n\n\n"
                    "10. SEVERABILITY\n\n"
                    "If any provision of this Agreement is found to be invalid, illegal, or unenforceable by a court of competent jurisdiction, the remaining provisions shall continue in full force and effect.\n\n\n"
                    "11. ENTIRE AGREEMENT\n\n"
                    "This Agreement constitutes the entire agreement between the parties concerning its subject matter and supersedes all prior agreements, understandings, negotiations, and discussions, whether oral or written.\n\n\n"
                    "12. ACKNOWLEDGMENT AND CONSENT\n\n"
                    "By signing below, I acknowledge that I have read this Liability Waiver, Release of Claims, and Assumption of Risk Agreement in its entirety. I understand its terms and conditions and agree to be bound by them. I confirm that I am at least 18 years of age, or if under 18, that my parent or legal guardian has signed this Agreement on my behalf.\n\n"
                    "I understand that this waiver remains in effect for the duration of my membership, participation in Activities, or use of studio facilities, unless revoked in writing.\n\n"
                    "I am signing this Agreement voluntarily and of my own free will."
                )
                await db.execute(
                    f"""
                    INSERT INTO "{schema_name}".waiver_templates
                        (id, version, title, content, require_resign, expiration_days, is_active)
                    VALUES (gen_random_uuid(), 1, 'Liability Waiver & Release', $1, FALSE, 365, TRUE)
                    """,
                    default_waiver,
                )

                # 7. Assign any existing staff to the default studio
                await db.execute(
                    f"""
                    INSERT INTO "{schema_name}".studio_user_roles (studio_id, user_id, role, is_primary)
                    SELECT s.id, ou.user_id, ou.role, TRUE
                    FROM "{schema_name}".studios s
                    CROSS JOIN af_global.organization_users ou
                    WHERE ou.organization_id = $1
                      AND ou.role IN ('admin', 'instructor', 'front_desk')
                      AND ou.is_active = TRUE
                      AND s.is_active = TRUE
                    ON CONFLICT (studio_id, user_id) DO NOTHING
                    """,
                    org_id,
                )

        logger.info(
            "Tenant provisioning complete",
            org_id=org_id,
            slug=slug,
            schema=schema_name
        )

        return {
            "organization_id": org_id,
            "user_id": user_id,
            "slug": slug,
            "schema_name": schema_name,
        }

    async def _seed_feature_flags(self, db, org_id: str, plan_id: str):
        """Enable features based on subscription plan.

        Studio plan ($99/mo) gets ALL features. Enterprise is the same but
        with unlimited locations and custom pricing.
        """
        # All features — studio and enterprise get everything
        all_features = [
            "scheduling.group_classes",
            "scheduling.private_sessions",
            "scheduling.zoom_integration",
            "video.youtube_embed",
            "video.on_demand_library",
            "video.mux_hosting",
            "courses.workshops",
            "courses.teacher_training",
            "payments.pos_retail",
            "payments.gift_cards",
            "integrations.classpass",
            "integrations.emr",
            "integrations.api",
            "marketing.email_campaigns",
            "marketing.sms",
            "ai.newsletter_generator",
            "ai.churn_prediction",
            "ai.autonomous_resolution",
            "ai.engagement_autopilot",
            "ai.office_manager",
            "module.email",
            "studio.social_media",
            "studio.email_inbox",
            "multi_location",
        ]

        # Trial gets limited features, everything else gets all
        trial_features = [
            "scheduling.group_classes",
            "scheduling.private_sessions",
            "scheduling.zoom_integration",
            "video.youtube_embed",
            "module.email",
        ]

        features = trial_features if plan_id == "trial" else all_features

        for flag_key in features:
            await db.execute(
                """
                INSERT INTO af_global.feature_flags
                    (organization_id, flag_key, is_enabled)
                VALUES ($1, $2, TRUE)
                ON CONFLICT (organization_id, flag_key)
                DO UPDATE SET is_enabled = TRUE, updated_at = NOW()
                """,
                org_id, flag_key
            )

    async def deprovision(self, slug: str, hard_delete: bool = False) -> None:
        """
        Deprovision a tenant (studio churned).

        Soft delete: marks as cancelled, retains data for 90 days.
        Hard delete: drops the schema entirely (GDPR request).
        """
        async with get_global_db() as db:
            org = await db.fetchrow(
                "SELECT id, schema_name FROM af_global.organizations WHERE slug = $1",
                slug
            )
            if not org:
                raise ValueError(f"Organization '{slug}' not found")

            if hard_delete:
                # Drop schema entirely — irreversible
                await db.execute(
                    f'DROP SCHEMA IF EXISTS "{org["schema_name"]}" CASCADE'
                )
                await db.execute(
                    "DELETE FROM af_global.organizations WHERE id = $1",
                    org["id"]
                )
                logger.warning(
                    "Tenant schema hard deleted",
                    slug=slug,
                    schema=org["schema_name"]
                )
            else:
                # Soft delete
                await db.execute(
                    """
                    UPDATE af_global.organizations
                    SET status = 'cancelled', updated_at = NOW()
                    WHERE id = $1
                    """,
                    org["id"]
                )
                logger.info("Tenant soft deleted", slug=slug)
