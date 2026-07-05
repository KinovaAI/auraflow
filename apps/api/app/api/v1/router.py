"""
AuraFlow API v1 Router
All routes registered here with their prefixes and tags.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    users,
    organizations,
    staff,
    studios,
    studio_assignments,
    scheduling,
    instructors,
    guest_instructors,
    hiring,
    private_sessions,
    payroll,
    members,
    memberships,
    payments,
    video,
    courses,
    marketing,
    google_ads,
    meta_ads,
    analytics,
    ai,
    ai_usage,
    import_export,
    integrations,
    zoom,
    communications,
    time_clock,
    payroll_export,
    facilities,
    retail,
    platform_infrastructure,
    platform_health,
    public,
    member_portal,
    ai_manager,
    voice,
    admin_data,
    notifications,
    activity,
    webhook_configs,
    onboarding,
    chatbot,
    waivers,
    gdpr,
    email_preferences,
    support,
    gift_cards,
    office_manager,
    engagement,
    studio_email,
    studio_social,
    kiosk_devices,
    save_card,
    self_serve,
    managed_billing,
)
from app.api.v1.endpoints.external.router import router as external_router
from app.api.v1.endpoints.contracts import router as contracts_router, external_router as contracts_external_router

api_router = APIRouter()

# ── Authentication (no tenant required) ──────────────────────────────────────
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

# ── Public hosted card-save (JWT-authed, no tenant context required) ────────
api_router.include_router(
    save_card.router,
    tags=["SaveCard"],
)

# ── Public self-serve online-membership signup (no tenant required) ─────────
api_router.include_router(
    self_serve.router,
    prefix="/self-serve",
    tags=["SelfServe"],
)

# ── Self-host managed-billing settings (open-core; admin-gated proxy) ────────
api_router.include_router(
    managed_billing.router,
    tags=["ManagedBilling"],
)

# ── User Profile ─────────────────────────────────────────────────────────────
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["Users"]
)

# ── Organization Management ───────────────────────────────────────────────────
api_router.include_router(
    organizations.router,
    prefix="/organizations",
    tags=["Organizations"]
)

# ── Staff Management ───────────────────────────────────────────────────────
api_router.include_router(
    staff.router,
    prefix="/staff",
    tags=["Staff Management"]
)

# ── Hiring / Applicant Tracking + Onboarding (W-4) ────────────────────────────
api_router.include_router(
    hiring.router,
    prefix="/hiring",
    tags=["Hiring"]
)

# ── Studio Locations ──────────────────────────────────────────────────────────
api_router.include_router(
    studios.router,
    prefix="/studios",
    tags=["Studios"]
)

# ── Studio Staff Assignments (per-location roles) ───────────────────────────
api_router.include_router(
    studio_assignments.router,
    prefix="/studios",
    tags=["Studio Assignments"]
)

# ── Group Class Scheduling ────────────────────────────────────────────────────
api_router.include_router(
    scheduling.router,
    prefix="/scheduling",
    tags=["Scheduling — Group Classes"]
)

# ── Instructors ──────────────────────────────────────────────────────────────
api_router.include_router(
    instructors.router,
    prefix="/instructors",
    tags=["Instructors"]
)

# ── Guest Instructors (1099 contractors — workshops only) ────────────────────
# Separate from staff `instructors` by design: different table, different
# tax treatment, different UI. CA labor law forbids 1099 contractors
# from teaching regular classes — enforced both here and at the DB level.
api_router.include_router(
    guest_instructors.router,
    prefix="/guest-instructors",
    tags=["Guest Instructors"]
)

# ── Private Session Scheduling ────────────────────────────────────────────────
api_router.include_router(
    private_sessions.router,
    prefix="/private-sessions",
    tags=["Scheduling — Private Sessions"]
)

# ── Members ───────────────────────────────────────────────────────────────────
api_router.include_router(
    members.router,
    prefix="/members",
    tags=["Members"]
)

# ── Memberships & Packages ────────────────────────────────────────────────────
api_router.include_router(
    memberships.router,
    prefix="/memberships",
    tags=["Memberships & Packages"]
)

# ── Payments & POS ────────────────────────────────────────────────────────────
api_router.include_router(
    payments.router,
    prefix="/payments",
    tags=["Payments & POS"]
)

# ── Video Library ─────────────────────────────────────────────────────────────
api_router.include_router(
    video.router,
    prefix="/video",
    tags=["Video Library"]
)

# ── Workshops & Teacher Training ──────────────────────────────────────────────
api_router.include_router(
    courses.router,
    prefix="/courses",
    tags=["Workshops & Teacher Training"]
)

# ── Marketing & Email ─────────────────────────────────────────────────────────
api_router.include_router(
    marketing.router,
    prefix="/marketing",
    tags=["Marketing & Email"]
)

# ── Google Ads (AI-managed) ───────────────────────────────────────────────────
api_router.include_router(
    google_ads.router,
    prefix="/google-ads",
    tags=["Google Ads"]
)

# ── Meta/Facebook Ads (AI-managed) ──────────────────────────────────────────
api_router.include_router(
    meta_ads.router,
    prefix="/meta-ads",
    tags=["Meta Ads"]
)

# ── Analytics & Reporting ─────────────────────────────────────────────────────
api_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["Analytics & Reporting"]
)

# ── AI Features ───────────────────────────────────────────────────────────────
api_router.include_router(
    ai.router,
    prefix="/ai",
    tags=["AI Features"]
)

# ── AI Token Usage & Billing ──────────────────────────────────────────────────
api_router.include_router(
    ai_usage.router,
    prefix="/ai",
    tags=["AI Token Billing"]
)

# ── Import / Export ──────────────────────────────────────────────────────────
api_router.include_router(
    import_export.router,
    prefix="/import",
    tags=["Import / Export"]
)

# ── Integrations (ClassPass etc.) ─────────────────────────────────────────────
api_router.include_router(
    integrations.router,
    prefix="/integrations",
    tags=["Integrations"]
)

# ── Zoom Integration ─────────────────────────────────────────────────────────
api_router.include_router(
    zoom.router,
    prefix="/integrations/zoom",
    tags=["Zoom Integration"]
)

# ── Communications Settings ──────────────────────────────────────────────────
api_router.include_router(
    communications.router,
    prefix="/integrations/communications",
    tags=["Communications"]
)

# ── Time Clock & Payroll ─────────────────────────────────────────────────────
api_router.include_router(
    time_clock.router,
    prefix="/time-clock",
    tags=["Time Clock & Payroll"]
)

# ── Instructor Payroll / Compensation ───────────────────────────────────────
api_router.include_router(
    payroll.router,
    prefix="/payroll",
    tags=["Instructor Payroll"]
)

# ── Payroll Export & Integrations ────────────────────────────────────────────
api_router.include_router(
    payroll_export.router,
    prefix="/payroll-export",
    tags=["Payroll Export & Integrations"]
)

# ── Facility Management ────────────────────────────────────────────────────
api_router.include_router(
    facilities.router,
    prefix="/facilities",
    tags=["Facility Management"]
)

# ── Retail & POS ────────────────────────────────────────────────────────────
api_router.include_router(
    retail.router,
    prefix="/retail",
    tags=["Retail & POS"]
)

# ── Platform Infrastructure (self-host: DB/backups/monitoring) ───────────────
api_router.include_router(
    platform_infrastructure.router,
    prefix="/platform/infrastructure",
    tags=["Platform Infrastructure"]
)

# ── Platform System Health (self-host: DB/Redis/Celery status) ───────────────
api_router.include_router(
    platform_health.router,
    prefix="/platform/health",
    tags=["Platform Health"]
)

# ── Public Schedule (no auth) ────────────────────────────────────────────────
api_router.include_router(
    public.router,
    prefix="/public",
    tags=["Public Schedule"]
)

# ── Public Tenant Branding (no auth) ────────────────────────────────────────
# Read-only consumer-of-record for the white-label portal template.
from app.api.v1.endpoints import public_branding  # local import to keep top-of-file clean
api_router.include_router(
    public_branding.router,
    prefix="/public",
    tags=["Public Tenant Branding"]
)

# ── Portal Setup Wizard (Phase 5 — JWT admin/owner) ─────────────────────────
# Powers the onboarding wizard at /dashboard/settings/portal-setup
from app.api.v1.endpoints import portal_setup
api_router.include_router(
    portal_setup.router,
    prefix="/admin",
    tags=["Portal Setup"]
)

# ── Member Portal (self-service) ─────────────────────────────────────────────
api_router.include_router(
    member_portal.router,
    prefix="/portal",
    tags=["Member Portal"]
)

# ── AI Manager (resolutions + Sub-Finder) ────────────────────────────────────
api_router.include_router(
    ai_manager.router,
    prefix="/ai-manager",
    tags=["AI Manager"]
)

# ── Voice (check-in + commands) ──────────────────────────────────────────────
api_router.include_router(
    voice.router,
    prefix="/voice",
    tags=["Voice"]
)

# ── Notifications ───────────────────────────────────────────────────────────
api_router.include_router(
    notifications.router,
    prefix="/notifications",
    tags=["Notifications"]
)

# ── Activity Feed ───────────────────────────────────────────────────────────
api_router.include_router(
    activity.router,
    prefix="/activity",
    tags=["Activity Feed"]
)

# ── Webhook Configs (admin/owner) ───────────────────────────────────────────
api_router.include_router(
    webhook_configs.router,
    prefix="/webhook-configs",
    tags=["Webhook Configs"]
)

# ── Onboarding Checklist ───────────────────────────────────────────────────
api_router.include_router(
    onboarding.router,
    prefix="/onboarding",
    tags=["Onboarding"]
)

# ── AI Chatbot ─────────────────────────────────────────────────────────────
api_router.include_router(
    chatbot.router,
    prefix="/chatbot",
    tags=["AI Chatbot"]
)

# ── Waivers (liability waiver management) ────────────────────────────────────
api_router.include_router(
    waivers.router,
    prefix="",
    tags=["Waivers"]
)

# ── GDPR & CCPA Compliance ──────────────────────────────────────────────────
api_router.include_router(
    gdpr.router,
    prefix="/gdpr",
    tags=["GDPR & CCPA"]
)

# ── Email Preferences / CAN-SPAM Unsubscribe (public, no auth) ─────────────
api_router.include_router(
    email_preferences.router,
    prefix="/email",
    tags=["Email Preferences"]
)

# ── Support Contact Form (public, no auth) ───────────────────────────────────
api_router.include_router(
    support.router,
    prefix="/support",
    tags=["Support"]
)

# ── Gift Cards ────────────────────────────────────────────────────────────────
api_router.include_router(
    gift_cards.router,
    prefix="/gift-cards",
    tags=["Gift Cards"]
)

# ── AI Office Manager ────────────────────────────────────────────────────────
api_router.include_router(
    office_manager.router,
    prefix="/office-manager",
    tags=["AI Office Manager"]
)

# ── AI Engagement Autopilot ──────────────────────────────────────────────────
api_router.include_router(
    engagement.router,
    prefix="/engagement",
    tags=["AI Engagement"]
)

# ── Studio Email Inbox (per-tenant AI inbox) ─────────────────────────────────
api_router.include_router(
    studio_email.router,
    prefix="/studio-email",
    tags=["Studio Email"]
)

# ── Studio Social Media (per-tenant Facebook/Instagram) ──────────────────────
api_router.include_router(
    studio_social.router,
    prefix="/social",
    tags=["Social Media"]
)

# ── Admin Data (audit log, communication log, video views) ──────────────────
api_router.include_router(
    admin_data.router,
    prefix="/admin",
    tags=["Admin Data"]
)

# ── Platform Admin Data (announcements, AI agent log, backup schedules) ─────
api_router.include_router(
    admin_data.platform_router,
    prefix="/platform",
    tags=["Platform Admin Data"]
)


# ── Workshop Contracts (admin) ───────────────────────────────────────────────
api_router.include_router(
    contracts_router,
    tags=["Workshop Contracts"],
)

# ── Kiosk Device Lockdown (owner-only register / list / revoke) ─────────────
api_router.include_router(
    kiosk_devices.router,
    prefix="/kiosk-devices",
    tags=["Kiosk Devices"],
)
# ── External API (API-key-authenticated, third-party integrations) ──────────
api_router.include_router(
    external_router,
    prefix="/external",
    tags=["External API"]
)
