"""
AuraFlow — Permission Service

Action-level per-user permission system. Roles are STARTER TEMPLATES
only — owner picks a role when adding a staff member, the matching
template seeds a default set of permission keys for that user, and from
that moment on the owner edits each key individually on the staff
detail page. The backend gates every endpoint on a specific permission
key, NOT on role.

Owner is the only role with implicit bypass: an owner always has every
permission regardless of what's in the user_permissions table. Every
other role's access is decided purely by the per-user grants stored in
af_global.user_permissions.

Members get a fixed set of "own actions" permissions auto-granted on
signup (view_own_profile, book_self, etc.) — those aren't shown in the
staff PermissionMatrix UI because they apply to every member by
definition.

Cache: each (org, user) → permission list is Redis-cached for 5 min.
Cache is invalidated on any set/revoke.
"""
import json
from typing import Optional

from app.core.logging import logger


# ── Permission Keys (action-level, one per gated action in the API) ────────
#
# Naming: <area>.<verb> or <area>.<verb>_<qualifier>
# - <verb> is action-oriented (view, edit, create, delete, send, etc.)
# - <qualifier> distinguishes "own vs all" or "self vs others" where it matters
#
# This list is the single source of truth: the staff page reads it via
# /staff/permissions/defaults and the PermissionMatrix UI renders one
# toggle per key. Adding a new gated endpoint = add a key here + use it
# in require_permission(...) on the endpoint.

