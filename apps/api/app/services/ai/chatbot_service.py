"""AuraFlow — AI Chatbot Service

Claude-powered chat assistant that helps users navigate the platform,
answer questions about features, look up data, and perform actions.
Uses SSE streaming with multi-turn tool execution.
"""
import json
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import logger
from app.db.session import get_tenant_db
from app.services.ai.token_tracking_service import track_ai_usage
from app.services.members.phi_helpers import decrypt_phone


# ── Knowledge Base ────────────────────────────────────────────────────────────

HELP_DOCS = [
    # ── Operations ────────────────────────────────────────────────────
    {
        "topic": "Dashboard",
        "keywords": ["dashboard", "home", "overview", "kpi", "metrics", "summary"],
        "content": (
            "The Dashboard (/dashboard) is your command center showing key performance "
            "indicators: today's revenue, active memberships, classes scheduled today, "
            "check-ins so far, and member retention rate. Each KPI tile is clickable and "
            "links to the detailed report. Below the KPIs: a calendar widget for today's "
            "schedule, a recent activity feed (check-ins, bookings, payments, sign-ups), "
            "and an AI-powered at-risk members panel. Located under Operations in the sidebar."
        ),
    },
    {
        "topic": "Voice Check-In",
        "keywords": ["voice", "speech", "check in", "checkin", "voice command", "transcription", "kiosk"],
        "content": (
            "Voice Check-In (/check-in) uses OpenAI Whisper speech-to-text for hands-free "
            "member check-in. Click the microphone button or press-hold spacebar and say the "
            "member's name. AuraFlow transcribes, matches to a member profile, and records "
            "attendance (uses 'attended' status). Supports manual check-in and walk-ins too. "
            "Kiosk mode must use the studio-specific URL: /{slug}/dashboard/check-in/kiosk. "
            "The generic /dashboard/check-in/kiosk is disabled. Located under Operations in the sidebar."
        ),
    },
    {
        "topic": "Schedule Management",
        "keywords": ["schedule", "class", "session", "calendar", "timetable", "recurring", "class schedule"],
        "content": (
            "The Schedule page (/schedule) shows a weekly calendar of all group class sessions. "
            "Create one-time or recurring sessions, assign instructors, set capacity, enable "
            "waitlists, and configure auto-cancellation thresholds. Supports day/week/month "
            "views with drag-and-drop rescheduling. Filter by class type, instructor, or "
            "location. Located under Operations in the sidebar."
        ),
    },
    {
        "topic": "Waitlist Management",
        "keywords": ["waitlist", "priority", "triage", "queue", "waiting list", "auto-promote"],
        "content": (
            "Waitlists activate automatically when a class is full. Members are placed in "
            "order. When a spot opens, the first waitlisted member is auto-promoted and "
            "notified via email/SMS. You control the auto-promotion time window. AI waitlist "
            "triage can prioritize beyond FIFO using membership tier, attendance loyalty, "
            "churn risk, and time since last visit."
        ),
    },
    # ── Classes & Content ─────────────────────────────────────────────
    {
        "topic": "Private Sessions",
        "keywords": ["private session", "one-on-one", "personal training", "appointment", "private lesson", "package"],
        "content": (
            "Private Sessions (/private-sessions) handle 1-on-1 or small group appointments. "
            "Create service types with name, duration, price, and eligible instructors. "
            "Package deals: services can have package_sessions + package_price_cents for bulk "
            "pricing. Book as Package checkbox creates credits on payment. Payment status "
            "(paid/unpaid) tracked separately from booking status. Payroll only counts paid "
            "sessions. Instructors set availability windows. Members or staff book within those "
            "windows. Session notes track client progress. Located under Classes & Content in the sidebar."
        ),
    },
    {
        "topic": "Workshops & Teacher Training",
        "keywords": ["workshop", "teacher training", "course", "multi-day", "intensive", "retreat"],
        "content": (
            "Workshops (/courses) handle multi-session events: teacher trainings, weekend "
            "workshops, retreats, and intensives. Fixed enrollment with separate pricing, "
            "payment plans, early-bird discounts, progress tracking, attendance requirements, "
            "and completion certificates. Located under Classes & Content in the sidebar."
        ),
    },
    {
        "topic": "Video Library",
        "keywords": ["video", "on demand", "recorded", "replay", "video library", "mux"],
        "content": (
            "The Video Library (/video) hosts on-demand content processed through Mux for "
            "adaptive streaming. Upload MP4/MOV/WebM or link YouTube URLs. Organize with "
            "categories and tags, control access by membership type, and track view analytics. "
            "Members browse a Netflix-style interface in the portal. Located under Classes & "
            "Content in the sidebar."
        ),
    },
    # ── People ────────────────────────────────────────────────────────
    {
        "topic": "Members",
        "keywords": ["member", "members", "client", "customer", "profile", "contact", "member list"],
        "content": (
            "The Members page (/members) lists all studio members with search, filtering, "
            "and sorting. Profiles show contact info, membership status, visit history, "
            "bookings, payments, notes, waivers, and emergency contacts. Add manually, "
            "import from CSV/MindBody/MomoYoga, merge duplicates, tag members, export data. "
            "AI insights provide churn risk scores and retention recommendations. Located "
            "under People in the sidebar."
        ),
    },
    {
        "topic": "Member Insights & AI Analysis",
        "keywords": ["insights", "ai analysis", "churn", "at risk", "retention", "member behavior"],
        "content": (
            "AI continuously analyzes member behavior: attendance frequency, booking trends, "
            "cancellations, and membership status. Each member gets a churn risk score (0-100) "
            "from the 12-feature ML model. High-risk members appear on the dashboard with "
            "recommended retention actions. Periodic insight reports highlight trends like "
            "'Members attending both yoga and pilates have 35% higher retention.'"
        ),
    },
    {
        "topic": "Instructors",
        "keywords": ["instructor", "teacher", "trainer", "substitute", "sub finder", "availability"],
        "content": (
            "Instructor management (/instructors) tracks profiles, certifications, specialties, "
            "availability, assigned classes, pay rates, and performance metrics. The Sub-Finder "
            "automatically contacts available substitutes when an instructor calls out. "
            "Instructors submit time-off requests for admin approval. Located under People "
            "in the sidebar."
        ),
    },
    {
        "topic": "Staff & Permissions",
        "keywords": ["staff", "employee", "role", "permissions", "team", "organization users"],
        "content": (
            "Staff management (/staff) uses role-based access control: owner > admin > "
            "instructor > front_desk. Per-user permissions set by the owner via Staff > "
            "user > Permissions are the FINAL authority — there is no client-side studio "
            "role filtering. Key permission modules: module.email (separate from module.ai), "
            "module.payroll (separate from module.payments). Staff can be assigned to "
            "specific locations. Invite new staff via email. Located under People in the sidebar."
        ),
    },
    # ── Business ──────────────────────────────────────────────────────
    {
        "topic": "Memberships & Plans",
        "keywords": ["membership", "package", "plan", "subscription", "credits", "unlimited", "class pack", "pricing"],
        "content": (
            "Memberships (/memberships) define pricing plans: unlimited monthly, class packs, "
            "drop-in rates, intro offers, day passes, and custom plans. Each has a name, price, "
            "billing cycle, class count (for packs), auto-renew settings, and eligible class "
            "types. Tiered pricing, student/senior discounts, and family plans supported. "
            "Located under Business in the sidebar."
        ),
    },
    {
        "topic": "Payments & Billing",
        "keywords": ["payment", "billing", "invoice", "charge", "refund", "transaction", "stripe", "credit card"],
        "content": (
            "Payments (/payments) shows all transactions: membership charges, drop-in fees, "
            "retail, courses, and manual charges. Powered by Stripe with Stripe Connect for "
            "marketplace revenue splitting. Issue refunds or studio credits. Recurring billing "
            "with automatic retry for failed payments. Located under Business in the sidebar."
        ),
    },
    {
        "topic": "Point of Sale",
        "keywords": ["pos", "point of sale", "merchandise", "product", "retail", "shop", "payment link", "pending orders"],
        "content": (
            "Point of Sale (/pos) is a full POS system for selling merchandise, water, mats, "
            "and products. Features: product catalog, barcode scanning, discount codes, sales "
            "reporting, Stripe integration. Send Payment Link option for remote sales (emails "
            "Stripe checkout to member). Pending Orders tab: view unpaid orders, resend payment "
            "link, pay in person. Stripe webhook marks transactions as completed. Member "
            "purchases link to their profiles. Located under Business in the sidebar."
        ),
    },
    {
        "topic": "Inventory",
        "keywords": ["inventory", "stock", "product", "reorder", "low stock"],
        "content": (
            "Inventory (/inventory) manages product stock levels across locations. Each product "
            "has name, SKU, price, cost, and quantity. Low-stock alerts from the AI Office "
            "Manager. Stock adjustments logged with audit trail. Located under Business "
            "in the sidebar."
        ),
    },
    {
        "topic": "Gift Cards",
        "keywords": ["gift card", "gift", "voucher", "redeem", "gift certificate"],
        "content": (
            "Gift Cards (/payments/gift-cards) let you create and sell digital gift cards. "
            "Email directly to recipients with personalized messages. Recipients redeem at "
            "checkout with a gift card code. Partial redemptions and balance tracking supported. "
            "Members view balances in the portal. Located under Business > Payments."
        ),
    },
    # ── Insights ──────────────────────────────────────────────────────
    {
        "topic": "Analytics & Reporting",
        "keywords": ["analytics", "report", "reporting", "chart", "data", "statistics", "revenue report", "attendance report"],
        "content": (
            "Analytics (/analytics) provides comprehensive reporting: revenue breakdown, "
            "attendance trends, membership growth, instructor performance, class popularity, "
            "peak hours analysis, retention metrics, and cohort analysis. Filter by date, "
            "location, class type. Export to CSV. AI forecasts and insights included. "
            "Located under Insights in the sidebar."
        ),
    },
    # ── AI Features ───────────────────────────────────────────────────
    {
        "topic": "AI Chatbot (This Assistant)",
        "keywords": ["chatbot", "assistant", "help", "support", "ai chat", "ask a question"],
        "content": (
            "You are the AuraFlow AI Assistant! I can help you navigate the platform, "
            "answer questions about any feature, look up your bookings and memberships, "
            "check the class schedule, and (for staff) search member records and view "
            "key metrics. Just ask me anything about AuraFlow. I can also guide you to "
            "the right page for any task."
        ),
    },
    {
        "topic": "AI Office Manager",
        "keywords": ["ai manager", "office manager", "sub finder", "substitute", "inventory alert", "auto response"],
        "content": (
            "The AI Office Manager (/ai/office-manager) handles routine operations: "
            "Sub-Finder contacts available substitutes when instructors call out, "
            "inventory alerts notify when products run low, and scheduling conflict "
            "detection surfaces coverage gaps. Located under Insights > AI Assistant."
        ),
    },
    {
        "topic": "AI Engagement Autopilot",
        "keywords": ["engagement", "autopilot", "automated outreach", "welcome series", "win back", "milestone"],
        "content": (
            "The Engagement Autopilot automates personalized outreach: welcome series for "
            "new sign-ups, re-engagement for declining attendance, birthday greetings, "
            "milestone celebrations (10th visit, 1-year anniversary), and win-back sequences "
            "for lapsed members. AI generates personalized email/SMS content."
        ),
    },
    {
        "topic": "AI Email Inbox",
        "keywords": ["email inbox", "first responder", "incoming email", "auto reply", "email ai", "reclassify"],
        "content": (
            "The AI Email Inbox (/ai/inbox) acts as a first-responder for incoming member "
            "emails. Connect your studio email under Settings > Email Inbox. It classifies "
            "intent, looks up data, drafts responses, and sends or queues for staff review. "
            "Use the Reclassify button to manually override AI classification on any email. "
            "Complex issues are escalated. All resolutions logged."
        ),
    },
    {
        "topic": "Churn Risk Prediction",
        "keywords": ["churn", "retention", "at risk", "losing members", "risk score"],
        "content": (
            "Churn Risk (/ai/churn-risk) uses a 12-feature ML model scoring 0-100. Factors: "
            "visit frequency decline, days since last visit, membership age, cancellation "
            "patterns, booking behavior, communication engagement. High-risk members flagged "
            "with recommended actions. Retention Dashboard shows aggregate trends."
        ),
    },
    # ── Studio ────────────────────────────────────────────────────────
    {
        "topic": "Marketing & Campaigns",
        "keywords": ["marketing", "campaign", "email campaign", "sms", "promotion", "automation", "drip"],
        "content": (
            "Marketing (/marketing) for email and SMS campaigns. Audience segmentation, "
            "template builder, AI content generation, scheduling, and analytics. Automated "
            "drip campaigns: welcome series, win-back, birthday greetings. SMS via Twilio. "
            "Located under Studio in the sidebar."
        ),
    },
    {
        "topic": "Facilities & Rooms",
        "keywords": ["facility", "room", "space", "studio room", "equipment", "amenity"],
        "content": (
            "Facilities (/facilities) manages physical spaces: rooms, equipment, and amenities. "
            "Each room has name, capacity, and equipment. Room booking prevents scheduling "
            "conflicts. Located under Studio in the sidebar."
        ),
    },
    {
        "topic": "Time Clock",
        "keywords": ["time clock", "clock in", "clock out", "hours", "timesheet", "payroll"],
        "content": (
            "Time Clock (/time-clock) for staff clock-in/out with optional GPS tracking. "
            "Managers view timesheets, approve hours, edit entries. Break tracking, overtime "
            "rules, and payroll export in Gusto/QuickBooks formats. Located under Studio "
            "in the sidebar."
        ),
    },
    # ── Settings ──────────────────────────────────────────────────────
    {
        "topic": "Settings Overview",
        "keywords": ["settings", "configuration", "preferences", "setup", "customize"],
        "content": (
            "Settings (/settings) tabs: Studio (name, logo, timezone, address), Locations "
            "(multi-location management), Communications (SendGrid email, Twilio SMS), "
            "Email Inbox (AI first-responder connection), Integrations (Stripe, ClassPass, "
            "Mailchimp, EMR, API keys), Import (CSV, MindBody, MomoYoga), Billing (plan "
            "management, Stripe connect), Waivers (digital liability forms), Webhooks "
            "(event notifications), Audit Log (admin action history), Account (password, "
            "2FA, cancellation). Located under Studio in the sidebar."
        ),
    },
    {
        "topic": "Communications & Email",
        "keywords": ["sms", "text message", "twilio", "notification", "communication", "email settings", "sendgrid", "purelymail", "smtp"],
        "content": (
            "Communications settings (/settings/communications) configure outbound SMS "
            "(via Twilio with Messaging Service SID for A2P 10DLC compliance) and email. "
            "Studio SMTP (Purelymail) is the primary email sender; studio's own SendGrid "
            "is fallback. Platform email (AuraFlow) is never used for tenant emails. "
            "Email templates: booking confirmations, daily class reminders (7 AM Pacific), "
            "post-class follow-ups. All templates use studio name. Set 'from' name and reply-to."
        ),
    },
    {
        "topic": "Email Inbox Connection",
        "keywords": ["email inbox", "connect email", "incoming email", "inbox setup"],
        "content": (
            "Email Inbox (/settings/email-inbox) connects your studio email to enable the "
            "AI Email Inbox first-responder feature. Once connected, AuraFlow receives "
            "incoming member emails for AI classification, drafting, and response."
        ),
    },
    {
        "topic": "Import & Export",
        "keywords": ["import", "export", "csv", "mindbody", "momoyoga", "migration", "data transfer"],
        "content": (
            "Import (/settings/import or /dashboard/import) supports CSV imports for members, "
            "class types, and schedules. Dedicated importers for MindBody and MomoYoga. "
            "Export options on individual report pages. All imports validated with preview."
        ),
    },
    {
        "topic": "Integrations",
        "keywords": ["integration", "api", "connect", "third party", "classpass", "mailchimp", "emr", "fhir"],
        "content": (
            "Integrations (/integrations) manages: Stripe (payments), ClassPass (class "
            "marketplace), Mailchimp (email marketing sync), EMR/FHIR R4/HL7v2 (medical "
            "records), API keys (REST API access), and webhook endpoints. Each integration "
            "has its own setup wizard."
        ),
    },
    {
        "topic": "Billing & Plans",
        "keywords": ["billing", "subscription", "plan", "upgrade", "cancel account", "pricing", "studio plan", "enterprise"],
        "content": (
            "Billing (/settings/billing) manages your AuraFlow platform subscription. "
            "AuraFlow offers two plans: Studio ($99/mo, up to 10 locations, all features, "
            "full white-label, RESTful API) and Enterprise (custom pricing for franchise "
            "chains). Stripe Connect platform fee is 1.25%. View your current plan, next "
            "billing date, update payment method, review invoices. Also where you connect "
            "Stripe for member payments."
        ),
    },
    {
        "topic": "Waivers",
        "keywords": ["waiver", "liability", "form", "signature", "digital waiver"],
        "content": (
            "Waivers (/settings/waivers) for creating digital liability forms. Members sign "
            "electronically through the portal. Track completion status. Optionally require "
            "before class booking."
        ),
    },
    {
        "topic": "Webhooks",
        "keywords": ["webhook", "event", "notification", "zapier", "make", "automation"],
        "content": (
            "Webhooks (/settings/webhooks) send JSON payloads to your URL when events occur: "
            "member created, payment processed, class booked, check-in recorded, etc. "
            "Automatic retry on failure. Testing tool and delivery logs included."
        ),
    },
    {
        "topic": "Audit Log",
        "keywords": ["audit", "log", "history", "security", "admin actions", "activity log"],
        "content": (
            "Audit Log (/settings/audit-log) records all admin actions, logins, and security "
            "events with timestamps and user attribution. Filter by date, action type, or "
            "user. Essential for security reviews and compliance."
        ),
    },
    # ── Member Portal ─────────────────────────────────────────────────
    {
        "topic": "Member Portal",
        "keywords": ["portal", "self-service", "my account", "member portal", "member login"],
        "content": (
            "The Member Portal (/portal) is the self-service area. Members can: browse and "
            "book classes, manage profile and billing, view membership and remaining credits, "
            "watch on-demand videos, purchase and redeem gift cards, enroll in workshops, "
            "sign waivers, and manage communication preferences."
        ),
    },
    # ── Navigation ────────────────────────────────────────────────────
    {
        "topic": "Navigation Guide",
        "keywords": ["navigate", "go to", "find page", "where is", "how to get to", "sidebar"],
        "content": (
            "Sidebar navigation groups: OPERATIONS (Dashboard, Check-In, Schedule), "
            "CLASSES & CONTENT (Private Sessions, Workshops, Video), PEOPLE (Members, "
            "Instructors, Staff), BUSINESS (Memberships, Payments, Point of Sale, Inventory), "
            "INSIGHTS (Analytics, AI Assistant), STUDIO (Marketing, Facilities, Time Clock, "
            "Settings). Settings tabs: Studio, Locations, Communications, Email Inbox, "
            "Integrations, Import, Billing, Waivers, Webhooks, Audit Log, Account."
        ),
    },
]


