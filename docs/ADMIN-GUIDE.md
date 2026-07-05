# AuraFlow Platform Admin Guide

> **The definitive operations reference for the AuraFlow multi-tenant studio management platform.**
> Deployed on Hetzner VPS with Docker Compose and Nginx reverse proxy.

---

## Table of Contents

1. [Quick Start Checklist](#1-quick-start-checklist)
2. [API Key Configuration](#2-api-key-configuration)
3. [Platform Admin Dashboard](#3-platform-admin-dashboard)
4. [Daily Operations](#4-daily-operations)
5. [Backup and Recovery](#5-backup-and-recovery)
6. [SSL Certificate Management](#6-ssl-certificate-management)
7. [Scaling: Larger Hetzner VPS](#7-scaling-larger-hetzner-vps)
8. [Load Balancing](#8-load-balancing)
9. [Managed Database Migration](#9-managed-database-migration)
10. [AWS Migration Guide](#10-aws-migration-guide)
11. [Operational Notes](#11-operational-notes)
12. [Troubleshooting](#12-troubleshooting)
13. [Environment Variable Reference](#13-environment-variable-reference)

---

## 1. Quick Start Checklist

After provisioning a fresh Hetzner VPS (Ubuntu 22.04/24.04), follow these steps to bring the platform online.

### 1.1 Run the VPS Setup Script

```bash
# SSH into your new server as root
ssh root@YOUR_VPS_IP

# Download and run the setup script
bash /path/to/infra/scripts/setup-vps.sh
```

This script installs Docker, Nginx, Certbot, creates the `deploy` user, configures the firewall (ports 22, 80, 443), and sets up the `/opt/auraflow` directory.

### 1.2 Copy Project Files to the Server

```bash
# From your local machine
scp docker-compose.prod.yml deploy@YOUR_VPS:/opt/auraflow/
scp .env.prod deploy@YOUR_VPS:/opt/auraflow/
scp -r infra/ deploy@YOUR_VPS:/opt/auraflow/
scp -r apps/ deploy@YOUR_VPS:/opt/auraflow/
```

### 1.3 Configure Environment Variables

```bash
ssh deploy@YOUR_VPS
cd /opt/auraflow

# Copy the example and fill in real values
cp .env.prod.example .env.prod
nano .env.prod
```

At minimum, set these before first start:

- [ ] `APP_SECRET` -- generate with `openssl rand -hex 32`
- [ ] `POSTGRES_PASSWORD` -- generate with `openssl rand -hex 32`
- [ ] `REDIS_PASSWORD` -- generate with `openssl rand -hex 32`
- [ ] `DATABASE_URL` -- include the POSTGRES_PASSWORD you just generated
- [ ] `REDIS_URL` -- include the REDIS_PASSWORD you just generated
- [ ] `CORS_ORIGINS` -- set to your actual domains
- [ ] `APP_URL`, `API_URL` -- your production URLs
- [ ] `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_URL` -- must match APP_URL and API_URL

**Important:** The Redis password in `.env.prod` must match the password hardcoded in the `redis` service `command` inside `docker-compose.prod.yml`. If you change one, change both.

### 1.4 Configure DNS

Point these A records to your VPS IP address:

| Record | Type | Value |
|--------|------|-------|
| `auraflow.fit` | A | YOUR_VPS_IP |
| `www.auraflow.fit` | A | YOUR_VPS_IP |
| `app.auraflow.fit` | A | YOUR_VPS_IP |
| `api.auraflow.fit` | A | YOUR_VPS_IP |

Wait for DNS propagation (check with `dig +short app.auraflow.fit`).

**Cloudflare DNS notes:** If using Cloudflare, `app.auraflow.fit` and `api.auraflow.fit` must be set to **DNS only** (no orange cloud proxy). Cloudflare's JS challenge breaks the React app and API calls. The root domain `auraflow.fit` can stay proxied for marketing CDN benefits.

### 1.5 Deploy Nginx Configuration

```bash
sudo cp /opt/auraflow/infra/nginx/nginx.prod.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 1.6 Get SSL Certificates

```bash
sudo certbot --nginx \
  -d auraflow.fit \
  -d www.auraflow.fit \
  -d app.auraflow.fit \
  -d api.auraflow.fit
```

### 1.7 Build and Start Services

```bash
cd /opt/auraflow
./infra/scripts/deploy.sh full
```

This will:
1. Build all Docker images in parallel
2. Stop existing services and start new ones
3. Deploy the Nginx configuration
4. Run database migrations (`alembic upgrade head`)
5. Print health check status

### 1.8 Verify Everything Is Running

```bash
./infra/scripts/deploy.sh status
```

You should see all services as healthy:

```
  API:    healthy
  Web:    healthy
  DB:     healthy
  Redis:  healthy
  Nginx:  running
```

Also verify from outside:

```bash
curl -sf https://api.auraflow.fit/health
curl -sf https://app.auraflow.fit/
```

### 1.9 Create the First Platform Admin User

Connect to the database and insert the first platform admin:

```bash
docker exec -it auraflow_postgres psql -U auraflow -d auraflow -c \
  "UPDATE af_global.users SET is_platform_admin = true WHERE email = 'your-email@example.com';"
```

### 1.10 Post-Deploy Checklist

- [ ] All 6 Docker services running (postgres, redis, api, web, celery_worker, celery_beat)
- [ ] SSL certificates installed and HTTPS working
- [ ] Health endpoint returns 200
- [ ] Platform admin dashboard accessible at `/dashboard/platform/overview`
- [ ] Backup cron job configured (see [Section 5](#5-backup-and-recovery))
- [ ] Sentry DSNs configured for error monitoring
- [ ] API keys configured for active integrations

---

## 2. API Key Configuration

This section provides step-by-step instructions for configuring every third-party integration. All keys go in `.env.prod` unless otherwise noted. After changing `.env.prod`, rebuild and restart:

```bash
cd /opt/auraflow
./infra/scripts/deploy.sh build
./infra/scripts/deploy.sh restart
```

**Important for Next.js variables:** Any variable prefixed with `NEXT_PUBLIC_` is baked into the frontend at build time. If you change a `NEXT_PUBLIC_*` value, you must rebuild the `web` container -- a restart alone is not sufficient.

---

### 2.1 Stripe Connect (Payments)

Stripe handles all payment processing, subscriptions, and marketplace payouts for tenant studios.

**Steps:**

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com)
2. Navigate to **Developers > API Keys**
3. Copy your **Publishable key** (`pk_live_...`) and **Secret key** (`sk_live_...`)
4. Navigate to **Developers > Webhooks > Add endpoint**
5. Set the endpoint URL to:
   ```
   https://api.auraflow.fit/webhooks/stripe
   ```
6. Subscribe to these events:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `account.updated`
7. Copy the **Signing secret** (`whsec_...`)
8. For Stripe Connect (marketplace payouts to studios):
   - Navigate to **Settings > Connect settings**
   - Copy the **Platform client ID** (`ca_...`)
9. Set the platform fee percentage (default 1.25%)

**Environment variables:**

```bash
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CONNECT_CLIENT_ID=ca_...
STRIPE_PLATFORM_FEE_PERCENT=1.25
```

---

### 2.2 Anthropic (AI Features)

Anthropic's Claude powers the AI chatbot assistant, marketing content generation, member insights, schedule analysis, revenue forecasting, email processing, social media content, ad optimization, and landing page generation.

**Steps:**

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Navigate to **API Keys** and create a new key
3. Copy the key (`sk-ant-...`)

**Environment variables:**

```bash
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_MODEL_FAST=claude-haiku-4-5-20251001
ANTHROPIC_MAX_TOKENS=4096
```

The platform uses two models:
- **claude-sonnet-4-6** (primary) -- used for complex tasks: email processing, ad optimization, landing page generation, in-depth member insights
- **claude-haiku-4-5-20251001** (fast) -- used for quick tasks: chatbot responses, content suggestions, quick summaries

---

### 2.3 Twilio (SMS)

Twilio provides SMS notifications, appointment reminders, and marketing SMS campaigns.

**Steps:**

1. Go to [twilio.com/console](https://www.twilio.com/console)
2. From the dashboard, copy your **Account SID** and **Auth Token**
3. Navigate to **Phone Numbers > Manage > Active numbers**
4. Purchase a phone number (or use an existing one) with SMS capability
5. Copy the phone number in E.164 format (`+1XXXXXXXXXX`)

**Environment variables:**

```bash
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
TWILIO_MESSAGING_SERVICE_SID=MG...
```

**A2P 10DLC Compliance:** SMS is sent using a Twilio Messaging Service SID (not the phone number directly). This is required for Application-to-Person (A2P) messaging compliance on US 10DLC numbers. Register your brand and campaign in the Twilio console under **Messaging > Services**. All phone numbers are normalized to E.164 format (`+1XXXXXXXXXX`) before sending.

---

### 2.4 Mux (Video Hosting)

Mux provides video hosting, HLS adaptive streaming, and automatic thumbnail generation for on-demand class recordings and instructor content.

**Steps:**

1. Go to [dashboard.mux.com](https://dashboard.mux.com)
2. Navigate to **Settings > API Access Tokens**
3. Create a new token with **Mux Video** read/write permissions
4. Copy the **Token ID** and **Token Secret**
5. Navigate to **Settings > Webhooks**
6. Add a new webhook endpoint:
   ```
   https://api.auraflow.fit/webhooks/mux
   ```
7. Subscribe to events: `video.asset.ready`, `video.asset.errored`, `video.upload.asset_created`
8. Copy the **Webhook signing secret**
9. For the environment key (used for Mux Player), find it under **Settings > Environments**

**Environment variables:**

```bash
MUX_TOKEN_ID=...
MUX_TOKEN_SECRET=...
MUX_WEBHOOK_SECRET=...
MUX_ENV_KEY=...
```

---

### 2.5 SendGrid (Fallback Email)

SendGrid serves as the **fallback** email transport when the studio's primary SMTP (Purelymail) delivery fails. It handles the same transactional emails: welcome messages, password resets, booking confirmations, invoice receipts, and notification emails.

**Steps:**

1. Go to [app.sendgrid.com](https://app.sendgrid.com)
2. Navigate to **Settings > API Keys**
3. Create a new API key with **Full Access** or restricted to **Mail Send**
4. Copy the key (`SG...`)
5. For inbound email parsing (delivery tracking):
   - Navigate to **Settings > Inbound Parse**
   - Set up your domain and webhook URL
   - Copy the **Webhook Verification Key**
6. Verify your sender domain under **Settings > Sender Authentication**

**Environment variables:**

```bash
SENDGRID_API_KEY=SG...
SENDGRID_FROM_EMAIL=hello@auraflow.fit
SENDGRID_FROM_NAME=AuraFlow
SENDGRID_WEBHOOK_VERIFICATION_KEY=...
```

These can also be configured from the Platform Admin Dashboard under **Settings > Email Configuration** without editing `.env.prod`.

---

### 2.6 SMTP / Purelymail (Primary Email)

Studio SMTP (Purelymail) is the **primary** email sender for all tenant/studio transactional emails (booking confirmations, daily class reminders at 7 AM Pacific, post-class follow-ups). The studio's own SendGrid is the fallback. **Platform email (AuraFlow) is NEVER used for tenant emails** -- if the studio's email configuration fails, the email fails rather than falling back to an AuraFlow sender. The platform also uses IMAP (via Purelymail) for the AI-powered email inbox system.

**Steps:**

1. Create a [Purelymail](https://purelymail.com) account
2. Add your domain and configure MX records
3. Create mailbox accounts (e.g., `hello@auraflow.fit`, `support@auraflow.fit`)
4. Note the IMAP/SMTP settings:
   - IMAP: `imap.purelymail.com` port `993` (SSL)
   - SMTP: `smtp.purelymail.com` port `465` (SSL) or `587` (STARTTLS)

**Environment variables (primary SMTP):**

```bash
SMTP_HOST=smtp.purelymail.com
SMTP_PORT=587
SMTP_USE_TLS=false
SMTP_USERNAME=hello@auraflow.fit
SMTP_PASSWORD=your-purelymail-password
SMTP_FROM_EMAIL=hello@auraflow.fit
SMTP_FROM_NAME=AuraFlow
```

**Note:** Studio SMTP (Purelymail) is the primary transport for all studio transactional email. The studio's own SendGrid serves as a fallback if SMTP delivery fails. Platform email (AuraFlow) is never used for tenant emails. All email templates use the studio name as the sender, and all scheduled times are in Pacific (`America/Los_Angeles`). Individual email accounts are added through the Platform Admin Dashboard at **Email Inbox > Add Email Account**.

---

### 2.7 OpenAI (Whisper Speech-to-Text)

OpenAI's Whisper API powers voice check-in and voice notes functionality.

**Steps:**

1. Go to [platform.openai.com](https://platform.openai.com)
2. Navigate to **API Keys** and create a new secret key
3. Copy the key (`sk-...`)
4. Ensure your account has billing enabled and sufficient credits

**Environment variables:**

```bash
OPENAI_API_KEY=sk-...
```

---

### 2.8 Backblaze B2 (Object Storage)

Backblaze B2 stores database backups and platform assets (images, documents, uploads).

**Steps:**

1. Create an account at [backblaze.com](https://www.backblaze.com)
2. Navigate to **Buckets** and create two buckets:
   - `auraflow-backups` -- **Private** bucket for database and file backups
   - `auraflow-assets` -- **Public** bucket for user-uploaded images and documents
3. Navigate to **Application Keys**
4. Create a new application key with read/write access to both buckets
5. Copy the **keyID** (Account ID) and **applicationKey**
6. Note the S3-compatible endpoint for your region (e.g., `https://s3.us-west-002.backblazeb2.com`)

**Environment variables:**

```bash
B2_ACCOUNT_ID=your-key-id
B2_APPLICATION_KEY=your-application-key
B2_BUCKET_BACKUPS=auraflow-backups
B2_BUCKET_ASSETS=auraflow-assets
B2_ENDPOINT=https://s3.us-west-002.backblazeb2.com
```

**For the backup script** (`infra/scripts/backup.sh`), also install `rclone` on the server and configure the B2 remote:

```bash
sudo apt install rclone
rclone config
# Choose "Backblaze B2" as the storage type
# Enter your account ID and application key
```

---

### 2.9 Sentry (Error Monitoring)

Sentry tracks errors and performance across both the API and web frontend.

**Steps:**

1. Go to [sentry.io](https://sentry.io) and create an organization
2. Create two projects:
   - **auraflow-api** -- Platform: Python (FastAPI)
   - **auraflow-web** -- Platform: Next.js (JavaScript)
3. Copy the **DSN** from each project's settings (Settings > Client Keys)

**Environment variables:**

```bash
SENTRY_DSN_API=https://examplePublicKey@o0.ingest.sentry.io/0
SENTRY_DSN_WEB=https://examplePublicKey@o0.ingest.sentry.io/1
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

Set `SENTRY_TRACES_SAMPLE_RATE` between `0.0` (no performance tracing) and `1.0` (trace every request). `0.1` (10%) is a good default for production.

---

### 2.10 Square (POS Integration)

Square provides point-of-sale integration for in-studio retail purchases.

**Steps:**

1. Go to [developer.squareup.com](https://developer.squareup.com)
2. Create a new application
3. Copy the **Application ID** from the application dashboard
4. Navigate to **Locations** and copy the **Location ID** for your primary location
5. Set the environment to `production` (use `sandbox` for testing)

**Environment variables:**

```bash
NEXT_PUBLIC_SQUARE_APPLICATION_ID=sq0idp-...
NEXT_PUBLIC_SQUARE_LOCATION_ID=...
NEXT_PUBLIC_SQUARE_ENVIRONMENT=production
```

**Note:** These are `NEXT_PUBLIC_` variables, so you must rebuild the `web` container after changing them.

---

### 2.11 Zoom (Livestream Classes)

Zoom integration enables livestream class sessions directly from the platform.

**Steps:**

1. Go to [marketplace.zoom.us](https://marketplace.zoom.us)
2. Click **Develop > Build App**
3. Choose **Server-to-Server OAuth** app type
4. Fill in the required app information
5. Under **Scopes**, add:
   - `meeting:write:admin`
   - `meeting:read:admin`
   - `meeting:delete:admin`
   - `user:read:admin`
6. Activate the app
7. Copy **Account ID**, **Client ID**, and **Client Secret**

**Environment variables:**

```bash
ZOOM_ACCOUNT_ID=...
ZOOM_CLIENT_ID=...
ZOOM_CLIENT_SECRET=...
```

---

### 2.12 Google Ads and Google My Business

Google Ads integration enables ad campaign management and AI optimization. Google My Business enables listing management.

**Steps:**

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable the **Google Ads API** and **My Business Account Management API**
4. Navigate to **APIs & Services > Credentials**
5. Create an **OAuth 2.0 Client ID** (Web application type)
6. Copy the **Client ID** and **Client Secret**
7. For Google Ads, you also need:
   - A **Developer Token** from [ads.google.com/aw/apicenter](https://ads.google.com/aw/apicenter)
   - The **Login Customer ID** (your MCC account ID, format: `123-456-7890`)

These are configured from the Platform Admin Dashboard under **Settings > Google Ads** or via `.env.prod`:

```bash
# These go in the Platform Settings DB (via admin dashboard), not .env.prod
# google_ads_developer_token=...
# google_ads_login_customer_id=123-456-7890
# google_client_id=...apps.googleusercontent.com
# google_client_secret=...
```

---

### 2.13 Meta / Facebook and Instagram

Meta integration powers Facebook and Instagram ad management and social media posting.

**Steps:**

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create a new app (Business type)
3. Copy the **App ID** and **App Secret**
4. Navigate to your Facebook Page settings
5. Generate a **Page Access Token** with extended permissions:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_messaging`
   - `instagram_basic`
   - `instagram_content_publish`
6. Copy the **Page ID** from your Facebook Page's About section
7. For Instagram, link your Instagram Business Account and copy the **Instagram Business Account ID**

These are configured from the Platform Admin Dashboard under **Settings > Meta / Facebook Ads**:

```
meta_app_id=...
meta_app_secret=...
meta_page_access_token=...
meta_page_id=...
instagram_business_account_id=...
```

---

### 2.14 Gusto (Payroll)

Gusto integration is planned for staff payroll management.

**Steps:**

1. Go to [gusto.com/developers](https://gusto.com/developers)
2. Create an OAuth application
3. Set the redirect URI to `https://api.auraflow.fit/integrations/gusto/callback`
4. Copy the **Client ID** and **Client Secret**

*Configuration details will be added when the Gusto integration is built (Round 3).*

---

### 2.15 QuickBooks (Payroll Export)

QuickBooks integration is planned for accounting and payroll export.

**Steps:**

1. Go to [developer.intuit.com](https://developer.intuit.com)
2. Create an app and select **Accounting** scope
3. Set the redirect URI to `https://api.auraflow.fit/integrations/quickbooks/callback`
4. Copy the **Client ID** and **Client Secret**

*Configuration details will be added when the QuickBooks integration is built (Round 3).*

---

## 3. Platform Admin Dashboard

The Platform Admin Dashboard is accessible at `/dashboard/platform/` and is restricted to users with the `is_platform_admin` flag set to `true`. If a non-admin user navigates to these pages, they are redirected to the standard dashboard.

The sidebar navigation includes 12 pages organized by function.

---

### 3.1 Overview

**Path:** `/dashboard/platform/overview`

**What it shows:**
- Total organizations on the platform
- Active organizations (non-suspended)
- Total users across all tenants

**When to use:** Quick pulse check on platform growth. This is the default landing page for the platform admin section.

---

### 3.2 Organizations

**Path:** `/dashboard/platform/organizations`

**What it shows:**
- Table of all tenant organizations with: Name, Slug, Status (active/suspended/trial), User Count, Created Date
- Status badges color-coded: green for active, red for suspended, blue for trial

**Available actions:**
- **Suspend** an active organization -- immediately blocks all access for that tenant
- **Activate** a suspended organization -- restores access
- **Delete** an organization -- permanently removes the tenant, its schema (`af_tenant_{slug}`), and all associated data. Requires confirmation dialog. **This is irreversible.**

**When to use:** Onboarding new studios, investigating tenant issues, managing trial-to-paid conversions, suspending accounts for non-payment.

---

### 3.3 Users

**Path:** `/dashboard/platform/users`

**What it shows:**
- Table of all users across the platform: Email, Name, Active status, Platform Admin flag, Organization count

**Available actions:**
- **Change Password** -- opens a modal to set a new password for any user (minimum 8 characters)
- **Deactivate** -- disables a user's account (unavailable for platform admins)
- **Delete** -- permanently removes a user (unavailable for platform admins, requires confirmation)

**When to use:** Password resets when a user is locked out, deactivating accounts, investigating suspicious activity, verifying platform admin assignments.

---

### 3.4 Feature Flags

**Path:** `/dashboard/platform/flags`

**What it shows:**
- Organization selector dropdown
- Grid of all feature flags for the selected organization, each with a toggle switch
- Flags with per-org overrides are labeled "org override"

**Available actions:**
- **Toggle** any feature flag on/off for a specific organization

**When to use:** Gradual feature rollouts (enable a feature for one studio before all), disabling a broken feature for a specific tenant, A/B testing functionality.

**Note:** Feature flags are cached in Redis with a 5-minute TTL (`FEATURE_FLAGS_CACHE_TTL=300`). After toggling a flag, it may take up to 5 minutes for the change to take effect across all API instances.

---

### 3.5 Announcements

**Path:** `/dashboard/platform/announcements`

**What it shows:**
- List of all platform announcements with: Title, Type badge, Active/Inactive status, Body text, Creation date

**Available actions:**
- **Create Announcement** -- opens a dialog with fields for Title, Body (optional), and Type:
  - `info` (blue) -- general platform updates
  - `warning` (yellow) -- important notices
  - `maintenance` (orange) -- scheduled downtime
  - `feature` (green) -- new feature announcements

**When to use:** Communicating scheduled maintenance windows, announcing new features, warning about known issues, platform-wide notifications.

---

### 3.6 Email Inbox

**Path:** `/dashboard/platform/emails`

**What it shows:**
- **Email Accounts section** -- all configured IMAP/SMTP accounts (e.g., Purelymail) with connection status and last check time
- **Stats cards** -- Pending emails, Resolved today, Average response time, Escalated count
- **Email list** -- all inbound emails with: Sender, Mailbox, AI Status badge (pending/processing/resolved/escalated/failed), Subject, Date, AI summary

**Available actions:**
- **Add Email Account** -- configure a new IMAP/SMTP account (email address, display name, IMAP host/port, SMTP host/port, username, password)
- **Test** an account -- verifies IMAP and SMTP connectivity
- **Check Mail** -- manually trigger an IMAP fetch across all accounts (or per-account)
- **Delete** an account -- removes the IMAP/SMTP configuration
- **AI Process** -- send a pending email through the AI for automated classification, response drafting, and action execution
- **Reclassify** -- override the AI classification on a processed email (manually re-categorize)
- **Reply** -- type and send a manual reply via SMTP
- **Escalate** -- manually escalate an email for human attention
- **Resolve** -- mark an email as resolved
- **Filter** by status (pending, processing, resolved, escalated, failed) and mailbox (hello@, support@)

**When to use:** Daily email triage, monitoring AI email processing quality, manually handling escalated emails, adding new support mailboxes.

---

### 3.7 Social Media

**Path:** `/dashboard/platform/social`

**What it shows:**
- **Connection status** for Facebook and Instagram (configured/not configured)
- **Posts tab** -- all social media posts with: Platform icon, Status (draft/scheduled/published/failed), AI-generated flag, Content preview, Engagement metrics (likes, comments)
- **Messages tab** -- inbound social messages with: Platform, Sender, Message type, AI status, AI response

**Available actions:**
- **Create Post** -- create a new social media post for Facebook or Instagram
  - **AI Generate** -- enter a topic and have Claude generate the post content
- **Publish** a draft post
- **Delete** a draft/scheduled post

**When to use:** Managing the platform's social media presence, creating marketing content with AI assistance, monitoring and responding to inbound social messages.

**Prerequisite:** Meta/Facebook credentials must be configured in Settings (meta_app_id, meta_app_secret, meta_page_access_token, meta_page_id, instagram_business_account_id).

---

### 3.8 Ad Campaigns

**Path:** `/dashboard/platform/ads`

**What it shows:**
- **Connection status** for Google Ads and Meta Ads (links to Settings page for configuration)
- **Performance cards (30 days)** -- Total Spend, Impressions, Clicks, Conversions, ROAS
- **Platform breakdown** -- separate Google Ads and Meta Ads metrics
- **Ad Settings** -- max monthly spend limits (Google and Meta), platform toggles (Google enabled, Meta enabled, AI Auto-Optimize)
- **AI Optimization** -- trigger AI optimization for Google or Meta campaigns, with a log of recent AI actions

**Available actions:**
- **Save Limits** -- set maximum monthly ad spend per platform
- **Toggle** Google Ads, Meta Ads, or AI Auto-Optimize on/off
- **Optimize Google Ads** -- trigger AI-driven campaign optimization
- **Optimize Meta Ads** -- trigger AI-driven campaign optimization

**When to use:** Monitoring ad spend and ROI, setting budget caps, triggering AI optimization, enabling/disabling ad platforms.

---

### 3.9 Landing Pages

**Path:** `/dashboard/platform/landing-pages`

**What it shows:**
- **Stats** -- Total pages, Active count, Total views, Conversion rate
- **Filter** by status (all, draft, active, paused)
- **Pages table** -- Title, Slug (/lp/{slug}), Campaign source, Status, Views, Conversions, Conversion rate

**Available actions:**
- **AI Generate** -- create a landing page with AI:
  - Link to an existing ad campaign (Google or Meta)
  - Specify topic/campaign name
  - Select campaign source (organic, Google Ads, Meta Ads, email, social)
  - Paste ad copy for AI message matching
- **Edit** -- modify title, slug, hero headline, hero subheadline, CTA text/URL, meta title/description, status
- **View** -- open active landing pages in a new tab
- **Delete** -- remove a landing page

**When to use:** Creating ad-matched landing pages for campaigns, monitoring conversion rates, A/B testing different page variants.

---

### 3.10 Infrastructure

**Path:** `/dashboard/platform/infrastructure`

This page has four tabs:

#### Database Tab
- Database size, connection count (with utilization bar), cache hit ratio, uptime
- Transaction stats: committed, rolled back, deadlocks, temp files
- Active connections table: PID, State, Client, Duration, Query
- Largest tables: Schema, Table name, Size, Row estimate
- **Run Integrity Check** button -- checks for bloated tables and invalid indexes

#### Backups Tab
- **Backup Database** button -- triggers an on-demand database backup
- **Backup Files** button -- triggers an on-demand files backup
- Backup schedules with cron expressions, retention days, last run time, and active toggle
- Backup history table: Type, Status, File name, Size, Duration, Trigger, Created date
- **Download** completed backups

#### Traffic Tab
- Active users (5 minutes), Requests (24h), Average response time, Errors (24h)
- Active user breakdown: last 5 minutes, last 1 hour, last 24 hours
- Request volume bar chart (24h)
- Top endpoints by request count

#### Security Tab
- Total events (24h), Unacknowledged count, High/Critical event counts
- **Run Security Scan** button
- Filter by severity (critical, high, medium, low)
- Security events feed with: event type, severity badge, source IP, endpoint, timestamp, details
- **Acknowledge** individual events

**When to use:** Daily infrastructure monitoring, investigating slow queries, checking backup status, reviewing security events.

---

### 3.11 System Health

**Path:** `/dashboard/platform/health`

**What it shows:**
- **Service status pills** -- API, Database, Redis, Celery (healthy/unhealthy/unknown)
- **Server metrics** -- CPU usage (with utilization bar), Memory usage (used/total with bar), Disk usage (used/total/free with bar), Load average (1m/5m/15m), Platform/Python version, Process uptime, Hostname
- **Database metrics** -- PostgreSQL version, Uptime, Connections (with utilization bar), Cache hit ratio, Database size, Transaction counts, Temp files, Replication status
- **Redis metrics** -- Version, Memory used (of max), Connected clients, Uptime
- **Active queries table** -- PID, State, Client, Duration with severity badge, Query text
- Last updated timestamp (auto-refreshes every 30 seconds)

**When to use:** Real-time health monitoring, diagnosing performance issues, checking if Celery workers are running, verifying Redis memory usage.

---

### 3.12 Settings

**Path:** `/dashboard/platform/settings`

**What it shows:** Three collapsible configuration sections:

#### Email Configuration (SendGrid)
- SendGrid API Key, From Email, From Name, Inbound Webhook Secret
- Admin Alert Email, Escalation Email
- **Test Credentials** button -- verifies SendGrid API key is valid
- **Save** button

#### Google Ads (Platform Level)
- Developer Token, Login Customer ID, Client ID, Client Secret
- **Save** button

#### Meta / Facebook Ads (Platform Level)
- App ID, App Secret, Page Access Token, Page ID, Instagram Business Account ID
- **Save** button

**When to use:** Initial API key configuration, rotating credentials, updating sender information. These settings are stored in the database (not `.env.prod`) and can be changed without restarting services.

---

## 4. Daily Operations

### 4.1 Checking Service Status

```bash
cd /opt/auraflow
./infra/scripts/deploy.sh status
```

This checks: API, Web, PostgreSQL, Redis, Nginx, and SSL certificate expiry.

### 4.2 Viewing Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f celery_worker
docker compose -f docker-compose.prod.yml logs -f celery_beat

# Last 100 lines of API logs
docker compose -f docker-compose.prod.yml logs --tail=100 api

# Logs since a specific time
docker compose -f docker-compose.prod.yml logs --since="2026-03-04T00:00:00" api
```

### 4.3 Health Endpoints

```bash
# API health check
curl -sf https://api.auraflow.fit/health | python3 -m json.tool

# From inside the server (no SSL)
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:3000/
```

### 4.4 Redis Monitoring

```bash
# Redis info
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  info

# Memory usage
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  info memory

# Connected clients
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  info clients

# Key count
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  dbsize

# Flush cache (if needed -- will clear feature flag cache)
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  flushdb
```

### 4.5 PostgreSQL Monitoring

```bash
# Organization count
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT count(*) FROM af_global.organizations;"

# Active organizations
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT name, slug, status FROM af_global.organizations ORDER BY created_at DESC;"

# User count
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT count(*) FROM af_global.users;"

# Database size
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT pg_size_pretty(pg_database_size('auraflow'));"

# Active connections
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'auraflow';"

# List all tenant schemas
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'af_tenant_%';"

# Check for long-running queries (>30 seconds)
docker exec auraflow_postgres psql -U auraflow -d auraflow -c \
  "SELECT pid, now() - pg_stat_activity.query_start AS duration, query
   FROM pg_stat_activity
   WHERE (now() - pg_stat_activity.query_start) > interval '30 seconds'
   AND state = 'active';"
```

### 4.6 Running Database Migrations

```bash
cd /opt/auraflow
./infra/scripts/deploy.sh migrate

# Or manually:
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### 4.7 Restarting Individual Services

```bash
cd /opt/auraflow

# Restart just the API (zero-downtime if Nginx handles the brief gap)
docker compose -f docker-compose.prod.yml restart api

# Restart Celery workers
docker compose -f docker-compose.prod.yml restart celery_worker celery_beat

# Rebuild and restart a single service
docker compose -f docker-compose.prod.yml build api
docker compose -f docker-compose.prod.yml up -d api
```

### 4.8 Docker Resource Usage

```bash
# Container resource usage
docker stats --no-stream

# Disk usage
docker system df

# Clean up unused images and build cache
docker system prune -f
sudo docker builder prune -af   # Reclaim all build cache (can be many GB)
```

---

## 5. Backup and Recovery

### 5.1 Manual Database Backup

```bash
# Full cluster backup (all schemas including af_global and all af_tenant_*)
docker exec auraflow_postgres pg_dumpall -U auraflow --clean --if-exists \
  | gzip > /tmp/auraflow-backup-$(date +%Y%m%d-%H%M).sql.gz

# Check the backup size
ls -lh /tmp/auraflow-backup-*.sql.gz
```

### 5.2 Manual Redis Backup

```bash
# Trigger a background save
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  bgsave

# Copy the dump file
docker cp auraflow_redis:/data/dump.rdb /tmp/redis-backup-$(date +%Y%m%d).rdb

# Also copy the append-only file if it exists
docker cp auraflow_redis:/data/appendonly.aof /tmp/redis-aof-$(date +%Y%m%d).aof
```

### 5.3 Upload Backups to Backblaze B2

Using the `rclone` tool:

```bash
# Upload database backup
rclone copy /tmp/auraflow-backup-20260304-0200.sql.gz \
  b2:auraflow-backups/postgres/

# Upload Redis backup
rclone copy /tmp/redis-backup-20260304.rdb \
  b2:auraflow-backups/redis/
```

Or using the `b2` CLI directly:

```bash
b2 upload-file auraflow-backups \
  /tmp/auraflow-backup-20260304-0200.sql.gz \
  backups/postgres/20260304-0200.sql.gz
```

### 5.4 Automated Backup Cron Job

The backup script at `infra/scripts/backup.sh` automates PostgreSQL backup and B2 upload. Set it up as a daily cron job:

```bash
# Edit the deploy user's crontab
crontab -e

# Add this line to run backup at 2:00 AM daily
0 2 * * * DB_PASSWORD=YOUR_POSTGRES_PASSWORD B2_BUCKET_BACKUPS=auraflow-backups /opt/auraflow/infra/scripts/backup.sh >> /var/log/auraflow-backup.log 2>&1
```

The backup script:
- Dumps the entire PostgreSQL cluster with `pg_dumpall`
- Compresses with gzip
- Uploads to Backblaze B2 via rclone
- Cleans up local backups older than 3 days
- Cleans up remote backups older than 90 days

### 5.5 Full Database Restoration

**Warning: This is a destructive operation. It will replace all existing data.**

```bash
# 1. Stop application services (keep postgres running)
cd /opt/auraflow
docker compose -f docker-compose.prod.yml stop api web celery_worker celery_beat

# 2. Download the backup from B2
rclone copy b2:auraflow-backups/postgres/20260304-0200.sql.gz /tmp/

# 3. Decompress
gunzip /tmp/20260304-0200.sql.gz

# 4. Restore (pg_dumpall with --clean drops and recreates)
docker exec -i auraflow_postgres psql -U auraflow -d postgres < /tmp/20260304-0200.sql

# 5. Restart all services
docker compose -f docker-compose.prod.yml up -d

# 6. Verify
./infra/scripts/deploy.sh status
```

### 5.6 Redis Restoration

```bash
# 1. Stop Redis
docker compose -f docker-compose.prod.yml stop redis

# 2. Copy the dump file into the volume
docker cp /tmp/redis-backup-20260304.rdb auraflow_redis:/data/dump.rdb

# 3. Start Redis
docker compose -f docker-compose.prod.yml start redis
```

### 5.7 Recommended Backup Schedule

| What | Frequency | Retention | Storage |
|------|-----------|-----------|---------|
| PostgreSQL full dump | Daily at 2:00 AM | 90 days remote, 3 days local | Backblaze B2 |
| Redis RDB snapshot | Daily at 3:00 AM | 30 days | Backblaze B2 |
| .env.prod | After every change | Keep all versions | Local + B2 |

---

## 6. SSL Certificate Management

### 6.1 Initial Certificate Setup

After DNS records are pointing to your server:

```bash
sudo certbot --nginx \
  -d auraflow.fit \
  -d www.auraflow.fit \
  -d app.auraflow.fit \
  -d api.auraflow.fit
```

Certbot will:
1. Verify domain ownership via HTTP-01 challenge
2. Obtain certificates from Let's Encrypt
3. Automatically modify the Nginx configuration to use SSL
4. Set up HTTP-to-HTTPS redirect

### 6.2 Auto-Renewal

Certbot automatically installs a systemd timer for certificate renewal. Verify it is active:

```bash
sudo systemctl status certbot.timer
```

Expected output:
```
certbot.timer - Run certbot twice daily
   Loaded: loaded
   Active: active (waiting)
```

### 6.3 Manual Renewal

Test renewal without actually renewing:

```bash
sudo certbot renew --dry-run
```

Force renewal:

```bash
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

### 6.4 Certificate Locations

```
/etc/letsencrypt/live/auraflow.fit/fullchain.pem   # Certificate chain
/etc/letsencrypt/live/auraflow.fit/privkey.pem      # Private key
/etc/letsencrypt/live/auraflow.fit/cert.pem         # Server certificate only
/etc/letsencrypt/live/auraflow.fit/chain.pem        # Intermediate certificates
```

### 6.5 Check Certificate Expiry

```bash
# Via deploy.sh status
./infra/scripts/deploy.sh status

# Or directly
openssl x509 -enddate -noout -in /etc/letsencrypt/live/auraflow.fit/fullchain.pem
```

Let's Encrypt certificates are valid for 90 days. Certbot renews them when fewer than 30 days remain.

---

## 7. Scaling: Larger Hetzner VPS

When the current VPS reaches capacity (CPU consistently above 80%, memory above 80%, or response times degrading), migrate to a larger Hetzner plan.

### Recommended Plans

| Plan | vCPU | RAM | Disk | Monthly | Good For |
|------|------|-----|------|---------|----------|
| CPX21 (current) | 3 | 4 GB | 80 GB | ~$10 | Up to ~50 orgs |
| CPX31 | 4 | 8 GB | 160 GB | ~$15 | 50-200 orgs |
| CPX41 | 8 | 16 GB | 240 GB | ~$28 | 200-500 orgs |
| CCX13 | 2 | 8 GB | 80 GB | ~$15 | CPU-intensive (dedicated) |
| CCX23 | 4 | 16 GB | 160 GB | ~$30 | 200-500 orgs (dedicated) |
| CCX33 | 8 | 32 GB | 240 GB | ~$60 | 500+ orgs (dedicated) |

### Migration Steps

**1. Provision the new server**

```bash
# In Hetzner Cloud Console, create a new server
# Choose your target plan (e.g., CPX31)
# Select Ubuntu 22.04 or 24.04
# Add your SSH key
# Note the new IP address
```

**2. Set up the new server**

```bash
ssh root@NEW_VPS_IP
bash /path/to/setup-vps.sh
```

**3. Clone the repository and copy config**

```bash
# On the new server as deploy user
su - deploy
git clone git@github.com:KinovaAI/auraflow.git /opt/auraflow
# Or scp the files from old server

# Copy .env.prod from old server
scp deploy@OLD_VPS_IP:/opt/auraflow/.env.prod /opt/auraflow/.env.prod
```

**4. Backup the current database**

```bash
# On the OLD server
docker exec auraflow_postgres pg_dumpall -U auraflow --clean --if-exists \
  | gzip > /tmp/migration-backup.sql.gz
```

**5. Backup Redis data**

```bash
# On the OLD server
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  bgsave
sleep 5
docker cp auraflow_redis:/data/dump.rdb /tmp/redis-migration.rdb
```

**6. Transfer backups to the new server**

```bash
scp /tmp/migration-backup.sql.gz deploy@NEW_VPS_IP:/tmp/
scp /tmp/redis-migration.rdb deploy@NEW_VPS_IP:/tmp/
```

**7. Start services on the new server (without data)**

```bash
# On the NEW server
cd /opt/auraflow
docker compose -f docker-compose.prod.yml up -d postgres redis
sleep 10  # Wait for postgres to initialize
```

**8. Restore database**

```bash
gunzip /tmp/migration-backup.sql.gz
docker exec -i auraflow_postgres psql -U auraflow -d postgres < /tmp/migration-backup.sql
```

**9. Restore Redis**

```bash
docker compose -f docker-compose.prod.yml stop redis
docker cp /tmp/redis-migration.rdb auraflow_redis:/data/dump.rdb
docker compose -f docker-compose.prod.yml start redis
```

**10. Start all services**

```bash
./infra/scripts/deploy.sh build
./infra/scripts/deploy.sh restart
```

**11. Update DNS records**

Update all A records to point to the new VPS IP:
- `auraflow.fit` -> NEW_VPS_IP
- `www.auraflow.fit` -> NEW_VPS_IP
- `app.auraflow.fit` -> NEW_VPS_IP
- `api.auraflow.fit` -> NEW_VPS_IP

**12. Get SSL certificates on the new server**

```bash
sudo certbot --nginx \
  -d auraflow.fit \
  -d www.auraflow.fit \
  -d app.auraflow.fit \
  -d api.auraflow.fit
```

**13. Verify health**

```bash
./infra/scripts/deploy.sh status
curl -sf https://api.auraflow.fit/health
```

**14. Decommission the old server**

After verifying everything works (wait at least 24-48 hours):
- Cancel/delete the old Hetzner server
- Remove any DNS records pointing to the old IP

---

## 8. Load Balancing

When a single VPS can no longer handle the load, deploy multiple application servers behind a Hetzner Load Balancer.

### 8.1 Architecture

```
                    +-----------------------+
                    |   Hetzner Cloud LB    |
                    |   (Layer 7 / HTTP)    |
                    +-----------+-----------+
                                |
                 +--------------+--------------+
                 |              |              |
          +------+------+ +----+----+ +------+------+
          |   VPS #1    | | VPS #2  | |   VPS #3    |
          | api + web   | | api     | | api + web   |
          | celery      | | web     | | celery      |
          +------+------+ +---------+ +------+------+
                 |                            |
                 +----------+---------+-------+
                            |         |
                    +-------+--+ +----+------+
                    | Managed  | | Managed   |
                    | Postgres | | Redis     |
                    +----------+ +-----------+
```

### 8.2 Hetzner Load Balancer Setup

1. In Hetzner Cloud Console, create a **Load Balancer** (LB11 for basic, LB21 for production)
2. Configure:
   - **Algorithm:** Round Robin
   - **Protocol:** HTTPS (terminate SSL at the LB)
   - **Health check:** HTTP GET `http://backend:8000/health` every 10s
   - **Certificate:** Upload your Let's Encrypt cert or use Hetzner managed cert
3. Add your VPS instances as targets
4. Point DNS to the Load Balancer IP

### 8.3 JWT and Stateless Sessions

AuraFlow uses JWT-based authentication, which is stateless. This means:
- **No sticky sessions required** -- any backend can handle any request
- Access tokens are validated independently by each API instance
- The only shared state is in PostgreSQL and Redis

### 8.4 Shared Redis

All API instances must connect to the same Redis for:
- Feature flag cache consistency
- Celery task broker and result backend
- Rate limiting

Options:
- **Hetzner Managed Redis** (not yet available -- use a dedicated Redis VPS)
- **Redis on a dedicated VPS** with a private network IP
- **Redis Sentinel** for high availability (3 nodes: 1 master + 2 replicas)

### 8.5 Nginx Upstream Configuration

If running Nginx on each VPS (rather than the LB), configure upstream:

```nginx
upstream api_backend {
    least_conn;
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
    server 10.0.0.3:8000;
}

upstream web_backend {
    least_conn;
    server 10.0.0.1:3000;
    server 10.0.0.3:3000;
}

server {
    listen 443 ssl;
    server_name api.auraflow.fit;

    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE / long-polling support
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 300s;
    }
}
```

### 8.6 SSE (Server-Sent Events) Considerations

The platform uses SSE for real-time AI streaming responses. When load balancing:
- Set `proxy_read_timeout` to at least 300 seconds
- Use `Connection: ""` (not `keep-alive`) in the upstream proxy
- Configure the load balancer idle timeout to match (300s minimum)
- Do not enable response buffering for SSE endpoints

### 8.7 Celery Workers

Run Celery workers on only one or two VPS instances (not all) to avoid duplicate task execution:
- **celery_beat** (scheduler) must run on exactly ONE instance
- **celery_worker** can run on multiple instances
- All workers share the same Redis broker and PostgreSQL result backend

---

## 9. Managed Database Migration

Migrate from the Docker PostgreSQL container to a Hetzner Managed Database for better reliability, automatic backups, and connection pooling.

### 9.1 Create a Managed Database

1. In Hetzner Cloud Console, navigate to **Databases**
2. Create a new database:
   - **Engine:** PostgreSQL 16
   - **Plan:** Start with DB-1 (2 vCPU, 4 GB RAM) and scale as needed
   - **Region:** Same as your VPS (e.g., Falkenstein)
   - **Network:** Attach to the same private network as your VPS
3. Note the connection details:
   - Host, Port (default 25060 for managed DBs)
   - Username (default `doadmin` or custom)
   - Password
   - Database name

### 9.2 Export Data from Docker PostgreSQL

```bash
# Full cluster dump
docker exec auraflow_postgres pg_dumpall -U auraflow --clean --if-exists \
  | gzip > /tmp/managed-db-migration.sql.gz
```

### 9.3 Restore to Managed Database

```bash
gunzip /tmp/managed-db-migration.sql.gz

# Restore (use the managed DB connection details)
PGPASSWORD=managed_db_password psql \
  -h managed-db-host.hetzner.cloud \
  -p 25060 \
  -U doadmin \
  -d defaultdb \
  < /tmp/managed-db-migration.sql
```

### 9.4 Update Environment Variables

Edit `.env.prod`:

```bash
# Old (Docker PostgreSQL)
# DATABASE_URL=postgresql://auraflow:password@auraflow_postgres:5432/auraflow

# New (Managed PostgreSQL)
DATABASE_URL=postgresql://doadmin:managed_password@managed-db-host.hetzner.cloud:25060/auraflow?sslmode=require
```

### 9.5 Remove Docker PostgreSQL

Edit `docker-compose.prod.yml`:
- Remove the `postgres` service block
- Remove `postgres` from `depends_on` in `api`, `celery_worker`, and `celery_beat`
- Remove the `postgres_data` volume

### 9.6 Rebuild and Restart

```bash
./infra/scripts/deploy.sh build
./infra/scripts/deploy.sh restart
./infra/scripts/deploy.sh status
```

### 9.7 Connection Pooling

Hetzner Managed PostgreSQL includes PgBouncer. Use the **connection pool** port (default 25061) for application connections:

```bash
DATABASE_URL=postgresql://doadmin:password@managed-db-host.hetzner.cloud:25061/auraflow?sslmode=require
```

With PgBouncer, you can reduce `DATABASE_POOL_SIZE` in `.env.prod` since PgBouncer handles connection multiplexing.

---

## 10. AWS Migration Guide

This section outlines the full migration path from a single-VPS Hetzner deployment to AWS managed services.

### 10.1 Architecture Mapping

| Current (Hetzner) | AWS Equivalent | Notes |
|--------------------|----------------|-------|
| Docker Compose | ECS Fargate (or EKS) | Serverless containers, no servers to manage |
| PostgreSQL (Docker) | RDS PostgreSQL | Managed, automated backups, read replicas |
| Redis (Docker) | ElastiCache Redis | Managed, multi-AZ, automatic failover |
| Nginx (host) | ALB (Application Load Balancer) | Layer 7, SSL termination, path routing |
| Let's Encrypt SSL | ACM (AWS Certificate Manager) | Free, auto-renewing certificates |
| DNS (external) | Route 53 | DNS management with health checks |
| Backblaze B2 | S3 | Object storage, lifecycle policies |
| Sentry (external) | CloudWatch + X-Ray | Or keep Sentry (works from anywhere) |
| deploy.sh | CodePipeline / GitHub Actions | CI/CD: GitHub -> ECR -> ECS |
| VPS monitoring | CloudWatch | Metrics, alarms, dashboards |

### 10.2 AWS Service Setup

#### ECS Fargate

1. Create an ECS cluster
2. Create ECR repositories: `auraflow-api`, `auraflow-web`
3. Push Docker images to ECR
4. Create Task Definitions for:
   - **api** -- 1 vCPU, 2 GB memory, port 8000
   - **web** -- 0.5 vCPU, 1 GB memory, port 3000
   - **celery_worker** -- 1 vCPU, 2 GB memory
   - **celery_beat** -- 0.25 vCPU, 0.5 GB memory (desired count: 1)
5. Create ECS Services with desired count and auto-scaling

#### RDS PostgreSQL

1. Create an RDS instance: PostgreSQL 16, db.t3.medium or larger
2. Enable Multi-AZ for production
3. Enable automated backups (35-day retention)
4. Create a parameter group with settings matching your current config

#### ElastiCache Redis

1. Create a Redis cluster: cache.t3.micro or larger
2. Enable Multi-AZ with automatic failover
3. Set `maxmemory-policy` to `allkeys-lru`

#### ALB

1. Create an Application Load Balancer
2. Create target groups for API (port 8000) and Web (port 3000)
3. Configure listener rules:
   - `api.auraflow.fit/*` -> API target group
   - `app.auraflow.fit/*` -> Web target group
4. Attach ACM certificate

### 10.3 Data Migration Steps

```bash
# 1. Export from Hetzner PostgreSQL
docker exec auraflow_postgres pg_dumpall -U auraflow --clean --if-exists \
  | gzip > migration.sql.gz

# 2. Transfer to an EC2 instance (or your local machine)
scp deploy@hetzner-vps:/tmp/migration.sql.gz .

# 3. Restore to RDS
gunzip migration.sql.gz
PGPASSWORD=rds_password psql \
  -h auraflow-db.xxxx.us-east-1.rds.amazonaws.com \
  -p 5432 \
  -U auraflow \
  -d auraflow \
  < migration.sql

# 4. Update DNS to point to ALB
# In Route 53, create ALIAS records pointing to the ALB DNS name

# 5. Verify
curl -sf https://api.auraflow.fit/health
```

### 10.4 Cost Comparison

| Component | Hetzner (CPX31) | AWS Equivalent | AWS Monthly Cost |
|-----------|-----------------|----------------|------------------|
| Compute | Included | ECS Fargate (2 tasks) | ~$70-120 |
| Database | Included | RDS db.t3.medium | ~$65 |
| Redis | Included | ElastiCache cache.t3.micro | ~$15 |
| Load Balancer | N/A | ALB | ~$25 |
| SSL | Free (Certbot) | Free (ACM) | $0 |
| DNS | External | Route 53 | ~$1 |
| Object Storage | B2 (~$5) | S3 | ~$5 |
| Monitoring | Free | CloudWatch | ~$10-30 |
| Data Transfer | 20 TB included | Pay per GB | ~$10-50 |
| **Total** | **~$15-20/mo** | | **~$200-400/mo** |

### 10.5 When to Migrate

Consider AWS migration when:
- **Scale:** More than 1,000 tenant organizations
- **Compliance:** Need SOC 2, HIPAA, or PCI compliance certifications
- **Reliability:** Need 99.99% uptime SLA with multi-AZ
- **Team:** Multiple developers need managed CI/CD and infrastructure-as-code
- **Global:** Need to serve users in multiple geographic regions (multi-region)

Stay on Hetzner when:
- Under 1,000 organizations
- Single-region deployment is sufficient
- Cost efficiency is a priority
- The team is comfortable managing Docker Compose
- Current uptime meets business requirements

---

## 11. Operational Notes

This section covers important implementation details and conventions that affect day-to-day operations. These reflect the current production behavior as of April 2026.

### 11.1 Deployment Commands

```bash
sudo docker compose up -d
sudo docker compose logs -f api
sudo docker compose restart api
```

The repo has a single `docker-compose.yml` (production). Every service loads
`.env.prod`. There is no separate production flag to pass.

**`APP_SECRET`** in `.env.prod` is the field-level encryption key for every
encrypted column in the database (Stripe keys, SMTP passwords, Zoom secrets,
SendGrid keys, Meta/Google Ads tokens, etc.) and for JWT signing. Changing it
invalidates every encrypted credential in the database — don't rotate it
without a re-encryption plan. The API refuses to start if the loaded
`APP_SECRET` doesn't match the committed `APP_SECRET_FINGERPRINT` fingerprint.

**Reclaiming disk space from Docker build cache:**

```bash
sudo docker builder prune -af
```

Docker build cache can grow to many gigabytes over time. Run this periodically (especially after multiple rebuilds) to reclaim disk space. Use `docker system df` to check current usage.

### 11.2 Email: Studio SMTP Primary, Studio SendGrid Fallback

Studio SMTP (Purelymail) is the primary email transport. The studio's own SendGrid is the fallback if SMTP fails. The email service tries SMTP first, and only falls back to SendGrid on SMTP delivery failure. **Platform email (AuraFlow) is NEVER used for tenant emails** -- if the studio's email fails, the email fails.

**Email templates and schedules:**
- Booking confirmations sent immediately on booking
- Daily class reminders sent at **7 AM Pacific**
- Post-class follow-ups sent after class completion
- All email templates use the **studio name** as the sender (never AuraFlow)
- All scheduled times are in **Pacific time** (`America/Los_Angeles`)

**Email inbox features:**
- AI classification with manual **Reclassify** button to override AI categorization

**Important rules:**
- Never send tenant/studio emails from AuraFlow platform accounts (e.g., `hello@auraflow.fit`). Tenant emails must come from the tenant's own configured sender. If studio email fails, the email fails.
- Never use Purelymail for marketing or bulk email. It is for transactional email only.
- Never blast emails or SMS. Always send one at a time with spacing between sends.
- All scheduled email times (reminders, expiration notices, etc.) are in **Pacific time** (`America/Los_Angeles`).

### 11.3 Stripe Direct Mode (Per-Tenant)

A tenant can use Stripe in **direct mode** (not Stripe Connect) — useful when Stripe Connect onboarding is not complete or not desired.

**Key implementation details:**
- The tenant's Stripe API key is passed **per-request** using the `api_key` parameter on each Stripe API call. The global `stripe.api_key` is never mutated.
- The webhook endpoint verifies using the **org-specific webhook signing secret**, not a single global secret. Each tenant can have its own Stripe account and webhook secret.
- Stripe customer IDs, subscription IDs, and payment intent IDs are all scoped to the tenant's Stripe account.

### 11.4 Zoom Integration

Zoom uses **Server-to-Server (S2S) OAuth** -- there is no user-facing OAuth flow. Credentials (Account ID, Client ID, Client Secret) are stored encrypted in the database per-tenant.

**Meeting configuration:**
- All meetings are created as **recurring series (type 8)** with timezone `America/Los_Angeles`.
- **Auto-recording is OFF.** Auto-recording was disabled because it causes audio clicks/pops for participants when the recording starts.
- The Zoom S2S app needs the `meeting:delete` scope added. Without it, meetings cannot be cleaned up when sessions are cancelled. Test deletion on one meeting before enabling bulk operations.

### 11.5 SMS: Twilio A2P 10DLC Compliance

SMS is sent using a **Twilio Messaging Service SID** (not a direct phone number). This is required for A2P 10DLC compliance, which carriers enforce for application-to-person messaging.

**Environment variable:**
```bash
TWILIO_MESSAGING_SERVICE_SID=MG...
```

All phone numbers are normalized to **E.164 format** (`+1XXXXXXXXXX`) before storage and before sending. The SMS service strips formatting and adds the country code if missing.

### 11.6 Private Sessions: Payment Tracking

Private sessions have two independent status fields:
- **`status`** (booking status): `pending`, `confirmed`, `cancelled`, `completed`, `no_show`
- **`payment_status`**: `unpaid` or `paid`

These are separate because a session can be confirmed (booked) but unpaid, or paid but later cancelled.

**Payment links:** When a private session is booked, a Stripe payment link is generated and emailed to the member. The member pays at their convenience. The `payment_url` field on the booking holds this link.

**Payroll:** The payroll service only pays instructors for sessions where `payment_status = 'paid'`. Unpaid sessions are excluded from payroll calculations regardless of booking status.

### 11.7 POS: Send Payment Link and Pending Orders

The POS system supports a **Send Payment Link** option for remote sales. Instead of processing a card in person, the system generates a Stripe Checkout session and emails the payment link to the member. This allows selling products to members who are not physically in the studio.

**Pending Orders tab:** View unpaid orders, resend payment links, or pay in person. Payment methods `send_payment_link`, `stripe`, and `card` all start as **pending** until Stripe confirms payment via webhook. The Stripe webhook marks POS transactions as completed and records them in the transactions table.

Card payments processed in-studio go through Stripe Checkout as well (not Square -- Square integration is planned but not active).

### 11.8 Membership Expiration

The membership expiration Celery task runs daily and auto-expires memberships past their `ends_at` date. However, it **skips members who have an active Stripe subscription**. This prevents incorrectly expiring members whose payment is processing or whose membership renewal is handled by Stripe's subscription lifecycle.

When Stripe sends a webhook for a successful payment on an expired membership, the webhook handler **reactivates** the membership (expired -> active) and extends the end date.

### 11.9 Classes: In-Studio with Optional Hybrid Streaming

All classes are **in-studio** classes. The `is_virtual` flag means the class is **also streamed** via Zoom (hybrid), not that it is online-only. There is no `access_scope` filtering on class bookings -- all members can book any class regardless of their membership's access scope. The access scope distinction only applies to on-demand video library access.

### 11.10 Kiosk Check-In

The kiosk must use the **studio-specific URL**: `/{slug}/dashboard/check-in/kiosk` (e.g., `/your-studio/dashboard/check-in/kiosk`). The generic `/dashboard/check-in/kiosk` URL is **disabled**. The kiosk uses `attended` status (the API uses `attended`, not `checked_in`).

### 11.11 Auth Tokens

- **Access token lifetime:** 4 hours (was previously 60 minutes)
- **Stale refresh tokens** are auto-cleaned on each token refresh and by a daily cleanup task at **5 AM Pacific**
- **Network errors** in the auth interceptor trigger a token refresh attempt; if the refresh also fails, the user is redirected to the login page

### 11.12 Permissions

Per-user permissions set by the owner via **Staff > user > Permissions** are the **FINAL authority**. There is no client-side studio role filtering -- it has been removed entirely. Key permission separations:
- `module.email` is a separate permission from `module.ai`
- `module.payroll` is correctly separated from `module.payments`

### 11.13 Private Session Packages

Services can have **package deals**: `package_sessions` + `package_price_cents` fields define bulk pricing. The **Book as Package** checkbox in the dashboard creates credits on payment. The `payment_status` (`paid`/`unpaid`) is tracked separately from the booking status. Payroll only counts sessions where `payment_status = 'paid'` for instructor compensation.

### 11.14 Membership and Billing Automation

- **Auto-expire task** skips Stripe-managed memberships (prevents incorrectly expiring members whose renewal is handled by Stripe)
- **Webhook** handles expired-to-active reactivation on invoice payment
- **Class pack credits** are restored on non-late cancellations
- **Repeat purchases** add credits to existing packs and always record transactions
- **Waiver** is forced on login for members with unsigned waivers
- **Payment setup** is forced on login for members flagged by admin

### 11.15 Public API Endpoints

- `GET /api/v1/public/{slug}/schedule` -- JSON schedule data (no auth required)
- `GET /api/v1/public/{slug}/schedule.html` -- HTML schedule page for ClassPass embedding
- **API keys** now have a granular scope selector in the dashboard

### 11.16 Zoom Automation

- 15 recurring weekly series configured, auto-recording **OFF**
- **Zoom link sender:** emails the join link 1 hour before virtual/hybrid classes
- **Zoom auto-create:** daily task creates Zoom meetings 3 days ahead of scheduled classes
- All meetings use timezone `America/Los_Angeles`

### 11.17 Scheduled Tasks Summary

| Task | Schedule | Description |
|------|----------|-------------|
| Daily class reminders | 7 AM Pacific | Email reminders for today's classes |
| Token cleanup | 5 AM Pacific | Clean stale refresh tokens |
| Docker cleanup | 9 PM Pacific | `docker system prune` cron job |
| Membership auto-expire | Daily | Expire past-due memberships (skips Stripe-managed) |
| Zoom auto-create | Daily | Create Zoom meetings 3 days ahead |
| Zoom link sender | 1 hour before class | Email join link to booked members |
| Webhook crash alerts | On failure | Email crash alerts to studio owner |

### 11.18 Cloudflare DNS Configuration

- `app.auraflow.fit` and `api.auraflow.fit`: **DNS only** (no orange cloud proxy) -- Cloudflare's JS challenge breaks the React app and API calls
- `auraflow.fit`: can stay proxied for marketing site CDN benefits

---

## 12. Troubleshooting

### Container Will Not Start

```bash
# Check container logs
docker compose -f docker-compose.prod.yml logs api

# Check if .env.prod exists and is readable
ls -la .env.prod

# Verify Docker Compose file is valid
docker compose -f docker-compose.prod.yml config --quiet

# Check if port is already in use
ss -tlnp | grep -E '8000|3000|5432|6379'

# Check available disk space
df -h
```

### 502 Bad Gateway

The Nginx reverse proxy cannot reach the upstream service.

```bash
# Is the API container running?
docker ps | grep auraflow_api

# Can you reach it locally?
curl -sf http://127.0.0.1:8000/health

# Check API container logs
docker compose -f docker-compose.prod.yml logs --tail=50 api

# Check Nginx error log
sudo tail -50 /var/log/nginx/error.log

# Restart the API container
docker compose -f docker-compose.prod.yml restart api
```

### Redis Authentication Error

```
NOAUTH Authentication required
```

or

```
ERR invalid password
```

The Redis password in `.env.prod` does not match the password in the `docker-compose.prod.yml` redis service command.

```bash
# Check the password in docker-compose.prod.yml
grep requirepass docker-compose.prod.yml

# Check the password in .env.prod
grep REDIS .env.prod

# They must match. If they don't:
# 1. Update .env.prod to match docker-compose.prod.yml
# 2. Rebuild and restart
./infra/scripts/deploy.sh build
./infra/scripts/deploy.sh restart
```

### Database Connection Refused

```bash
# Is PostgreSQL running?
docker exec auraflow_postgres pg_isready -U auraflow -d auraflow

# Check PostgreSQL logs
docker compose -f docker-compose.prod.yml logs --tail=50 postgres

# Verify DATABASE_URL in .env.prod
grep DATABASE_URL .env.prod

# Check if the container is healthy
docker inspect --format='{{.State.Health.Status}}' auraflow_postgres

# If postgres data is corrupted, restore from backup (see Section 5.5)
```

### SSL Certificate Expired

```bash
# Check expiry
openssl x509 -enddate -noout -in /etc/letsencrypt/live/auraflow.fit/fullchain.pem

# Renew
sudo certbot renew

# If renewal fails, check DNS
dig +short auraflow.fit
dig +short api.auraflow.fit
dig +short app.auraflow.fit

# Force renewal
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

### Blank Page on Frontend

`NEXT_PUBLIC_*` variables are baked into the Next.js build at build time. If they are wrong or missing, the frontend will render a blank page or fail to connect to the API.

```bash
# Check the build-time variables
grep NEXT_PUBLIC .env.prod

# They must be correct BEFORE building:
NEXT_PUBLIC_API_URL=https://api.auraflow.fit
NEXT_PUBLIC_APP_URL=https://app.auraflow.fit

# Rebuild the web container
docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml up -d web
```

Also check the browser console (F12 > Console) for JavaScript errors.

### CORS Errors

```bash
# Check CORS_ORIGINS in .env.prod
grep CORS_ORIGINS .env.prod

# It should be a JSON array of allowed origins:
CORS_ORIGINS=["https://auraflow.fit","https://api.auraflow.fit","https://app.auraflow.fit"]

# Check Nginx CORS headers (if configured in nginx.conf)
sudo grep -i cors /etc/nginx/nginx.conf

# After fixing, restart:
./infra/scripts/deploy.sh restart
./infra/scripts/deploy.sh nginx
```

### High Memory Usage

```bash
# Check which container is using the most memory
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Current resource limits (from docker-compose.prod.yml):
#   postgres:       2 GB
#   redis:          512 MB (also limited by maxmemory 512mb in Redis config)
#   api:            1 GB
#   web:            512 MB
#   celery_worker:  1 GB
#   celery_beat:    256 MB

# If a container is hitting its limit, increase it in docker-compose.prod.yml:
# deploy:
#   resources:
#     limits:
#       memory: 2G    # Increase this

# Then restart
docker compose -f docker-compose.prod.yml up -d
```

### Celery Tasks Not Running

```bash
# Check if celery_worker is running
docker ps | grep celery

# Check worker logs
docker compose -f docker-compose.prod.yml logs --tail=100 celery_worker

# Check beat logs (for scheduled tasks)
docker compose -f docker-compose.prod.yml logs --tail=100 celery_beat

# Verify Redis connection (Celery uses Redis as broker)
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  ping

# Check queues
docker exec auraflow_redis redis-cli \
  -a f9fa2052c0c510da2fdccfe7fd31c64b4788d500b1bebf31d77f2f22d6fdb801 \
  keys "celery*"

# Restart workers
docker compose -f docker-compose.prod.yml restart celery_worker celery_beat
```

Celery worker processes 5 queues: `default`, `email`, `sms`, `payments`, `video`.

### Alembic Migration Fails

```bash
# Check current migration state
docker compose -f docker-compose.prod.yml exec api alembic current

# Check migration history
docker compose -f docker-compose.prod.yml exec api alembic history --verbose

# If the database is ahead of migrations (manual changes), stamp:
docker compose -f docker-compose.prod.yml exec api alembic stamp head

# If there is a conflict, check the migration files:
# apps/api/alembic/versions/
```

### API Returns 500 Internal Server Error

```bash
# Check API logs for the full traceback
docker compose -f docker-compose.prod.yml logs --tail=200 api | grep -A 20 "Traceback"

# Check Sentry for the error (if configured)
# https://sentry.io/organizations/YOUR_ORG/issues/

# Common causes:
# - Missing environment variable
# - Database connection pool exhausted
# - Redis connection timeout
# - External API key expired or invalid
```

---

## 13. Environment Variable Reference

Complete reference of all environment variables used by the platform.

### App Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | Yes | `development` | Runtime environment: `development`, `staging`, `production` |
| `NODE_ENV` | Yes | `development` | Node.js environment: `development`, `production` |
| `APP_URL` | Yes | -- | Frontend URL (e.g., `https://app.auraflow.fit`) |
| `API_URL` | Yes | -- | Backend API URL (e.g., `https://api.auraflow.fit`) |
| `APP_SECRET` | Yes | -- | Secret key for JWT signing, encryption. Generate: `openssl rand -hex 32` |
| `PLATFORM_NAME` | No | `AuraFlow` | Platform display name |
| `PLATFORM_DOMAIN` | No | `auraflow.fit` | Primary platform domain |
| `CORS_ORIGINS` | Yes | `["http://localhost:3000"]` | JSON array of allowed CORS origins |

### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | -- | PostgreSQL connection string: `postgresql://user:pass@host:port/db` |
| `POSTGRES_PASSWORD` | Yes | -- | PostgreSQL password (used by the postgres Docker container on init) |
| `DATABASE_POOL_SIZE` | No | `20` | asyncpg connection pool size |
| `DATABASE_MAX_OVERFLOW` | No | `40` | Maximum overflow connections beyond pool size |

### Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | Yes | -- | Redis connection string: `redis://:password@host:6379/0` |
| `REDIS_PASSWORD` | Yes | -- | Redis password (must match `--requirepass` in compose) |
| `REDIS_CACHE_TTL` | No | `300` | Default cache TTL in seconds |

### Stripe (Payments)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STRIPE_PUBLISHABLE_KEY` | Yes | -- | Stripe publishable API key (`pk_live_...` or `pk_test_...`) |
| `STRIPE_SECRET_KEY` | Yes | -- | Stripe secret API key (`sk_live_...` or `sk_test_...`) |
| `STRIPE_WEBHOOK_SECRET` | Yes | -- | Stripe webhook signing secret (`whsec_...`) |
| `STRIPE_CONNECT_CLIENT_ID` | No | -- | Stripe Connect platform client ID (`ca_...`) |
| `STRIPE_PLATFORM_FEE_PERCENT` | No | `1.25` | Platform fee percentage on Connect payments |

### SendGrid (Transactional Email)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENDGRID_API_KEY` | No | -- | SendGrid API key (`SG...`). Also configurable via admin dashboard. |
| `SENDGRID_FROM_EMAIL` | No | `hello@auraflow.fit` | Default sender email address |
| `SENDGRID_FROM_NAME` | No | `AuraFlow` | Default sender display name |
| `SENDGRID_WEBHOOK_VERIFICATION_KEY` | No | -- | Webhook verification key for delivery tracking |

### SMTP (Purelymail Primary)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | No | `smtp.purelymail.com` | SMTP server hostname |
| `SMTP_PORT` | No | `587` | SMTP server port |
| `SMTP_USE_TLS` | No | `false` | Use STARTTLS (`false`) vs implicit TLS (`true`) |
| `SMTP_USERNAME` | No | -- | SMTP authentication username |
| `SMTP_PASSWORD` | No | -- | SMTP authentication password |
| `SMTP_FROM_EMAIL` | No | -- | SMTP sender email address |
| `SMTP_FROM_NAME` | No | `AuraFlow` | SMTP sender display name |

### Mux (Video)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MUX_TOKEN_ID` | No | -- | Mux API token ID |
| `MUX_TOKEN_SECRET` | No | -- | Mux API token secret |
| `MUX_WEBHOOK_SECRET` | No | -- | Mux webhook signing secret |
| `MUX_ENV_KEY` | No | -- | Mux environment key (for Mux Player) |

### OpenAI (Speech-to-Text)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | No | -- | OpenAI API key for Whisper STT (`sk-...`) |

### Anthropic (AI)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | -- | Anthropic API key (`sk-ant-...`) |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-6` | Primary model for complex AI tasks |
| `ANTHROPIC_MODEL_FAST` | No | `claude-haiku-4-5-20251001` | Fast model for quick AI tasks |
| `ANTHROPIC_MAX_TOKENS` | No | `4096` | Maximum tokens per AI response |

### Backblaze B2 (Object Storage)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `B2_ACCOUNT_ID` | No | -- | Backblaze B2 key ID |
| `B2_APPLICATION_KEY` | No | -- | Backblaze B2 application key |
| `B2_BUCKET_BACKUPS` | No | `auraflow-backups` | Bucket name for database/file backups |
| `B2_BUCKET_ASSETS` | No | `auraflow-assets` | Bucket name for user-uploaded assets |
| `B2_ENDPOINT` | No | `https://s3.us-west-002.backblazeb2.com` | S3-compatible endpoint URL |

### Twilio (SMS)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TWILIO_ACCOUNT_SID` | No | -- | Twilio Account SID (`AC...`) |
| `TWILIO_AUTH_TOKEN` | No | -- | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | No | -- | Twilio phone number in E.164 format (`+1XXXXXXXXXX`) |
| `TWILIO_MESSAGING_SERVICE_SID` | No | -- | Twilio Messaging Service SID for A2P 10DLC compliance (`MG...`) |

### Square (POS)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_SQUARE_APPLICATION_ID` | No | -- | Square Application ID. **Build-time variable.** |
| `NEXT_PUBLIC_SQUARE_LOCATION_ID` | No | -- | Square Location ID. **Build-time variable.** |
| `NEXT_PUBLIC_SQUARE_ENVIRONMENT` | No | `production` | Square environment: `sandbox` or `production`. **Build-time variable.** |

### Zoom (Livestream)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ZOOM_ACCOUNT_ID` | No | -- | Zoom Server-to-Server OAuth Account ID |
| `ZOOM_CLIENT_ID` | No | -- | Zoom OAuth Client ID |
| `ZOOM_CLIENT_SECRET` | No | -- | Zoom OAuth Client Secret |

### Sentry (Error Monitoring)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN_API` | No | -- | Sentry DSN for the FastAPI backend |
| `SENTRY_DSN_WEB` | No | -- | Sentry DSN for the Next.js frontend |
| `SENTRY_ENVIRONMENT` | No | `production` | Sentry environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.1` | Performance trace sample rate (0.0 to 1.0) |

### Next.js Public

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | Yes | -- | API URL for frontend fetch calls. **Build-time variable.** |
| `NEXT_PUBLIC_APP_URL` | Yes | -- | App URL for frontend self-references. **Build-time variable.** |

### Feature Flags

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FEATURE_FLAGS_CACHE_TTL` | No | `300` | Redis cache TTL for feature flags in seconds |

### Logging

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_LEVEL` | No | `WARNING` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `LOG_FORMAT` | No | `json` | Log output format: `json` (structured) or `text` (human-readable) |

### Airflow (Workflows -- Future)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AIRFLOW__CORE__FERNET_KEY` | No | -- | Fernet key for Airflow encryption. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | No | -- | Airflow webserver session secret key |

---

## Appendix: Docker Service Summary

| Service | Container Name | Image | Ports (Host) | Memory Limit | CPU Limit | Health Check |
|---------|---------------|-------|--------------|--------------|-----------|--------------|
| postgres | `auraflow_postgres` | `postgres:16-alpine` | 127.0.0.1:5432 | 2 GB | 2.0 | `pg_isready` |
| redis | `auraflow_redis` | `redis:7-alpine` | 127.0.0.1:6379 | 512 MB | 0.5 | `redis-cli ping` |
| api | `auraflow_api` | Built from `apps/api/Dockerfile` | 127.0.0.1:8000 | 1 GB | 2.0 | `curl http://localhost:8000/health` |
| web | `auraflow_web` | Built from `apps/web/Dockerfile` | 127.0.0.1:3000 | 512 MB | 1.0 | `wget http://localhost:3000/` |
| celery_worker | `auraflow_celery_worker` | Built from `apps/api/Dockerfile` | None | 1 GB | 1.0 | None |
| celery_beat | `auraflow_celery_beat` | Built from `apps/api/Dockerfile` | None | 256 MB | 0.25 | None |

All services are on the `auraflow_network` bridge network. PostgreSQL and Redis ports are bound to `127.0.0.1` only (not exposed to the internet). Nginx on the host reverse-proxies HTTPS traffic to the API (port 8000) and Web (port 3000) containers.

---

## Appendix: Deploy Script Reference

```bash
./infra/scripts/deploy.sh full      # Build + restart + nginx + migrate + status
./infra/scripts/deploy.sh build     # Build Docker images only (parallel)
./infra/scripts/deploy.sh restart   # Stop and start all services
./infra/scripts/deploy.sh nginx     # Copy nginx config and reload
./infra/scripts/deploy.sh status    # Check health of all services + SSL
./infra/scripts/deploy.sh migrate   # Run alembic upgrade head
```

---

## Appendix: Key File Paths

| Path | Description |
|------|-------------|
| `/opt/auraflow/` | Production deployment root (on VPS) |
| `/opt/auraflow/.env.prod` | Production environment variables |
| `/opt/auraflow/docker-compose.prod.yml` | Production Docker Compose file |
| `/opt/auraflow/infra/scripts/deploy.sh` | Deployment script |
| `/opt/auraflow/infra/scripts/backup.sh` | Automated backup script |
| `/opt/auraflow/infra/scripts/setup-vps.sh` | VPS initial setup script |
| `/opt/auraflow/infra/nginx/nginx.prod.conf` | Nginx configuration |
| `/etc/nginx/nginx.conf` | Active Nginx config (copied from above) |
| `/etc/letsencrypt/live/auraflow.fit/` | SSL certificate files |
| `/var/log/auraflow-backup.log` | Backup script log |
| `/tmp/auraflow-backups/` | Temporary local backup storage |