ALL_PERMISSIONS: list[str] = [
    # AI assistant
    "ai.analyze_retention",
    "ai.analyze_schedule",
    "ai.approve_draft",
    "ai.approve_pricing",
    "ai.create_draft",
    "ai.create_pricing_rule",
    "ai.delete_pricing_rule",
    "ai.edit_draft",
    "ai.edit_pricing_rule",
    "ai.generate_class_description",
    "ai.generate_marketing",
    "ai.generate_milestones_video",
    "ai.manage_resolutions",
    "ai.manage_retention",
    "ai.manage_waitlist",
    "ai.moderate_reviews",
    "ai.outreach_retention",
    "ai.respond_reviews",
    "ai.suggest_pricing",
    "ai.view_draft",
    "ai.view_member_insight",
    "ai.view_milestones",
    "ai.view_pricing",
    "ai.view_resolutions",
    "ai.view_retention",
    "ai.view_reviews",
    "ai.view_waitlist",

    # Analytics + reports
    "analytics.export_payroll",
    "analytics.view_activity",
    "analytics.view_attendance",
    "analytics.view_dashboard",
    "analytics.view_instructors",
    "analytics.view_members",
    "analytics.view_memberships",
    "analytics.view_payroll",
    "analytics.view_revenue",
    "analytics.view_rooms",
    "analytics.view_video",
    "audit.view",

    # Billing + org subscription
    "billing.apply_coupon",
    "billing.cancel",
    "billing.change_plan",
    "billing.reactivate",
    "billing.view_billing",
    "billing.view_discount",
    "billing.view_invoices",
    "billing.view_plans",

    # Communications (email + SMS providers, social, Zoom)
    "communications.configure_zoom",
    "communications.connect_email",
    "communications.connect_facebook",
    "communications.connect_instagram",
    "communications.connect_sms",
    "communications.connect_zoom",
    "communications.create_social_post",
    "communications.delete_social_post",
    "communications.disconnect_email",
    "communications.disconnect_sms",
    "communications.disconnect_social",
    "communications.disconnect_zoom",
    "communications.manage_inbox",
    "communications.manage_messages",
    "communications.publish_social_post",
    "communications.reply_inbox",
    "communications.test_email",
    "communications.test_sms",
    "communications.test_zoom",
    "communications.view_inbox",
    "communications.view_log",
    "communications.view_messages",
    "communications.view_social_posts",
    "communications.view_stats",
    "communications.view_status",
    "communications.view_team",

    # Contracts (guest workshop agreements, etc.)
    "contracts.create_guest_workshop",
    "contracts.manage",
    "contracts.prepare",
    "contracts.view",

    # Engagement (win-back, milestone campaigns)
    "engagement.configure",
    "engagement.manage_campaigns",
    "engagement.view_campaigns",
    "engagement.view_log",
    "engagement.view_settings",
    "engagement.view_stats",

    # Facilities
    "facilities.complete_schedule",
    "facilities.create_equipment",
    "facilities.create_maintenance",
    "facilities.create_schedule",
    "facilities.delete_equipment",
    "facilities.delete_schedule",
    "facilities.edit_equipment",
    "facilities.edit_rooms",
    "facilities.edit_schedule",
    "facilities.manage_maintenance",
    "facilities.view_equipment",
    "facilities.view_maintenance",
    "facilities.view_schedules",

    # Gift cards
    "gift_cards.apply",
    "gift_cards.manage",
    "gift_cards.purchase",
    "gift_cards.view",
    "gift_cards.view_own",
    "gift_cards.view_stats",

    # Hiring / applicant tracking + onboarding
    "hiring.view",            # view job applications + pipeline
    "hiring.manage",          # update status/rating/reviewer, add notes
    "hiring.hire",            # run the hire action (creates staff/instructor)
    "hiring.view_w4",         # view a hired employee's W-4 incl. decrypted SSN (restricted)
    "hiring.manage_employer", # edit the studio's employer profile + onboarding settings

    # Import / export
    "import.ai_analyze",
    "import.ai_execute",
    "import.ai_interact",
    "import.ai_preview",
    "import.execute",
    "import.execute_instructors",
    "import.execute_members",
    "import.execute_memberships",
    "import.execute_schedule",
    "import.execute_stripe",
    "import.preview",
    "import.preview_stripe",
    "import.view_status",

    # Instructors (staff side; "their own" things are under payroll/time_clock)
    "instructors.delete",
    "instructors.delete_guest",
    "instructors.edit",
    "instructors.edit_guest",
    "instructors.manage_availability",
    "instructors.view_guest",
    "instructors.view_schedule",

    # Integrations (ClassPass, GMB, EMR, Mailchimp, Stripe Connect)
    "integrations.connect_classpass",
    "integrations.connect_emr",
    "integrations.connect_gmb",
    "integrations.connect_mailchimp",
    "integrations.configure_classpass",
    "integrations.disconnect_classpass",
    "integrations.disconnect_emr",
    "integrations.disconnect_gmb",
    "integrations.disconnect_mailchimp",
    "integrations.manage_classpass_data",
    "integrations.manage_gmb",
    "integrations.oauth_callback",
    "integrations.respond_gmb",
    "integrations.sync_emr",
    "integrations.sync_gmb",
    "integrations.sync_mailchimp",
    "integrations.test_emr",
    "integrations.view_classpass",
    "integrations.view_classpass_data",
    "integrations.view_emr",
    "integrations.view_gmb",
    "integrations.view_mailchimp",

    # Marketing (email + SMS campaigns, Google Ads, Meta Ads)
    "marketing.manage_ads",
    "marketing.view_ads",
    "marketing.cancel_sms_campaign",
    "marketing.create_campaign",
    "marketing.create_sms_campaign",
    "marketing.create_sms_template",
    "marketing.delete_campaign",
    "marketing.delete_sms_campaign",
    "marketing.delete_sms_template",
    "marketing.edit_campaign",
    "marketing.edit_sms_campaign",
    "marketing.edit_sms_template",
    "marketing.schedule_sms_campaign",
    "marketing.send_campaign",
    "marketing.send_sms",
    "marketing.send_sms_campaign",
    "marketing.view_campaigns",
    "marketing.view_sms",
    "marketing.view_sms_campaigns",
    "marketing.view_sms_templates",

    # Members (staff side)
    "members.create",
    "members.create_note",
    "members.delete",
    "members.delete_note",
    "members.edit",
    "members.edit_health",
    "members.grant_credits",
    "members.invite",
    "members.remove",
    "members.revoke_credits",
    "members.view",
    "members.view_all",
    "members.view_bookings",
    "members.view_credits",
    "members.view_health",
    "members.view_memberships",
    "members.view_notes",
    "members.view_payments",
    "members.view_private_sessions",

    # Member-portal "own actions" — auto-granted to every member, not shown in staff matrix
    "members.create_review",
    "members.edit_own_profile",
    "members.view_own_profile",
    "members.view_own_reviews",
    "members.view_reviewable",

    # Memberships (staff side)
    "memberships.assign",
    "memberships.cancel",
    "memberships.create_type",
    "memberships.delete_type",
    "memberships.edit_type",
    "memberships.freeze",
    "memberships.seed_defaults",
    "memberships.unfreeze",
    "memberships.view_active",
    "memberships.view_templates",

    # Memberships member-portal "own actions"
    "memberships.cancel_own",
    "memberships.pause_own",
    "memberships.purchase",
    "memberships.purchase_with_gift_card",
    "memberships.resume_own",
    "memberships.view_own",
    "memberships.view_public",

    # Office manager (substitution requests, inventory alerts)
    "office_management.manage_requests",
    "office_management.view_inventory",
    "office_management.view_log",
    "office_management.view_requests",
    "office_management.view_stats",

    # Payments (Stripe Connect, refunds, drop-ins)
    "payments.charge_drop_in",
    "payments.charge_square",
    "payments.create_checkout",
    "payments.create_portal",
    "payments.manage_own",
    "payments.record_drop_in",
    "payments.record_transaction",
    "payments.refund_transaction",
    "payments.setup_connect",
    "payments.verify_checkout",
    "payments.view_connect_status",
    "payments.view_failed",
    "payments.view_log",
    "payments.view_own",
    "payments.view_revenue",
    "payments.view_transactions",

    # POS (Square Terminal API + saved-card charges)
    "pos.charge",
    "pos.charge_saved_card",
    "pos.manage_devices",

    # Payroll + time clock
    "payroll.approve_entries",
    "payroll.clock_in",
    "payroll.clock_out",
    "payroll.compile",
    "payroll.connect_gusto",
    "payroll.connect_quickbooks",
    "payroll.delete_run",
    "payroll.disconnect_gusto",
    "payroll.disconnect_quickbooks",
    "payroll.export_csv",
    "payroll.finalize",
    "payroll.manage_mappings",
    "payroll.mark_paid",
    "payroll.push_gusto",
    "payroll.push_quickbooks",
    "payroll.reject_entries",
    "payroll.view_clock_status",
    "payroll.view_export_status",
    "payroll.view_gusto",
    "payroll.view_history",
    "payroll.view_mappings",
    "payroll.view_own_timesheet",
    "payroll.view_quickbooks",
    "payroll.view_report",
    "payroll.view_runs",
    "payroll.view_timesheets",

    # Privacy / GDPR (admin side; members get their own auto-grants)
    "privacy.cancel_deletion",
    "privacy.export_data",
    "privacy.export_member",
    "privacy.manage_preferences",
    "privacy.request_deletion",
    "privacy.view_deletion_status",

    # Private sessions (staff side)
    "private_sessions.block_time",
    "private_sessions.book",
    "private_sessions.cancel_booking",
    "private_sessions.complete_booking",
    "private_sessions.confirm_booking",
    "private_sessions.create_service",
    "private_sessions.delete_service",
    "private_sessions.edit_service",
    "private_sessions.send_payment_link",
    "private_sessions.set_availability",

    # Private sessions member-portal "own actions"
    "private_sessions.book_self",
    "private_sessions.cancel_own",
    "private_sessions.view_availability",
    "private_sessions.view_own_bookings",
    "private_sessions.view_public",

    # Retail / POS
    "retail.adjust_inventory",
    "retail.checkout_transaction",
    "retail.create_product",
    "retail.delete_product",
    "retail.edit_product",
    "retail.record_transaction",
    "retail.refund_transaction",
    "retail.resend_payment_link",
    "retail.view_inventory",
    "retail.view_products",
    "retail.view_reports",
    "retail.view_transactions",

    # Schedule (class types, series, sessions, bookings)
    "schedule.cancel_booking",
    "schedule.check_in",
    "schedule.create_admin_booking",
    "schedule.create_class_type",
    "schedule.create_session",
    "schedule.create_series",
    "schedule.delete_class_type",
    "schedule.delete_series",
    "schedule.delete_session",
    "schedule.edit_class_type",
    "schedule.edit_series",
    "schedule.edit_session",
    "schedule.manage_series",
    "schedule.no_show",

    # Schedule member-portal "own actions"
    "schedule.cancel_own_booking",
    "schedule.create_booking",
    "schedule.view_own_bookings",
    "schedule.view_public",
    "schedule.view_suggestions",

    # Settings (org, custom domain, features, onboarding, webhooks)
    "settings.add_custom_domain",
    "settings.delete_custom_domain",
    "settings.delete_organization",
    "settings.edit_organization",
    "settings.manage_custom_domain",
    "settings.manage_features",
    "settings.manage_onboarding",
    "settings.manage_webhooks",
    "settings.view_cancellation_status",
    "settings.view_custom_domain",
    "settings.view_features",
    "settings.view_webhooks",

    # Staff management (invite, deactivate, set permissions)
    "staff.create_assignment",
    "staff.delete_assignment",
    "staff.edit_assignment",
    "staff.edit_profile",
    "staff.invite",
    "staff.set_permissions",
    "staff.set_role",
    "staff.view",
    "staff.view_assignments",

    # Studios + rooms
    "studios.create_room",
    "studios.delete",
    "studios.delete_room",
    "studios.edit",
    "studios.edit_room",
    "studios.view",

    # Video library + providers
    "video.browse",
    "video.connect_mux",
    "video.connect_youtube",
    "video.create_category",
    "video.delete_category",
    "video.delete_video",
    "video.disconnect_mux",
    "video.disconnect_youtube",
    "video.edit_category",
    "video.edit_video",
    "video.record_view",
    "video.start_youtube_oauth",
    "video.sync_videos",
    "video.test_mux",
    "video.test_youtube",
    "video.upload",
    "video.view_categories",
    "video.view_library",
    "video.view_stats",
    "video.view_youtube_oauth_status",

    # Voice check-in (kiosk / phone)
    "voice.handle_command",
    "voice.handle_sms_checkin",
    "voice.handle_voice_checkin",
    "voice.transcribe",

    # Waivers
    "waivers.create_template",
    "waivers.sign",
    "waivers.view_active_template",
    "waivers.view_for_signing",
    "waivers.view_signatures",
    "waivers.view_status",
    "waivers.view_templates",
    "waivers.view_unsigned",

    # Workshops + courses
    "workshops.cancel",
    "workshops.complete",
    "workshops.create",
    "workshops.delete",
    "workshops.edit",
    "workshops.enroll_member",
    "workshops.manage_sessions",
    "workshops.publish",
    "workshops.record_attendance",
    "workshops.upload_flyer",
    "workshops.view_attendance",
    "workshops.view_enrollments",
    "workshops.withdraw_member",

    # Workshops member-portal "own actions"
    "workshops.enroll_self",
    "workshops.view_own_enrollments",
    "workshops.view_public",
    "workshops.withdraw_self",
]