# ── Navigation Map ────────────────────────────────────────────────────────────

NAVIGATION_MAP = {
    "dashboard": {"path": "/dashboard", "description": "Main dashboard with KPIs and overview"},
    "check_in": {"path": "/dashboard/check-in", "description": "Voice and manual member check-in"},
    "schedule": {"path": "/dashboard/schedule", "description": "Weekly class schedule calendar"},
    "private_sessions": {"path": "/dashboard/private-sessions", "description": "One-on-one private session bookings"},
    "courses": {"path": "/dashboard/courses", "description": "Workshops, teacher trainings, and retreats"},
    "video": {"path": "/dashboard/video", "description": "On-demand video library"},
    "members": {"path": "/dashboard/members", "description": "Member directory and management"},
    "instructors": {"path": "/dashboard/instructors", "description": "Instructor profiles and availability"},
    "staff": {"path": "/dashboard/staff", "description": "Staff roles and permissions"},
    "memberships": {"path": "/dashboard/memberships", "description": "Membership plans and packages"},
    "payments": {"path": "/dashboard/payments", "description": "Payment transactions and billing"},
    "gift_cards": {"path": "/dashboard/payments/gift-cards", "description": "Gift card creation and management"},
    "pos": {"path": "/dashboard/pos", "description": "Point of sale for retail transactions"},
    "inventory": {"path": "/dashboard/inventory", "description": "Product inventory and stock management"},
    "analytics": {"path": "/dashboard/analytics", "description": "Reports, charts, and data analysis"},
    "ai": {"path": "/dashboard/ai", "description": "AI features: chatbot, office manager, engagement, inbox"},
    "ai_office_manager": {"path": "/dashboard/ai/office-manager", "description": "AI sub-finder, inventory alerts, scheduling"},
    "ai_inbox": {"path": "/dashboard/email", "description": "AI email inbox first-responder"},
    "email": {"path": "/dashboard/email", "description": "Studio email inbox with AI first-responder"},
    "churn": {"path": "/dashboard/ai/churn-risk", "description": "Member churn risk and retention dashboard"},
    "marketing": {"path": "/dashboard/marketing", "description": "Email and SMS campaign management"},
    "facilities": {"path": "/dashboard/facilities", "description": "Room and equipment management"},
    "time_clock": {"path": "/dashboard/time-clock", "description": "Staff time tracking and timesheets"},
    "settings": {"path": "/dashboard/settings", "description": "Studio settings and configuration"},
    "settings_studio": {"path": "/dashboard/settings/studio", "description": "Studio profile, logo, timezone"},
    "settings_locations": {"path": "/dashboard/settings/locations", "description": "Multi-location management"},
    "settings_communications": {"path": "/dashboard/settings/communications", "description": "Email and SMS configuration"},
    "settings_email_inbox": {"path": "/dashboard/settings/email-inbox", "description": "Connect studio email for AI inbox"},
    "integrations": {"path": "/dashboard/settings/integrations", "description": "Third-party integrations (Stripe, ClassPass, EMR, API)"},
    "import": {"path": "/dashboard/settings/import", "description": "Import data from CSV, MindBody, MomoYoga"},
    "settings_billing": {"path": "/dashboard/settings/billing", "description": "Platform subscription and Stripe connect"},
    "settings_waivers": {"path": "/dashboard/settings/waivers", "description": "Digital waiver and liability forms"},
    "settings_webhooks": {"path": "/dashboard/settings/webhooks", "description": "Webhook endpoint configuration"},
    "settings_audit_log": {"path": "/dashboard/settings/audit-log", "description": "Admin action and security audit log"},
    "settings_account": {"path": "/dashboard/settings/account", "description": "Account management, password, 2FA"},
    "portal": {"path": "/portal", "description": "Member self-service portal"},
    "portal_gift_cards": {"path": "/portal/gift-cards", "description": "Member gift card balances and redemption"},
}


