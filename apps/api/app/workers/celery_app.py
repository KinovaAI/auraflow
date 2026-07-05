"""AuraFlow — Celery Application

Celery worker + beat configuration for background tasks:
- Class reminders (2h before class)
- Membership expiration reminders (7-day + 1-day)
- Membership auto-expire (daily — mark expired memberships)
- Welcome sequence drip emails (Day 3 + Day 7)
- Post-class follow-up emails (~24h after attendance)
- Auto no-show marking (every 30 min — mark unattended bookings)
- No-show follow-up emails (next morning)
- Scheduled campaign sender (every 5 min)
- Trial expiration warnings + status updates
- Daily churn scan
- Email/SMS delivery
- YouTube video sync (hourly)
- Birthday emails (daily)
- Backup verification (after each backup)
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

try:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from app.core.config import settings as _settings
    if _settings.SENTRY_DSN_API:
        sentry_sdk.init(
            dsn=_settings.SENTRY_DSN_API,
            integrations=[CeleryIntegration()],
            environment=_settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=0.05,
        )
except ImportError:
    pass

app = Celery("auraflow")

# Register the dead-letter queue signal handler so exhausted-retry tasks
# get persisted to af_global.dead_letter_tasks instead of silently dying.
from app.workers import dead_letter  # noqa: F401 — imported for side effect

app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks.birthday_emails",
        "app.workers.tasks.canary",
        "app.workers.tasks.churn_scan",
        "app.workers.tasks.dynamic_pricing",
        "app.workers.tasks.emr_sync",
        "app.workers.tasks.engagement_autopilot",
        "app.workers.tasks.google_ads_optimization",
        "app.workers.tasks.mailchimp_sync",
        "app.workers.tasks.membership_expiration",
        "app.workers.tasks.membership_trial_nudge",
        "app.workers.tasks.meta_ads_optimization",
        "app.workers.tasks.no_show",
        "app.workers.tasks.phi_consistency",
        "app.workers.tasks.office_manager",
        "app.workers.tasks.payment_escalation",
        "app.workers.tasks.platform_backup",

        "app.workers.tasks.platform_security",

        "app.workers.tasks.post_class",
        "app.workers.tasks.reminders",
        "app.workers.tasks.zoom_auto_create",
        "app.workers.tasks.zoom_links",



        "app.workers.tasks.recurring_membership_renewals",
        "app.workers.tasks.scheduled_campaigns",
        "app.workers.tasks.scheduled_course_price",
        "app.workers.tasks.scheduled_sms_campaigns",
        "app.workers.tasks.daily_class_reminder",
        "app.workers.tasks.token_cleanup",
        "app.workers.tasks.studio_email_monitor",
        "app.workers.tasks.studio_social",
        "app.workers.tasks.trial_expiration",
        "app.workers.tasks.nightly_cleanup",
        "app.workers.tasks.orphan_scan",
        "app.workers.tasks.subscription_reconcile",
        "app.workers.tasks.webhook_retries",
        "app.workers.tasks.welcome_sequence",
        "app.workers.tasks.youtube_sync",
        'app.workers.tasks.contract_reminders',
        'app.workers.tasks.pos_checkout_expiry'],
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 min hard limit
    task_soft_time_limit=540,  # 9 min soft limit (raises SoftTimeLimitExceeded)
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (prevent memory leaks)
    worker_prefetch_multiplier=1,  # Fair scheduling
    task_default_queue="default",
    task_routes={
        "app.workers.tasks.reminders.*": {"queue": "email"},
        "app.workers.tasks.membership_expiration.*": {"queue": "email"},
        "app.workers.tasks.membership_trial_nudge.*": {"queue": "email"},
        "app.workers.tasks.welcome_sequence.*": {"queue": "email"},
        "app.workers.tasks.post_class.*": {"queue": "email"},
        "app.workers.tasks.no_show.*": {"queue": "email"},
        "app.workers.tasks.scheduled_campaigns.*": {"queue": "email"},
        "app.workers.tasks.email.*": {"queue": "email"},
        "app.workers.tasks.sms.*": {"queue": "sms"},
        "app.workers.tasks.scheduled_sms_campaigns.*": {"queue": "sms"},
        "app.workers.tasks.trial_expiration.*": {"queue": "email"},
        "app.workers.tasks.payment_escalation.*": {"queue": "email"},
        "app.workers.tasks.google_ads_optimization.*": {"queue": "default"},
        "app.workers.tasks.meta_ads_optimization.*": {"queue": "default"},
        "app.workers.tasks.emr_sync.*": {"queue": "default"},
        "app.workers.tasks.office_manager.*": {"queue": "sms"},
        "app.workers.tasks.engagement_autopilot.*": {"queue": "email"},
        "app.workers.tasks.studio_email_monitor.*": {"queue": "email"},
        "app.workers.tasks.studio_social.*": {"queue": "default"},
        "app.workers.tasks.youtube_sync.*": {"queue": "default"},
        "app.workers.tasks.birthday_emails.*": {"queue": "email"},
    },
    beat_schedule={
        'contract-reminders': {
            'task': 'contracts.send_reminders',
            'schedule': crontab(hour=15, minute=37),  # 8:37 AM Pacific daily
        },
        "send-class-reminders-every-15-min": {
            "task": "app.workers.tasks.reminders.send_class_reminders",
            "schedule": crontab(minute="*/15"),
        },
        "send-zoom-links-every-15-min": {
            "task": "app.workers.tasks.zoom_links.send_zoom_links",
            "schedule": crontab(minute="*/15"),
        },
        "auto-create-zoom-meetings-daily-6am": {
            "task": "app.workers.tasks.zoom_auto_create.auto_create_zoom_meetings",
            "schedule": crontab(hour=6, minute=30),
        },
        "daily-class-reminders-7am-pacific": {
            "task": "app.workers.tasks.daily_class_reminder.send_daily_class_reminders",
            "schedule": crontab(hour=14, minute=0),  # 7 AM Pacific = 2 PM UTC
        },
        "nightly-orphan-scan-5am-pacific": {
            "task": "app.workers.tasks.orphan_scan.nightly_orphan_scan",
            "schedule": crontab(hour=12, minute=0),  # 5 AM Pacific = 12 UTC
        },
        "nightly-data-cleanup-4am-pacific": {
            "task": "app.workers.tasks.nightly_cleanup.nightly_data_cleanup",
            "schedule": crontab(hour=11, minute=0),  # 4 AM Pacific = 11 AM UTC
        },
        "synthetic-canary-every-5min": {
            "task": "app.workers.tasks.canary.run_synthetic_canary",
            "schedule": crontab(minute="*/5"),
        },
        "process-webhook-retries-every-2min": {
            "task": "app.workers.tasks.webhook_retries.process_webhook_retries",
            "schedule": crontab(minute="*/2"),
        },
        "subscription-reconcile-hourly": {
            "task": "app.workers.tasks.subscription_reconcile.reconcile_subscriptions",
            "schedule": crontab(minute=37),  # hourly :37 — off-peak slot
        },
        "membership-trial-nudge-daily-730utc": {
            # Heads-up to free-trial members 1–2 days before the renewal sweep
            # makes their first charge. Runs before renewals (8:15 UTC).
            "task": "app.workers.tasks.membership_trial_nudge.send_trial_nudges",
            "schedule": crontab(hour=7, minute=30),
        },
        "recurring-membership-renewals-daily-1am-pacific": {
            "task": "app.workers.tasks.recurring_membership_renewals.run_renewals",
            "schedule": crontab(hour=8, minute=15),  # 1:15 AM Pacific = 8:15 AM UTC
        },
        "square-token-refresh-daily-2am-pacific": {
            "task": "app.workers.tasks.square_token_refresh.refresh_tokens",
            "schedule": crontab(hour=9, minute=0),  # 2 AM Pacific = 9 AM UTC
        },
        "pos-checkout-expiry-sweep-every-5min": {
            "task": "pos.expire_stale_checkouts",
            "schedule": crontab(minute="*/5"),  # every 5 minutes
        },
        "hipaa-phi-consistency-scan-daily-3am-pacific": {
            "task": "app.workers.tasks.phi_consistency.nightly_phi_scan",
            "schedule": crontab(hour=10, minute=0),  # 3 AM Pacific = 10 AM UTC
        },
        "token-cleanup-daily-5am": {
            "task": "app.workers.tasks.token_cleanup.cleanup_tokens",
            "schedule": crontab(hour=5, minute=0),
        },
        "daily-churn-scan-6am-utc": {
            "task": "app.workers.tasks.churn_scan.daily_churn_scan",
            "schedule": crontab(hour=6, minute=0),
        },
        "trial-expiration-daily-7am": {
            "task": "app.workers.tasks.trial_expiration.check_trial_expirations",
            "schedule": crontab(hour=7, minute=0),
        },
        "membership-expiration-reminders-daily-8am": {
            "task": "app.workers.tasks.membership_expiration.check_membership_expirations",
            "schedule": crontab(hour=8, minute=0),
        },
        "no-show-followup-daily-9am": {
            "task": "app.workers.tasks.no_show.send_no_show_followups",
            "schedule": crontab(hour=9, minute=0),
        },
        "welcome-sequence-daily-10am": {
            "task": "app.workers.tasks.welcome_sequence.run_welcome_sequence",
            "schedule": crontab(hour=10, minute=0),
        },
        "post-class-followup-hourly": {
            "task": "app.workers.tasks.post_class.send_post_class_followups",
            "schedule": crontab(minute=30),
        },
        "scheduled-campaigns-every-5min": {
            "task": "app.workers.tasks.scheduled_campaigns.process_scheduled_campaigns",
            "schedule": crontab(minute="*/5"),
        },
        "scheduled-sms-campaigns-every-5min": {
            "task": "app.workers.tasks.scheduled_sms_campaigns.process_scheduled_sms_campaigns",
            "schedule": crontab(minute="*/5"),
        },
        # ── Google Ads ──────────────────────────────────────────────────
        "google-ads-metrics-sync-hourly": {
            "task": "app.workers.tasks.google_ads_optimization.sync_google_ads_metrics",
            "schedule": crontab(minute=15),
        },
        "google-ads-ai-optimization-4x-daily": {
            "task": "app.workers.tasks.google_ads_optimization.run_ai_optimization",
            "schedule": crontab(hour="2,8,14,20", minute=30),
        },
        "google-ads-conversion-upload-daily": {
            "task": "app.workers.tasks.google_ads_optimization.upload_conversions",
            "schedule": crontab(hour=3, minute=0),
        },
        "google-ads-budget-check-4h": {
            "task": "app.workers.tasks.google_ads_optimization.monthly_budget_check",
            "schedule": crontab(hour="*/4", minute=45),
        },
        # ── Meta/Facebook Ads (offset from Google Ads schedules) ──────
        "meta-ads-metrics-sync-hourly": {
            "task": "app.workers.tasks.meta_ads_optimization.sync_meta_ads_metrics",
            "schedule": crontab(minute=45),
        },
        "meta-ads-ai-optimization-4x-daily": {
            "task": "app.workers.tasks.meta_ads_optimization.run_meta_ai_optimization",
            "schedule": crontab(hour="3,9,15,21", minute=30),
        },
        "meta-ads-conversion-upload-daily": {
            "task": "app.workers.tasks.meta_ads_optimization.upload_meta_conversions",
            "schedule": crontab(hour=4, minute=0),
        },
        "meta-ads-budget-check-4h": {
            "task": "app.workers.tasks.meta_ads_optimization.meta_monthly_budget_check",
            "schedule": crontab(hour="*/4", minute=15),
        },
        # ── Platform Infrastructure ─────────────────────────────────────
        # Backups: single source of truth is `platform_backup_schedule`
        # (cron strings + retention_days). The check task fires every
        # 5 min and triggers a backup only when the schedule says it's
        # due. The hardcoded daily DB + files beat schedules were
        # removed 2026-06-02 — they were duplicating the cron table
        # path AND firing on every container restart, which exhausted
        # the Backblaze cap with 40+ attempts/day of a 94 MB tarball
        # (mostly because the tar exclude missed /app/venv).
        "platform-check-backup-schedules-5min": {
            "task": "platform.check_backup_schedules",
            "schedule": crontab(minute="*/5"),
        },
        "platform-cleanup-expired-backups-daily-3am": {
            "task": "platform.cleanup_expired_backups",
            "schedule": crontab(hour=3, minute=0),
        },
        "platform-security-scan-5min": {
            "task": "platform.security_scan",
            "schedule": crontab(minute="*/5"),
        },
        "platform-aggregate-metrics-5min": {
            "task": "platform.aggregate_request_metrics",
            "schedule": crontab(minute="*/5"),
        },
        "platform-security-alerts-15min": {
            "task": "platform.send_security_alerts",
            "schedule": crontab(minute="*/15"),
        },
        "platform-email-check-2min": {
            "task": "platform.process_pending_emails",
            "schedule": crontab(minute="*/2"),
        },
        "platform-publish-scheduled-posts-5min": {
            "task": "platform.publish_scheduled_posts",
            "schedule": crontab(minute="*/5"),
        },
        "platform-sync-engagement-hourly": {
            "task": "platform.sync_post_engagement",
            "schedule": crontab(minute=20),
        },
        # ── Payment Failure Escalation ─────────────────────────────────
        "payment-escalation-daily-9am": {
            "task": "app.workers.tasks.payment_escalation.run_payment_escalation",
            "schedule": crontab(hour=9, minute=30),
        },
        # ── Dynamic Pricing ────────────────────────────────────────────
        "nightly-dynamic-pricing-11pm": {
            "task": "app.workers.tasks.dynamic_pricing.nightly_dynamic_pricing",
            "schedule": crontab(hour=23, minute=0),
        },
        # ── EMR Sync ─────────────────────────────────────────────────────
        "emr-retry-failed-syncs-15min": {
            "task": "app.workers.tasks.emr_sync.emr_periodic_retry",
            "schedule": crontab(minute="*/15"),
        },
        # ── AI Office Manager ──────────────────────────────────────────
        "office-manager-inventory-check-daily-8am": {
            "task": "app.workers.tasks.office_manager.daily_inventory_check",
            "schedule": crontab(hour=8, minute=30),
        },
        # ── AI Engagement Autopilot ──────────────────────────────────
        "engagement-autopilot-daily-scan-10am": {
            "task": "app.workers.tasks.engagement_autopilot.daily_engagement_scan",
            "schedule": crontab(hour=10, minute=30),
        },
        "engagement-autopilot-followups-2pm": {
            "task": "app.workers.tasks.engagement_autopilot.process_engagement_followups",
            "schedule": crontab(hour=14, minute=0),
        },
        "engagement-autopilot-outcomes-6pm": {
            "task": "app.workers.tasks.engagement_autopilot.check_engagement_outcomes",
            "schedule": crontab(hour=18, minute=0),
        },
        # ── Sales CRM ────────────────────────────────────────────────
        # ── Studio Email Inbox (per-tenant AI inbox) ──────────────────
        "studio-email-poll-2min": {
            "task": "studio.poll_studio_inboxes",
            "schedule": crontab(minute="*/2"),
        },
        # ── Studio Social Media (per-tenant) ────────────────────────────
        "studio-social-daily-ai-post-9am": {
            "task": "studio.daily_ai_social_post",
            "schedule": crontab(hour=9, minute=0),
        },
        "studio-social-sync-messages-5min": {
            "task": "studio.sync_social_messages",
            "schedule": crontab(minute="*/5"),
        },
        "studio-social-publish-scheduled-5min": {
            "task": "studio.publish_scheduled_social_posts",
            "schedule": crontab(minute="*/5"),
        },
        # ── YouTube Video Sync ────────────────────────────────────────
        "video-youtube-sync-hourly": {
            "task": "app.workers.tasks.youtube_sync.sync_youtube_videos_all_orgs",
            "schedule": crontab(minute=5),
        },
        # ── Auto No-Show Marking ─────────────────────────────────────
        "auto-mark-no-shows-every-30min": {
            "task": "app.workers.tasks.no_show.mark_no_shows",
            "schedule": crontab(minute="*/30"),
        },
        # ── Membership Auto-Expire ───────────────────────────────────
        "membership-auto-expire-daily-1am": {
            "task": "app.workers.tasks.membership_expiration.auto_expire_memberships",
            "schedule": crontab(hour=1, minute=0),
        },
        # ── Birthday Emails ──────────────────────────────────────────
        "birthday-emails-daily-730am": {
            "task": "app.workers.tasks.birthday_emails.send_birthday_emails",
            "schedule": crontab(hour=7, minute=30),
        },
    },
)

app.autodiscover_tasks([
    "app.workers.tasks",
], force=True)