# ── Role templates — STARTER PACKS, not enforced controls ──────────────────
#
# These are pre-built bundles owner picks from when adding a new staff
# member. They seed user_permissions but the owner edits each key
# individually after that. Changing a user's role later does NOT
# re-apply the template (deliberate — it would clobber prior custom
# tweaks). Owner can hit "Apply template" on the staff page to bulk-set
# from a template if they want to start over.
#
# OWNER is special-cased in code (PermissionService.has_permission) —
# always grants every permission. No template needed.
#
# MEMBER gets the "own actions" only and is auto-granted on member
# signup via initialize_default_permissions.

# Member-portal "own actions" — auto-granted when role=member is created.
_MEMBER_OWN_ACTIONS = [
    "gift_cards.apply",
    "gift_cards.view_own",
    "members.create_review",
    "members.edit_own_profile",
    "members.view_own_profile",
    "members.view_own_reviews",
    "members.view_reviewable",
    "memberships.cancel_own",
    "memberships.pause_own",
    "memberships.purchase",
    "memberships.purchase_with_gift_card",
    "memberships.resume_own",
    "memberships.view_own",
    "memberships.view_public",
    "payments.manage_own",
    "payments.verify_checkout",
    "payments.view_own",
    "privacy.cancel_deletion",
    "privacy.export_data",
    "privacy.manage_preferences",
    "privacy.request_deletion",
    "privacy.view_deletion_status",
    "private_sessions.book_self",
    "private_sessions.cancel_own",
    "private_sessions.view_availability",
    "private_sessions.view_own_bookings",
    "private_sessions.view_public",
    "schedule.cancel_own_booking",
    "schedule.create_booking",
    "schedule.view_own_bookings",
    "schedule.view_public",
    "schedule.view_suggestions",
    "video.browse",
    "video.record_view",
    "video.view_categories",
    "waivers.sign",
    "waivers.view_for_signing",
    "workshops.enroll_self",
    "workshops.view_own_enrollments",
    "workshops.view_public",
    "workshops.withdraw_self",
]