# ── Tool Definitions ──────────────────────────────────────────────────────────

# Available to all authenticated users
CHATBOT_TOOLS_BASE = [
    {
        "name": "search_help_docs",
        "description": (
            "Search the AuraFlow knowledge base for information about platform features, "
            "how-tos, and capabilities. Use keyword-based queries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for (e.g., 'membership pricing' or 'import data')",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_my_bookings",
        "description": "Get upcoming class bookings for the current user.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_my_memberships",
        "description": "Get active memberships and remaining credits for the current user.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_schedule",
        "description": "Get upcoming class schedule. Optionally filter by class type name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "class_type": {
                    "type": "string",
                    "description": "Filter by class type name (optional, e.g., 'yoga' or 'pilates')",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days ahead to show (default 7, max 30)",
                },
            },
        },
    },
    {
        "name": "navigate_to_page",
        "description": (
            "Navigate the user to a specific page in the platform. "
            "Use this when the user wants to go somewhere or needs to perform an action on a specific page."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_key": {
                    "type": "string",
                    "description": (
                        "The page identifier. Valid values: dashboard, check_in, schedule, "
                        "private_sessions, courses, video, members, instructors, staff, "
                        "memberships, payments, gift_cards, pos, inventory, analytics, ai, "
                        "ai_office_manager, ai_inbox, churn, marketing, facilities, "
                        "time_clock, settings, settings_studio, settings_locations, "
                        "settings_communications, settings_email_inbox, integrations, "
                        "import, settings_billing, settings_waivers, settings_webhooks, "
                        "settings_audit_log, settings_account, portal, portal_gift_cards"
                    ),
                },
            },
            "required": ["page_key"],
        },
    },
]

