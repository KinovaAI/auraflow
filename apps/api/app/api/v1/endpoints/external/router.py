from app.api.v1.endpoints.contracts import external_router as contracts_external_router
"""AuraFlow — External API Router

Aggregates all external API sub-routers under the /external prefix.
All endpoints use API key authentication unless otherwise noted.
"""
from fastapi import APIRouter

from app.api.v1.endpoints.external import (
    api_keys,
    members,
    scheduling,
    bookings,
    memberships,
    instructors,
    private_sessions,
    courses,
    events,
    guest_workshops,
    job_applications,
    onboarding,
    payments,
    mailchimp,
    portal_login,
    branding_admin,
    connect_status,
    kiosk_session,
    magic_link,
)

router = APIRouter()

# API key management (uses JWT auth, not API key auth)
router.include_router(api_keys.router, tags=["External — API Keys"])

# Members CRUD
router.include_router(members.router, tags=["External — Members"])

# Class types & sessions
router.include_router(scheduling.router, tags=["External — Scheduling"])

# Bookings
router.include_router(bookings.router, tags=["External — Bookings"])

# Memberships
router.include_router(memberships.router, tags=["External — Memberships"])

# Instructors
router.include_router(instructors.router, tags=["External — Instructors"])

# Private sessions (BioAlignPro integration)
router.include_router(private_sessions.router, tags=["External — Private Sessions"])

# Courses, workshops, teacher trainings, retreats (MyYogi Academy integration)
router.include_router(courses.router, tags=["External — Courses"])

# Public upcoming events (workshops/teacher_trainings/retreats) — used
# by studio marketing sites for the public /events listing.
router.include_router(events.router, tags=["External — Events"])

# Guest-instructor roster lookup. Used by your-domain.com/guestworkshops
# so a registered guest instructor can pull up the roster for their
# upcoming workshop on the day of teaching. Read-only.
router.include_router(guest_workshops.router, tags=["External — Guest Workshops"])

# Job applications submitted from a studio's branded careers page (api-key).
router.include_router(job_applications.router, tags=["External — Hiring"])

# New-hire onboarding packet e-sign (public token flow).
router.include_router(onboarding.router, tags=["External — Onboarding"])

# Payments & POS
router.include_router(payments.router, tags=["External — Payments & POS"])

# Mailchimp (email marketing sync)
router.include_router(mailchimp.router, tags=["External — Mailchimp"])

# White-label portal: tenant-scoped member login (Phase 1 of the
# auraflow-portal rollout — see KinovaAI/auraflow-portal/docs/PLAN.md).
router.include_router(portal_login.router, tags=["External — Portal Login"])

# White-label portal: branding + CORS-allowlist admin (api-key authed).
router.include_router(branding_admin.router, tags=["External — Branding Admin"])

# White-label portal: Stripe Connect readiness (api-key authed).
router.include_router(connect_status.router, tags=["External — Connect Status"])

# White-label portal: kiosk PIN-based session + admin PIN management.
router.include_router(kiosk_session.router, tags=["External — Kiosk"])

# White-label portal: passwordless magic-link auth (senior-friendly).
router.include_router(magic_link.router, tags=["External — Magic Link"])

router.include_router(contracts_external_router, tags=["External — Workshop Contracts"])