# Front Desk — checking members in, taking payments at the desk, basic schedule ops.
_FRONT_DESK_TEMPLATE = [
    "analytics.view_dashboard",
    "communications.view_inbox",
    "communications.view_status",
    "contracts.prepare",
    "contracts.view",
    "facilities.create_maintenance",
    "facilities.view_equipment",
    "facilities.view_maintenance",
    "facilities.view_schedules",
    "gift_cards.apply",
    "members.create_note",
    "members.edit",
    "members.view",
    "members.view_all",
    "members.view_bookings",
    "members.view_credits",
    "members.view_memberships",
    "members.view_notes",
    "members.view_payments",
    "memberships.assign",
    "memberships.purchase_with_gift_card",
    "payments.charge_drop_in",
    "payments.create_checkout",
    "payments.create_portal",
    "payments.record_drop_in",
    "payments.record_transaction",
    "payments.verify_checkout",
    "payments.view_transactions",
    "pos.charge",
    "pos.charge_saved_card",
    "payroll.clock_in",
    "payroll.clock_out",
    "payroll.view_clock_status",
    "payroll.view_own_timesheet",
    "private_sessions.book",
    "private_sessions.cancel_booking",
    "private_sessions.send_payment_link",
    "retail.checkout_transaction",
    "retail.record_transaction",
    "retail.resend_payment_link",
    "retail.view_inventory",
    "retail.view_products",
    "retail.view_transactions",
    "schedule.cancel_booking",
    "schedule.check_in",
    "schedule.create_admin_booking",
    "schedule.no_show",
    "waivers.view_status",
    "workshops.enroll_member",
]