# Additional tools for staff/admin/owner roles
CHATBOT_TOOLS_STAFF = [
    {
        "name": "lookup_member",
        "description": "Search for members by name, email, or phone number. Staff-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name, email, or phone number to search for",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_member_details",
        "description": (
            "Get detailed information about a specific member including profile, "
            "membership status, recent bookings, and visit count. Staff-only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "member_id": {
                    "type": "string",
                    "description": "The member's UUID",
                },
            },
            "required": ["member_id"],
        },
    },
    {
        "name": "get_dashboard_stats",
        "description": (
            "Get quick KPI summary: active members, revenue this month, "
            "classes today, and attendance rate. Staff/admin only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_at_risk_members",
        "description": "Get members flagged with high churn risk. Staff/admin only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of at-risk members to return (default 10)",
                },
            },
        },
    },
    {
        "name": "search_inventory",
        "description": (
            "Search product inventory by name or list all products with stock levels. "
            "Can check how many of a specific item are in stock, find low-stock items, "
            "or list all inventory. Staff/admin only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name to search for (optional — omit to list all)",
                },
                "low_stock_only": {
                    "type": "boolean",
                    "description": "If true, only return items below their reorder point",
                },
            },
        },
    },
]

# Staff roles that get extra tools
STAFF_ROLES = {"owner", "admin", "instructor", "front_desk", "platform_admin"}