# Instructor — teaching their classes, running their private sessions,
# basic studio visibility. ALSO includes the full _MEMBER_OWN_ACTIONS
# bundle so an instructor can use the studio as a member themselves
# (book classes, view their own profile, sign waivers, etc.). The
# "own actions" are inherently scoped to the caller's own user_id —
# granting them doesn't expose anyone else's data.
_INSTRUCTOR_TEMPLATE = list(_MEMBER_OWN_ACTIONS) + [
    "ai.generate_class_description",
    "analytics.view_dashboard",
    "communications.manage_inbox",
    "communications.reply_inbox",
    "communications.view_inbox",
    "contracts.create_guest_workshop",
    "facilities.create_maintenance",
    "facilities.view_equipment",
    "facilities.view_maintenance",
    "facilities.view_schedules",
    "instructors.view_schedule",
    "members.create_note",
    "members.view",
    "members.view_bookings",
    "members.view_credits",
    "members.view_memberships",
    "members.view_notes",
    "members.view_private_sessions",
    "payroll.clock_in",
    "payroll.clock_out",
    "payroll.view_clock_status",
    "payroll.view_own_timesheet",
    "private_sessions.block_time",
    "private_sessions.book",
    "private_sessions.complete_booking",
    "private_sessions.confirm_booking",
    "private_sessions.create_service",
    "private_sessions.edit_service",
    "private_sessions.send_payment_link",
    "private_sessions.set_availability",
    "schedule.create_admin_booking",
    "schedule.edit_session",
    "schedule.check_in",
    "video.browse",
    "video.view_categories",
    "video.view_library",
    "waivers.view_status",
    "workshops.record_attendance",
    "workshops.view_attendance",
    "workshops.view_enrollments",
]

# Manager — almost-everything, minus the sensitive money / staff-management knobs.
# (Replaces the old "admin" template which was effectively a quiet owner.)
# Owner removes whatever they don't want any given manager to have.
_MANAGER_TEMPLATE = [k for k in ALL_PERMISSIONS if k not in {
    # Money movement that should require explicit owner OK
    "payroll.run_payout" if False else "payroll.compile",  # keep for managers actually
    "payroll.finalize",
    "payroll.mark_paid",
    "payroll.delete_run",
    "payroll.push_gusto",
    "payroll.push_quickbooks",
    # Org-level configuration
    "billing.cancel",
    "billing.change_plan",
    "billing.reactivate",
    "billing.apply_coupon",
    "settings.delete_organization",
    "settings.add_custom_domain",
    "settings.delete_custom_domain",
    "settings.manage_custom_domain",
    # Staff permissions / role management (owner-only)
    "staff.set_permissions",
    "staff.set_role",
    # W-4 SSN access is owner-only by default; grant per-user to a trusted
    # manager via the permission matrix. (hiring.view/manage/hire ARE managers'.)
    "hiring.view_w4",
    # Member-portal own-actions (members get those automatically; managers don't impersonate)
    *_MEMBER_OWN_ACTIONS,
}]


DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": list(ALL_PERMISSIONS),  # implicit anyway; listed for completeness
    "admin": _MANAGER_TEMPLATE,      # legacy name kept; semantically a manager template
    "manager": _MANAGER_TEMPLATE,
    "instructor": _INSTRUCTOR_TEMPLATE,
    "front_desk": _FRONT_DESK_TEMPLATE,
    "member": _MEMBER_OWN_ACTIONS,
}