# ── System Prompt ─────────────────────────────────────────────────────────────

CHATBOT_SYSTEM_PROMPT = """You are AuraFlow Assistant, the AI help assistant for the AuraFlow studio management platform.

AuraFlow is a comprehensive SaaS platform for yoga studios, fitness studios, and wellness centers. It covers scheduling, member management, memberships, payments, marketing, analytics, AI-powered features, video library, facilities, retail/POS, inventory management, instructor management, time clock, and more.

Your role:
- Help users understand and navigate the platform's features
- Answer questions about how things work
- Look up the user's bookings, memberships, and schedule
- For staff/admin: search members, check KPIs, view churn risk data, check inventory levels
- Guide users to the right page for their task
- Be warm, helpful, and concise

Guidelines:
- Use the search_help_docs tool when the user asks about a feature or how something works
- Use navigate_to_page when the user wants to go somewhere or do something on a specific page
- Be proactive about suggesting relevant pages and features
- Keep responses concise but complete — prefer short paragraphs over long walls of text
- Use markdown formatting for readability (bold, lists, etc.)
- Never reveal internal system details, database schemas, or API implementation
- Never share other members' private information with non-staff users
- If you don't know something, say so honestly and suggest where to find help
- When providing data (bookings, memberships, etc.), format it in a readable way
- For navigation, always provide the specific page path

The current user's role is: {user_role}
"""