class PermissionService:
    """
    Per-user permission lookup with Redis cache.

    Owner and platform_admin bypass all checks — they always have every
    permission. Every other user's access is the exact set of keys
    granted in af_global.user_permissions (set per-user by an owner).

    The keys stored in user_permissions MUST exist in ALL_PERMISSIONS;
    unknown keys are silently dropped on set (defensive) so a stale UI
    can't grant access to a permission key the backend doesn't know
    about.
    """

    CACHE_TTL = 300  # 5 minutes

    async def get_user_permissions(
        self,
        organization_id: str,
        user_id: str,
        role: str,
    ) -> list[str]:
        """Return the granted permission keys for a user in an org.
        Owner returns ALL_PERMISSIONS unconditionally."""
        if role == "owner":
            return list(ALL_PERMISSIONS)

        cache_key = f"perms:{organization_id}:{user_id}"
        from app.core.redis import get_redis
        redis = await get_redis()

        if redis:
            cached = await redis.get(cache_key)
            if cached is not None:
                return json.loads(cached)

        permissions = await self._load_from_db(organization_id, user_id)

        if redis:
            await redis.setex(cache_key, self.CACHE_TTL, json.dumps(permissions))

        return permissions

    async def has_permission(
        self,
        organization_id: str,
        user_id: str,
        role: str,
        permission_key: str,
    ) -> bool:
        """Check if a user has a specific permission. Owner always True."""
        if role == "owner":
            return True
        permissions = await self.get_user_permissions(organization_id, user_id, role)
        return permission_key in permissions

    async def set_user_permissions(
        self,
        organization_id: str,
        user_id: str,
        permissions: dict[str, bool],
        granted_by: str,
    ) -> None:
        """
        Bulk set permissions for a user. Upserts each known key,
        silently drops keys not in ALL_PERMISSIONS, invalidates cache.
        """
        from app.db.session import get_global_db

        async with get_global_db() as db:
            for perm_key, is_granted in permissions.items():
                if perm_key not in ALL_PERMISSIONS:
                    continue
                await db.execute(
                    """
                    INSERT INTO af_global.user_permissions
                        (organization_id, user_id, permission_key, is_granted, granted_by)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (organization_id, user_id, permission_key)
                    DO UPDATE SET
                        is_granted = EXCLUDED.is_granted,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    organization_id, user_id, perm_key, is_granted, granted_by,
                )

        await self._invalidate_cache(organization_id, user_id)
        logger.info(
            "User permissions updated",
            org_id=organization_id,
            user_id=user_id,
            count=len(permissions),
        )

    async def initialize_default_permissions(
        self,
        organization_id: str,
        user_id: str,
        role: str,
    ) -> None:
        """Seed default permissions for a user from their role's template.
        Called when a user is first invited to an organization. The
        owner can edit each key freely afterwards; changing role later
        does NOT re-seed (would clobber custom tweaks)."""
        defaults = DEFAULT_ROLE_PERMISSIONS.get(role, [])
        if not defaults:
            return

        permissions = {key: True for key in defaults}
        await self.set_user_permissions(
            organization_id, user_id, permissions, granted_by=user_id,
        )
        logger.info(
            "Default permissions seeded",
            org_id=organization_id,
            user_id=user_id,
            role=role,
            count=len(defaults),
        )

    async def apply_template(
        self,
        organization_id: str,
        user_id: str,
        role: str,
        granted_by: str,
    ) -> None:
        """Bulk-reset a user's permissions to their role template.
        Triggered by the "Apply template" button on the staff page —
        wipes existing custom grants and starts fresh."""
        from app.db.session import get_global_db

        async with get_global_db() as db:
            await db.execute(
                "DELETE FROM af_global.user_permissions "
                "WHERE organization_id = $1 AND user_id = $2",
                organization_id, user_id,
            )

        defaults = DEFAULT_ROLE_PERMISSIONS.get(role, [])
        if defaults:
            permissions = {key: True for key in defaults}
            await self.set_user_permissions(
                organization_id, user_id, permissions, granted_by=granted_by,
            )

        await self._invalidate_cache(organization_id, user_id)
        logger.info(
            "Permissions reset to role template",
            org_id=organization_id,
            user_id=user_id,
            role=role,
            applied_keys=len(defaults),
        )

    async def _load_from_db(
        self,
        organization_id: str,
        user_id: str,
    ) -> list[str]:
        from app.db.session import get_global_db

        async with get_global_db() as db:
            rows = await db.fetch(
                """
                SELECT permission_key
                FROM af_global.user_permissions
                WHERE organization_id = $1
                  AND user_id = $2
                  AND is_granted = TRUE
                """,
                organization_id, user_id,
            )

        return [row["permission_key"] for row in rows]

    async def _invalidate_cache(
        self,
        organization_id: str,
        user_id: str,
    ) -> None:
        from app.core.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.delete(f"perms:{organization_id}:{user_id}")


# Singleton
permission_service = PermissionService()