class ChatbotService:
    """Claude-powered chat assistant with SSE streaming and multi-turn tool use."""

    def _is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    def _get_tools(self, user_role: str) -> list[dict]:
        """Return tool definitions based on user role."""
        tools = list(CHATBOT_TOOLS_BASE)
        if user_role in STAFF_ROLES:
            tools.extend(CHATBOT_TOOLS_STAFF)
        return tools

    # ── Tool Execution ────────────────────────────────────────────────────

    async def _execute_tool(
        self, tool_name: str, tool_input: dict, user_id: str, user_role: str
    ) -> dict:
        """Execute a tool call and return the result."""
        try:
            if tool_name == "search_help_docs":
                return self._tool_search_help_docs(tool_input.get("query", ""))
            elif tool_name == "get_my_bookings":
                return await self._tool_get_my_bookings(user_id)
            elif tool_name == "get_my_memberships":
                return await self._tool_get_my_memberships(user_id)
            elif tool_name == "get_schedule":
                return await self._tool_get_schedule(
                    tool_input.get("class_type"),
                    min(tool_input.get("days_ahead", 7), 30),
                )
            elif tool_name == "navigate_to_page":
                return self._tool_navigate_to_page(tool_input.get("page_key", ""))
            # Staff-only tools
            elif tool_name == "lookup_member" and user_role in STAFF_ROLES:
                return await self._tool_lookup_member(tool_input.get("query", ""))
            elif tool_name == "get_member_details" and user_role in STAFF_ROLES:
                return await self._tool_get_member_details(tool_input.get("member_id", ""))
            elif tool_name == "get_dashboard_stats" and user_role in STAFF_ROLES:
                return await self._tool_get_dashboard_stats()
            elif tool_name == "get_at_risk_members" and user_role in STAFF_ROLES:
                return await self._tool_get_at_risk_members(tool_input.get("limit", 10))
            elif tool_name == "search_inventory" and user_role in STAFF_ROLES:
                return await self._tool_search_inventory(
                    tool_input.get("query"), tool_input.get("low_stock_only", False)
                )
            else:
                return {"error": f"Unknown or unauthorized tool: {tool_name}"}
        except Exception as e:
            logger.error("Chatbot tool execution failed", tool=tool_name, error=str(e))
            return {"error": f"Tool failed: {str(e)}"}

    def _tool_search_help_docs(self, query: str) -> dict:
        """Search the built-in knowledge base."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for doc in HELP_DOCS:
            score = 0
            # Keyword matches
            for kw in doc["keywords"]:
                kw_lower = kw.lower()
                if kw_lower in query_lower:
                    score += 3
                for w in query_words:
                    if w in kw_lower:
                        score += 1
            # Topic name match
            if doc["topic"].lower() in query_lower:
                score += 5
            # Content relevance
            content_lower = doc["content"].lower()
            for w in query_words:
                if len(w) > 2 and w in content_lower:
                    score += 0.5
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [
            {"topic": s[1]["topic"], "content": s[1]["content"]}
            for s in scored[:5]
        ]
        if not results:
            return {"results": [], "message": "No matching help docs found. Try different keywords."}
        return {"results": results}

    async def _tool_get_my_bookings(self, user_id: str) -> dict:
        """Get upcoming bookings for the current user."""
        async with get_tenant_db() as db:
            # Find the member record linked to this user
            member = await db.fetchrow(
                "SELECT id FROM members WHERE user_id = $1 LIMIT 1",
                user_id,
            )
            if not member:
                return {"bookings": [], "message": "No member profile found for your account."}

            rows = await db.fetch(
                """
                SELECT b.id, b.status, b.booked_at,
                       cs.title, cs.starts_at, cs.ends_at,
                       ct.name AS class_type_name,
                       i.display_name AS instructor_name
                FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE b.member_id = $1
                  AND b.status IN ('confirmed', 'waitlisted')
                  AND cs.starts_at > NOW()
                ORDER BY cs.starts_at ASC
                LIMIT 15
                """,
                str(member["id"]),
            )

        return {"bookings": [
            {
                "id": str(r["id"]),
                "title": r["title"] or r["class_type_name"] or "Class",
                "class_type": r["class_type_name"],
                "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
                "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None,
                "instructor": r["instructor_name"],
                "status": r["status"],
            }
            for r in rows
        ]}

    async def _tool_get_my_memberships(self, user_id: str) -> dict:
        """Get active memberships for the current user."""
        async with get_tenant_db() as db:
            member = await db.fetchrow(
                "SELECT id FROM members WHERE user_id = $1 LIMIT 1",
                user_id,
            )
            if not member:
                return {"memberships": [], "message": "No member profile found for your account."}

            rows = await db.fetch(
                """
                SELECT mm.id, mm.status, mm.starts_at, mm.ends_at,
                       mm.classes_remaining,
                       mt.name AS type_name, mt.type AS membership_type,
                       mt.price_cents, mt.class_count, mt.auto_renew
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1 AND mm.status IN ('active', 'frozen')
                ORDER BY mm.starts_at DESC
                """,
                str(member["id"]),
            )

        return {"memberships": [
            {
                "id": str(r["id"]),
                "name": r["type_name"],
                "type": r["membership_type"],
                "status": r["status"],
                "classes_remaining": r["classes_remaining"],
                "total_classes": r["class_count"],
                "price": f"${r['price_cents'] / 100:.2f}" if r["price_cents"] else None,
                "auto_renew": r["auto_renew"],
                "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
                "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None,
            }
            for r in rows
        ]}

    async def _tool_get_schedule(
        self, class_type: str | None, days_ahead: int
    ) -> dict:
        """Get upcoming class schedule."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)

        async with get_tenant_db() as db:
            conditions = ["cs.starts_at >= $1", "cs.starts_at < $2", "cs.status = 'scheduled'"]
            params: list = [now, end]
            idx = 3

            if class_type:
                conditions.append(f"LOWER(ct.name) LIKE LOWER(${idx})")
                params.append(f"%{class_type}%")
                idx += 1

            rows = await db.fetch(
                f"""
                SELECT cs.title, cs.starts_at, cs.ends_at, cs.capacity,
                       ct.name AS class_type_name,
                       i.display_name AS instructor_name,
                       (SELECT COUNT(*) FROM bookings
                        WHERE class_session_id = cs.id AND status = 'confirmed') AS booked
                FROM class_sessions cs
                LEFT JOIN class_types ct ON ct.id = cs.class_type_id
                LEFT JOIN instructors i ON i.id = cs.instructor_id
                WHERE {' AND '.join(conditions)}
                ORDER BY cs.starts_at LIMIT 25
                """,
                *params,
            )

        return {"sessions": [
            {
                "title": r["title"] or r["class_type_name"] or "Class",
                "class_type": r["class_type_name"],
                "starts_at": r["starts_at"].isoformat() if r["starts_at"] else None,
                "ends_at": r["ends_at"].isoformat() if r["ends_at"] else None,
                "instructor": r["instructor_name"],
                "spots_remaining": max(0, (r["capacity"] or 0) - (r["booked"] or 0)),
                "capacity": r["capacity"],
            }
            for r in rows
        ]}

    def _tool_navigate_to_page(self, page_key: str) -> dict:
        """Return navigation info for a page."""
        nav = NAVIGATION_MAP.get(page_key)
        if nav:
            return {"action": "navigate", "path": nav["path"], "description": nav["description"]}
        # Fuzzy match
        for key, info in NAVIGATION_MAP.items():
            if page_key.lower() in key or key in page_key.lower():
                return {"action": "navigate", "path": info["path"], "description": info["description"]}
        return {"error": f"Unknown page: {page_key}. Try: {', '.join(sorted(NAVIGATION_MAP.keys()))}"}

    async def _tool_lookup_member(self, query: str) -> dict:
        """Search members by name/email/phone. Staff only."""
        from app.services.members.member_service import MemberService
        svc = MemberService()
        members = await svc.search_members(query, limit=10)
        return {"members": [
            {
                "id": str(m["id"]),
                "name": f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
                "email": m.get("email"),
                "phone": m.get("phone"),
                "membership_status": m.get("membership_status"),
                "total_visits": m.get("total_visits", 0),
            }
            for m in members
        ]}

    async def _tool_get_member_details(self, member_id: str) -> dict:
        """Get detailed member info. Staff only."""
        async with get_tenant_db() as db:
            member = await db.fetchrow(
                """
                SELECT m.id, m.first_name, m.last_name, m.email, m.phone_enc,
                       m.total_visits, m.is_active,
                       m.created_at, m.last_visit_at, m.member_number
                FROM members m
                WHERE m.id = $1
                """,
                member_id,
            )
            if not member:
                return {"error": "Member not found"}

            # Get active memberships
            memberships = await db.fetch(
                """
                SELECT mm.status, mm.classes_remaining, mt.name AS type_name
                FROM member_memberships mm
                JOIN membership_types mt ON mt.id = mm.membership_type_id
                WHERE mm.member_id = $1 AND mm.status IN ('active', 'frozen')
                """,
                member_id,
            )

            # Get upcoming bookings count
            bookings_count = await db.fetchval(
                """
                SELECT COUNT(*) FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE b.member_id = $1 AND b.status = 'confirmed' AND cs.starts_at > NOW()
                """,
                member_id,
            )

        return {
            "id": str(member["id"]),
            "name": f"{member['first_name']} {member.get('last_name', '')}".strip(),
            "email": member["email"],
            "phone": decrypt_phone(member),
            "member_number": member.get("member_number"),
            # Derived: status of first active membership row (if any).
            "membership_status": memberships[0]["status"] if memberships else None,
            "total_visits": member["total_visits"],
            "is_active": member["is_active"],
            "last_visit": member["last_visit_at"].isoformat() if member.get("last_visit_at") else None,
            "member_since": member["created_at"].isoformat() if member.get("created_at") else None,
            "active_memberships": [
                {
                    "name": ms["type_name"],
                    "status": ms["status"],
                    "classes_remaining": ms["classes_remaining"],
                }
                for ms in memberships
            ],
            "upcoming_bookings": bookings_count or 0,
        }

    async def _tool_get_dashboard_stats(self) -> dict:
        """Quick KPI summary. Staff only."""
        async with get_tenant_db() as db:
            # Active members
            active_members = await db.fetchval(
                "SELECT COUNT(*) FROM members WHERE is_active = TRUE"
            )

            # Revenue this month
            revenue = await db.fetchval(
                """
                SELECT COALESCE(SUM(amount_cents), 0) FROM transactions
                WHERE status = 'completed'
                  AND created_at >= date_trunc('month', NOW())
                """
            )

            # Classes today
            classes_today = await db.fetchval(
                """
                SELECT COUNT(*) FROM class_sessions
                WHERE starts_at::date = CURRENT_DATE AND status = 'scheduled'
                """
            )

            # Bookings today
            bookings_today = await db.fetchval(
                """
                SELECT COUNT(*) FROM bookings b
                JOIN class_sessions cs ON cs.id = b.class_session_id
                WHERE cs.starts_at::date = CURRENT_DATE AND b.status = 'confirmed'
                """
            )

            # New members this month
            new_members = await db.fetchval(
                """
                SELECT COUNT(*) FROM members
                WHERE created_at >= date_trunc('month', NOW())
                """
            )

        return {
            "active_members": active_members or 0,
            "revenue_this_month": f"${(revenue or 0) / 100:.2f}",
            "revenue_cents": revenue or 0,
            "classes_today": classes_today or 0,
            "bookings_today": bookings_today or 0,
            "new_members_this_month": new_members or 0,
        }

    async def _tool_get_at_risk_members(self, limit: int) -> dict:
        """Get churn-risk flagged members. Staff only."""
        from app.services.ai.churn_service import ChurnService
        svc = ChurnService()
        members = await svc.get_at_risk_members()
        return {"at_risk_members": members[:limit]}

    async def _tool_search_inventory(
        self, query: str | None, low_stock_only: bool
    ) -> dict:
        """Search product inventory. Staff only."""
        async with get_tenant_db() as db:
            conditions = ["p.active = TRUE"]
            params: list = []
            idx = 1

            if query:
                conditions.append(f"LOWER(p.name) LIKE LOWER(${idx})")
                params.append(f"%{query}%")
                idx += 1

            if low_stock_only:
                conditions.append("i.quantity_on_hand <= i.reorder_point")

            rows = await db.fetch(
                f"""
                SELECT p.name, p.sku, p.category,
                       p.price_cents, p.cost_cents,
                       i.quantity_on_hand, i.reorder_point, i.reorder_quantity
                FROM products p
                LEFT JOIN inventory i ON i.product_id = p.id
                WHERE {' AND '.join(conditions)}
                ORDER BY p.name
                LIMIT 50
                """,
                *params,
            )

        products = [
            {
                "name": r["name"],
                "sku": r["sku"],
                "category": r["category"],
                "price": f"${r['price_cents'] / 100:.2f}" if r["price_cents"] else None,
                "quantity_on_hand": r["quantity_on_hand"] or 0,
                "reorder_point": r["reorder_point"],
                "low_stock": (r["quantity_on_hand"] or 0) <= (r["reorder_point"] or 0)
                    if r["reorder_point"] else False,
            }
            for r in rows
        ]

        return {
            "products": products,
            "total_found": len(products),
            "message": "No products found matching your search." if not products else None,
        }

    # ── SSE Streaming ─────────────────────────────────────────────────────

    async def stream_message(
        self,
        user_id: str,
        conversation_id: str | None,
        message: str,
        user_role: str,
    ):
        """
        Async generator that yields SSE events for a chat message.
        Handles multi-turn tool execution with up to 5 turns.
        """
        if not self._is_configured():
            yield 'data: {"type": "error", "message": "AI assistant is not configured."}\n\n'
            yield 'data: {"type": "done"}\n\n'
            return

        import anthropic

        # Create or get conversation
        if conversation_id:
            conv_exists = await self._conversation_exists(conversation_id, user_id)
            if not conv_exists:
                conversation_id = None

        if not conversation_id:
            conversation_id = await self.create_conversation(user_id, title=message[:100])

        yield f'data: {json.dumps({"type": "conversation_id", "conversation_id": conversation_id})}\n\n'

        # Save user message
        await self._save_message(conversation_id, "user", message)

        # Load conversation history (last 20 messages for context)
        history = await self._load_history(conversation_id, limit=20)

        # Build messages for Claude
        messages = self._build_claude_messages(history)

        system_prompt = CHATBOT_SYSTEM_PROMPT.format(user_role=user_role)
        tools = self._get_tools(user_role)
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        full_response_text = ""
        tool_calls_log = []
        max_turns = 5

        for turn in range(max_turns):
            try:
                collected_text = ""
                tool_use_blocks = []

                # Stream the response
                async with client.messages.stream(
                    model=settings.ANTHROPIC_MODEL_FAST,
                    max_tokens=settings.ANTHROPIC_MAX_TOKENS,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if hasattr(event.content_block, "text"):
                                pass  # Text block starting
                            elif hasattr(event.content_block, "name"):
                                # Tool use block starting
                                tool_use_blocks.append({
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input_json": "",
                                })
                        elif event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                text_chunk = event.delta.text
                                collected_text += text_chunk
                                yield f'data: {json.dumps({"type": "content_delta", "content": text_chunk})}\n\n'
                            elif hasattr(event.delta, "partial_json"):
                                if tool_use_blocks:
                                    tool_use_blocks[-1]["input_json"] += event.delta.partial_json

                    # Get the final message for stop reason
                    final_message = await stream.get_final_message()
                    await track_ai_usage(
                        service_name="chatbot_service",
                        function_name="stream_message",
                        model=settings.ANTHROPIC_MODEL_FAST,
                        input_tokens=final_message.usage.input_tokens,
                        output_tokens=final_message.usage.output_tokens,
                    )

                full_response_text += collected_text

                # Check if we need to handle tool calls
                if final_message.stop_reason == "tool_use":
                    # Process tool calls
                    tool_results = []
                    for block in final_message.content:
                        if block.type == "tool_use":
                            tool_input = block.input
                            tool_name = block.name

                            # Execute the tool
                            result = await self._execute_tool(
                                tool_name, tool_input, user_id, user_role
                            )

                            tool_calls_log.append({
                                "tool": tool_name,
                                "input": tool_input,
                                "result_preview": str(result)[:300],
                            })

                            # Yield tool use event
                            yield f'data: {json.dumps({"type": "tool_use", "tool": tool_name, "result": result})}\n\n'

                            # Check for navigation action
                            if tool_name == "navigate_to_page" and result.get("action") == "navigate":
                                yield f'data: {json.dumps({"type": "action", "action": "navigate", "path": result["path"], "description": result.get("description", "")})}\n\n'

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, default=str),
                            })

                    # Add assistant message and tool results for next turn
                    messages.append({"role": "assistant", "content": final_message.content})
                    messages.append({"role": "user", "content": tool_results})
                else:
                    # End of response — no more tool calls
                    break

            except anthropic.APIError as e:
                logger.error("Chatbot Claude API error", error=str(e))
                yield f'data: {json.dumps({"type": "error", "message": "I encountered an issue. Please try again."})}\n\n'
                break
            except Exception as e:
                logger.error("Chatbot stream error", error=str(e))
                yield f'data: {json.dumps({"type": "error", "message": "Something went wrong. Please try again."})}\n\n'
                break

        # Save assistant response to DB
        if full_response_text:
            await self._save_message(
                conversation_id,
                "assistant",
                full_response_text,
                tool_calls=tool_calls_log if tool_calls_log else None,
            )

        # Update conversation metadata
        await self._update_conversation_meta(conversation_id, message)

        yield 'data: {"type": "done"}\n\n'

    def _build_claude_messages(self, history: list[dict]) -> list[dict]:
        """Convert DB message history into Claude API message format."""
        messages = []
        for msg in history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })
        return messages

    # ── Database Operations ───────────────────────────────────────────────

    async def create_conversation(
        self, user_id: str, title: str | None = None
    ) -> str:
        """Create a new conversation and return its ID."""
        conv_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO chatbot_conversations (id, user_id, title, message_count, created_at)
                VALUES ($1, $2, $3, 0, NOW())
                """,
                conv_id, user_id, title,
            )
        return conv_id

    async def _conversation_exists(self, conversation_id: str, user_id: str) -> bool:
        """Check if a conversation exists and belongs to the user."""
        async with get_tenant_db() as db:
            row = await db.fetchval(
                "SELECT 1 FROM chatbot_conversations WHERE id = $1 AND user_id = $2",
                conversation_id, user_id,
            )
        return row is not None

    async def _save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
    ) -> str:
        """Save a message to the conversation."""
        msg_id = str(uuid.uuid4())
        async with get_tenant_db() as db:
            await db.execute(
                """
                INSERT INTO chatbot_messages (id, conversation_id, role, content, tool_calls, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
                """,
                msg_id,
                conversation_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
            )
        return msg_id

    async def _load_history(
        self, conversation_id: str, limit: int = 20
    ) -> list[dict]:
        """Load recent messages for a conversation (for context window)."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT role, content, created_at
                FROM chatbot_messages
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                """,
                conversation_id,
            )
        # Return the most recent `limit` messages
        messages = [{"role": r["role"], "content": r["content"]} for r in rows]
        if len(messages) > limit:
            messages = messages[-limit:]
        return messages

    async def _update_conversation_meta(
        self, conversation_id: str, last_user_message: str
    ) -> None:
        """Update conversation message count and last_message_at."""
        async with get_tenant_db() as db:
            # Update metadata
            await db.execute(
                """
                UPDATE chatbot_conversations
                SET message_count = (
                        SELECT COUNT(*) FROM chatbot_messages WHERE conversation_id = $1
                    ),
                    last_message_at = NOW(),
                    title = COALESCE(title, $2)
                WHERE id = $1
                """,
                conversation_id,
                last_user_message[:100],
            )

    # ── Conversation CRUD ─────────────────────────────────────────────────

    async def list_conversations(
        self, user_id: str, limit: int = 20
    ) -> list[dict]:
        """List recent conversations for a user."""
        async with get_tenant_db() as db:
            rows = await db.fetch(
                """
                SELECT id, title, message_count, last_message_at, created_at
                FROM chatbot_conversations
                WHERE user_id = $1
                ORDER BY COALESCE(last_message_at, created_at) DESC
                LIMIT $2
                """,
                user_id, limit,
            )
        return [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "message_count": r["message_count"],
                "last_message_at": r["last_message_at"].isoformat() if r["last_message_at"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

    async def get_conversation(self, conversation_id: str) -> dict | None:
        """Get a conversation with all its messages."""
        async with get_tenant_db() as db:
            conv = await db.fetchrow(
                """
                SELECT id, user_id, title, message_count, last_message_at, created_at
                FROM chatbot_conversations
                WHERE id = $1
                """,
                conversation_id,
            )
            if not conv:
                return None

            messages = await db.fetch(
                """
                SELECT id, role, content, tool_calls, tokens_used, created_at
                FROM chatbot_messages
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                """,
                conversation_id,
            )

        return {
            "id": str(conv["id"]),
            "user_id": str(conv["user_id"]),
            "title": conv["title"],
            "message_count": conv["message_count"],
            "last_message_at": conv["last_message_at"].isoformat() if conv["last_message_at"] else None,
            "created_at": conv["created_at"].isoformat() if conv["created_at"] else None,
            "messages": [
                {
                    "id": str(m["id"]),
                    "role": m["role"],
                    "content": m["content"],
                    "tool_calls": m["tool_calls"] if isinstance(m["tool_calls"], list) else (
                        json.loads(m["tool_calls"]) if isinstance(m["tool_calls"], str) else m["tool_calls"]
                    ),
                    "tokens_used": m["tokens_used"],
                    "created_at": m["created_at"].isoformat() if m["created_at"] else None,
                }
                for m in messages
            ],
        }

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation and its messages (cascade). Returns True if deleted."""
        async with get_tenant_db() as db:
            result = await db.execute(
                "DELETE FROM chatbot_conversations WHERE id = $1 AND user_id = $2",
                conversation_id, user_id,
            )
        return "DELETE 1" in result
