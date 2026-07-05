"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  Search,
  ChevronRight,
  ChevronDown,
  Menu,
  X,
  BookOpen,
  Calendar,
  Users,
  CreditCard,
  Video,
  Brain,
  MapPin,
  BarChart3,
  Clock,
  ShieldCheck,
  UserCog,
  Megaphone,
  ShoppingBag,
  Package,
  Building,
  Bot,
  Plug,
  Settings,
  Mic,
  GraduationCap,
  HelpCircle,
  Gift,
  Mail,
  UserCheck,
  Sparkles,
  Shield,
  Globe,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Tip / Note callout component                                      */
/* ------------------------------------------------------------------ */
function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-4 rounded-lg border-l-4 border-blue-500 bg-blue-50 p-4">
      <p className="text-sm leading-relaxed text-blue-800">{children}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Numbered step component                                           */
/* ------------------------------------------------------------------ */
function Step({
  num,
  title,
  children,
}: {
  num: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="my-4 flex gap-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
        {num}
      </div>
      <div className="flex-1">
        <p className="font-semibold text-gray-800">{title}</p>
        <div className="mt-1 text-gray-600 leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section data                                                       */
/* ------------------------------------------------------------------ */
interface Section {
  id: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  render: () => React.ReactNode;
}

const SECTIONS: Section[] = [
  /* ================================================================ */
  /*  1 — Getting Started                                             */
  /* ================================================================ */
  {
    id: "getting-started",
    title: "Getting Started",
    icon: BookOpen,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Creating Your Studio Account
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Visit the AuraFlow signup page and choose a plan that fits your studio.
          Enter your studio details — name, address, timezone, and the type of
          classes you offer — then create your owner account with your email and
          a secure password. Once registered you are guided through a setup
          checklist that helps you configure your studio step by step.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Setup Checklist Walkthrough
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          After your first login you land on the dashboard with a setup checklist
          guiding you through initial configuration. The checklist covers: studio
          profile (name, logo, timezone, address), adding staff and assigning roles,
          creating membership types and pricing, building your class schedule,
          importing or adding existing members, connecting Stripe for payment
          processing, and configuring your member portal.
        </p>

        <Step num={1} title="Upload your logo and complete your studio profile">
          <p>
            Navigate to <strong>Settings &gt; Studio</strong>. Upload a PNG or
            SVG logo at least 400px wide. Set your timezone, physical address,
            and business hours. Your timezone controls how class times display
            everywhere in the platform.
          </p>
        </Step>
        <Step num={2} title="Add staff and assign roles">
          <p>
            Go to <strong>People &gt; Staff</strong> and invite your team. Assign
            each person a role: Owner, Admin, Instructor, or Front Desk. Each
            role determines what pages, data, and actions that person can access.
          </p>
        </Step>
        <Step num={3} title="Create membership types">
          <p>
            Open <strong>Business &gt; Memberships</strong> and set up your
            pricing plans: unlimited monthly, class packs, drop-in rates, and
            intro offers.
          </p>
        </Step>
        <Step num={4} title="Build your class schedule">
          <p>
            Navigate to <strong>Operations &gt; Schedule</strong> and create your
            recurring weekly classes. Assign instructors, set capacity, and
            enable waitlists.
          </p>
        </Step>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Connecting Payments (Stripe)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Go to <strong>Settings &gt; Billing</strong> or follow the setup
          checklist prompt to connect your Stripe account. You will be redirected
          to Stripe&apos;s onboarding flow where you enter your business
          information, bank account details, and verify your identity. Once
          connected, AuraFlow can charge credit cards, debit cards, and ACH
          transfers. Funds are deposited into your bank on Stripe&apos;s standard
          payout schedule (typically two business days).
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Connecting Email (Settings &gt; Communications)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Settings &gt; Communications</strong> to configure
          outbound email delivery via SendGrid and SMS via Twilio. Set up booking
          confirmations, cancellation notices, class reminders, membership expiry
          alerts, and payment receipts. Templates are customizable with merge
          fields like <code>{"{{member_name}}"}</code> and{" "}
          <code>{"{{class_name}}"}</code>. You can also set the default
          &quot;from&quot; name and reply-to address for all outgoing messages.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Connecting Your Email Inbox (Settings &gt; Email Inbox)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The Email Inbox feature lets AuraFlow receive and process incoming
          emails from members. Go to <strong>Settings &gt; Email Inbox</strong>{" "}
          to connect your studio email account. Once connected, the AI Email
          Inbox can act as a first-responder, classifying incoming messages,
          drafting replies, and escalating complex issues to staff. See the AI
          Features section for more details.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Importing Existing Data (Settings &gt; Import)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          If you are migrating from another platform, go to{" "}
          <strong>Settings &gt; Import</strong> to upload your existing data.
          AuraFlow supports CSV file imports with a flexible column-mapping tool.
          Dedicated importers exist for MindBody and MomoYoga platform
          migrations with pre-configured column mapping. All imports are
          validated before processing with a preview step that flags duplicates
          and missing required fields.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Getting Help
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          If you get stuck at any point, use the AI assistant chatbot (the chat
          bubble icon in the bottom-right corner of your dashboard) to ask
          questions in plain English. The assistant understands your studio data
          and can answer questions like &quot;How many members checked in last
          week?&quot; or help you navigate to the right page. You can also email
          our support team at support@auraflow.fit or browse the FAQ section of
          this documentation site.
        </p>

        <Tip>
          Use the keyboard shortcut <strong>Ctrl + K</strong> (or{" "}
          <strong>Cmd + K</strong> on Mac) anywhere in AuraFlow to open the
          command palette. You can quickly jump to any page, search for a member,
          or trigger common actions without touching the mouse.
        </Tip>
      </>
    ),
  },

  /* ================================================================ */
  /*  2 — Operations                                                   */
  /* ================================================================ */
  {
    id: "operations",
    title: "Operations",
    icon: Calendar,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Dashboard Overview and KPIs
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The dashboard is your command center. KPI tiles at the top show
          today&apos;s revenue, active memberships, classes scheduled today,
          check-ins so far, and your current member retention rate. Each tile is
          clickable and takes you to the detailed report. Below the KPIs you
          will find a calendar widget for today&apos;s schedule, a recent
          activity feed (latest check-ins, bookings, payments, sign-ups), and an
          at-risk members panel powered by AI churn risk scoring.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Voice Check-In Setup and Usage
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Voice check-in uses OpenAI Whisper speech-to-text to let members check
          in by saying their name at the front desk. Navigate to{" "}
          <strong>Operations &gt; Check-In</strong> and click the microphone
          button (or press and hold the spacebar). Say the member&apos;s name
          clearly. AuraFlow transcribes the audio, matches it against your member
          database, and displays the top matches. Click the correct member to
          confirm the check-in. If the member is registered for a class starting
          soon, the check-in is automatically associated with that class.
        </p>

        <Tip>
          Voice check-in requires microphone access in your browser. The first
          time you use it, click &quot;Allow&quot; when your browser asks for
          permission.
        </Tip>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Kiosk Mode
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Every studio gets its own kiosk URL at{" "}
          <code>/&lt;your-studio-slug&gt;/kiosk</code> — a locked-down,
          full-screen check-in station designed for a tablet at the front
          door. The kiosk runs the voice check-in flow, supports manual name
          search, and can sell drop-ins on the spot. Because the URL is
          studio-specific, you can bookmark it on the home screen of a
          dedicated tablet and members can self-check-in without staff
          involvement.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Manual Check-In and Walk-Ins
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          For each class, open the attendance roster and click the check-in
          button next to a member&apos;s name. Walk-ins who arrive without a
          booking can be added on the spot — search for their name or create a
          new member profile. You can sell them a drop-in pass or membership
          right from the check-in screen.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Managing Your Class Schedule
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Operations &gt; Schedule</strong> to view and manage
          your weekly class calendar. Create one-time or recurring sessions, assign
          instructors, set capacity, enable waitlists, and configure
          auto-cancellation thresholds. The calendar supports day, week, and month
          views. Drag-and-drop rescheduling is supported in the week view —
          drag any class block to a different time slot and AuraFlow will prompt
          you to confirm and optionally notify registered members.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Creating Recurring Series
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Most studios run the same classes weekly. Toggle the{" "}
          <strong>Recurring</strong> switch when creating a class and choose
          daily, weekly (select which days), or bi-weekly. Set an end date or
          choose &quot;No end date&quot; for indefinite recurrence. AuraFlow
          generates all future class instances automatically. When editing a
          recurring class, you can change &quot;This class only&quot;, &quot;This
          and future classes&quot;, or &quot;All classes in this series.&quot;
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Waitlist Management
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          When a class reaches full capacity, a waitlist activates automatically.
          Members who join are placed in order. If a booked member cancels, the
          first person on the waitlist is auto-promoted and notified via email and
          SMS (if enabled). You control the auto-promotion window — for example,
          only auto-promote if the cancellation happens at least two hours before
          class. Outside that window, staff can manually promote from the class
          detail page. AuraFlow also offers AI-powered waitlist triage that
          prioritizes members based on membership tier, attendance loyalty, churn
          risk, and time since last visit.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Class Categories and Filtering
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Organize classes with categories (Yoga, Pilates, Fitness, Meditation)
          and tags (Beginner, Hot, Prenatal, 45-minute). Members can filter
          classes by category and tag on the member portal. Sessions can also be
          filtered by instructor or studio location on the staff calendar.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Attendance Tracking
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Every check-in is recorded with a timestamp and associated class. View
          attendance from multiple angles: per class, per member, per instructor,
          or per time period. Late cancellations and no-shows are tracked
          separately. AuraFlow can enforce late cancellation policies
          automatically — for example, deducting a class pack credit or
          charging a fee for cancellations within your configured window.
        </p>
      </>
    ),
  },

  /* ================================================================ */
  /*  3 — Classes & Content                                            */
  /* ================================================================ */
  {
    id: "classes-content",
    title: "Classes & Content",
    icon: GraduationCap,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Private Session Services and Booking
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Private sessions handle one-on-one or small-group appointments. Go to{" "}
          <strong>Classes &amp; Content &gt; Private Sessions</strong> to manage
          service types and bookings. Create service types with a name (e.g.,
          &quot;Private Yoga Session&quot;), duration, price, and which
          instructors can offer it. Each instructor sets their own availability
          windows for private sessions. Staff can book on behalf of members, or
          members can self-book through the portal. Session notes let
          instructors track client progress over time.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Creating Workshops, Teacher Trainings, and Retreats
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Classes &amp; Content &gt; Workshops</strong> to
          create multi-session events. Unlike regular drop-in classes, courses
          have fixed enrollment — the same group of students attends every
          session. Examples include a 6-week beginner series, a weekend arm
          balances workshop, or a 200-hour yoga teacher training. For each course
          you define the sessions (date, time, duration, room), enrollment
          capacity, pricing (with optional early-bird discounts and payment
          plans), and minimum attendance requirements for completion. AuraFlow
          tracks progress, attendance across sessions, and can generate digital
          completion certificates.
        </p>

        <Tip>
          Courses and workshops are one of the highest-margin revenue streams for
          studios. Consider offering at least one workshop per month and a
          multi-week series each quarter to diversify your income beyond monthly
          memberships.
        </Tip>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Managing the Video Library
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Classes &amp; Content &gt; Video</strong> to manage
          your on-demand content library. Upload video files directly (MP4, MOV,
          WebM) or link YouTube URLs. Videos are processed through Mux for
          adaptive streaming. For each video, add a title, description,
          instructor, duration, difficulty level, and thumbnail. Organize videos
          into categories and tags. Control access by membership type — for
          example, restrict premium masterclass recordings to unlimited members
          only.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Video Analytics
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Track total views, unique viewers, average watch duration, completion
          rates, and most popular videos. Identify which members are most engaged
          with your digital offerings and which videos are underperforming to
          guide your content strategy.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Course Enrollment Management
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Members can enroll in courses through the member portal or staff can
          enroll them manually. Payment is collected at enrollment time, either
          in full or via a payment plan. The enrollment count and waitlist are
          tracked on the course page. Set enrollment deadlines to prevent late
          joiners. Communicate with all enrolled students from the course page
          using the <strong>Message Students</strong> button. Set up automated
          session reminders with the topic and what to bring.
        </p>
      </>
    ),
  },

  /* ================================================================ */
  /*  4 — People                                                       */
  /* ================================================================ */
  {
    id: "people",
    title: "People",
    icon: Users,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Adding and Managing Members
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>People &gt; Members</strong> to view your full
          member list with search, filtering, and sorting. Click{" "}
          <strong>+ Add Member</strong> to add someone manually with their name,
          email, phone, emergency contact, and notes. AuraFlow sends a welcome
          email with a link to set their password and access the member portal.
          The member list supports powerful filtering: by membership status
          (active, expired, none), membership type, tags, join date, and last
          visit date. Combine filters for precise segments and save them as
          presets.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Member Profiles
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Click any member&apos;s name to open their full profile with tabs for:
          <strong> Overview</strong> (contact info, membership status, lifetime
          value, quick stats), <strong>Attendance</strong> (complete history with
          dates and instructors), <strong>Billing</strong> (payments, invoices,
          credits), <strong>Memberships</strong> (current and past),{" "}
          <strong>Notes</strong> (internal staff notes), and{" "}
          <strong>Activity</strong> (a timeline of all actions). Tags are colored
          labels for easy identification — common examples include
          &quot;VIP&quot;, &quot;New Member&quot;, and &quot;Requires
          Modification.&quot;
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Member Insights and AI Analysis
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          AuraFlow&apos;s AI continuously analyzes member behavior patterns
          including attendance frequency, booking trends, cancellations, and
          membership status. Each member receives an AI-generated churn risk
          score from 0 to 100. High-risk members appear on your dashboard&apos;s
          at-risk panel with recommended retention actions — such as sending a
          personalized check-in email, offering a complimentary session, or
          scheduling a call. The AI also generates periodic insight reports
          highlighting trends (e.g., &quot;Members who attend both yoga and
          pilates have 35% higher retention&quot;).
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Merging Duplicate Profiles
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          If the same person has two profiles (common after CSV imports), open
          one profile, click the three-dot menu, and select{" "}
          <strong>Merge with another member</strong>. AuraFlow shows a
          side-by-side comparison and lets you choose which details, memberships,
          and records to keep.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Instructor Profiles and Availability
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>People &gt; Instructors</strong> to manage teaching
          staff. Each instructor profile includes their bio, certifications,
          specialties, profile photo (displayed on the member portal), pay rates,
          and performance metrics (average attendance, class count, member
          ratings). Instructors set their weekly availability, which AuraFlow
          uses when assigning classes and private sessions. The Sub-Finder
          feature automatically contacts available substitutes when an instructor
          calls out sick. Instructors can submit time-off requests for admin
          approval.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Staff Roles and Permissions
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>People &gt; Staff</strong> to manage all staff
          members. AuraFlow uses a role-based access control system with four
          roles: <strong>Owner</strong> (unrestricted access including billing
          and account deletion), <strong>Admin</strong> (everything except billing
          settings and account deletion), <strong>Instructor</strong> (own
          schedule, class rosters, performance reports), and{" "}
          <strong>Front Desk</strong> (check-ins, member search, walk-in
          payments). Each role ships with a sensible default permission set.
        </p>
        <p className="mt-2 text-gray-600 leading-relaxed">
          On top of role defaults, the owner can toggle{" "}
          <strong>granular per-user permissions</strong> from any staff
          member&apos;s <strong>Permissions</strong> tab. These per-user settings
          are the <strong>final authority</strong> — if the owner grants or
          removes a module for an individual, that choice overrides the role
          baseline. This lets you hand out specific capabilities
          (Payroll, Email Inbox, AI Assistant, Integrations, etc.) to a single
          instructor or front desk staffer without promoting them to admin. Each
          sidebar module has its own permission key, including{" "}
          <code>module.email</code> (Email Inbox) which is separate from{" "}
          <code>module.ai</code> (AI Assistant) so you can grant one without the
          other.
        </p>

        <Tip>
          Instructors&apos; profiles are public-facing on the member portal. A
          well-written bio with a professional photo helps members connect with
          your teachers and choose the right class.
        </Tip>
      </>
    ),
  },

  /* ================================================================ */
  /*  5 — Business                                                     */
  /* ================================================================ */
  {
    id: "business",
    title: "Business",
    icon: CreditCard,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Membership Types and Plans
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Business &gt; Memberships</strong> to create and
          manage your pricing plans. AuraFlow supports three fundamental types:{" "}
          <strong>Unlimited</strong> (access to as many classes as they want
          during the billing period), <strong>Class Pack</strong> (a fixed number
          of class credits), and <strong>Drop-In</strong> (single-visit pass).
          Create as many types as you need — for example, Unlimited Monthly,
          10-Class Pack, Student Unlimited, and Day Pass. Each type has a name,
          price, billing cycle, access rules (which class categories it covers),
          optional signup fee, and auto-renew settings.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Intro Offers and Tiered Pricing
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Create intro offers like &quot;2 Weeks Unlimited for $39&quot; as
          non-renewing memberships restricted to first-time members. Set up
          tiered pricing to reward longer commitments (e.g., $149/month
          no-commitment vs. $129/month paid annually). Tiered options display
          side by side on the member portal. Student discounts, senior
          discounts, and family plans are created as separate membership types
          with adjusted pricing.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Payment Processing and Stripe Connect
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          All payments are processed through Stripe. Navigate to{" "}
          <strong>Business &gt; Payments</strong> to view all transactions:
          membership charges, drop-in fees, retail purchases, course enrollment,
          and manual charges. Filter by date range, status, membership type, or
          payment method. Issue full or partial refunds, or offer studio credits
          instead. Recurring memberships are billed automatically — AuraFlow
          sends payment reminders three days before each billing date and
          handles failed payment retries (configurable under Settings &gt;
          Billing). Stripe Connect enables marketplace-style revenue splitting
          for guest instructors who receive their share directly.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Point of Sale Operations
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Business &gt; Point of Sale</strong> for a full POS
          system to sell merchandise, water, mats, props, and other products at
          your front desk. Features include a product catalog, barcode scanning,
          discount codes, and sales reporting. Integrates with Stripe for
          payments and supports walk-in purchases. Member purchases are linked
          to their profiles for complete spending history.
        </p>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Payment methods include <strong>cash</strong>,{" "}
          <strong>card</strong> (in-person Stripe checkout),{" "}
          <strong>send payment link</strong> (emails a Stripe checkout link to
          the member),{" "}
          <strong>comp</strong> (free), and <strong>check</strong>. Card and
          payment-link transactions start as <em>pending</em> and only flip to{" "}
          <em>completed</em> when Stripe confirms the charge via webhook — the
          sale is also recorded in <strong>Payments</strong> at that point.
        </p>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Pending Orders Tab
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The <strong>Pending Orders</strong> tab on the POS page lists every
          sale waiting on payment. Each row shows the member, items, total, and
          how long it has been open. Two actions are available:{" "}
          <strong>Resend Link</strong> (generates a fresh Stripe checkout URL and
          emails it again) and <strong>Pay In Person</strong> (opens a card
          reader / in-person checkout flow on the spot). Once the customer pays,
          the transaction moves to Completed automatically.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Inventory Management
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Business &gt; Inventory</strong> to manage product
          stock levels, receive low-stock alerts, and track inventory across
          locations. The AI Office Manager can automatically alert you when items
          need restocking. Each product has a name, SKU, price, cost, and
          current quantity. Stock adjustments are logged with an audit trail.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Gift Cards
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Create and sell gift cards from <strong>Business &gt; Payments &gt;
          Gift Cards</strong>. Gift cards can be emailed directly to recipients
          with a personalized message. Recipients redeem gift cards at checkout
          by entering the gift card code. Balance tracking is automatic — partial
          redemptions are supported. Members can also view and manage their
          gift card balances in the member portal.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Private Sessions and Session Packages
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Operations &gt; Private Sessions</strong> to book
          one-on-one appointments. Members can also purchase{" "}
          <strong>session packages</strong> (e.g. a 5-pack of private yoga
          lessons) — paying upfront unlocks a credit pool that&apos;s decremented
          automatically as each session is booked. Packages are priced once at
          purchase, sessions are tracked against the remaining balance, and the
          package expires based on the schedule you configure. Both individual
          sessions and packages support a <strong>Send Payment Link</strong>{" "}
          flow, so the member can pay by clicking a Stripe link emailed to
          them.
        </p>

        <Tip>
          Studio credits are often a better option than refunds because they keep
          revenue within your business. Consider offering credits for class
          cancellations or service issues instead of cash refunds.
        </Tip>
      </>
    ),
  },

  /* ================================================================ */
  /*  6 — AI Features                                                  */
  /* ================================================================ */
  {
    id: "ai-features",
    title: "AI Features",
    icon: Brain,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          AI Chatbot Assistant
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Accessible from any page via the chat bubble icon in the bottom-right
          corner. The AI assistant understands your studio data and can answer
          questions in plain English: &quot;How many members checked in last
          week?&quot;, &quot;What was my revenue in February?&quot;, &quot;Which
          class has the highest attendance?&quot;. It can look up member records,
          navigate you to the right page, and provide actionable business
          insights. Staff see different capabilities based on their role — owners
          and admins get full data access while instructors see their own class
          data.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          AI Office Manager
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The AI Office Manager at{" "}
          <strong>Insights &gt; AI Assistant &gt; Office Manager</strong> handles
          routine operational tasks automatically. It includes the{" "}
          <strong>Sub-Finder</strong> that contacts available substitute
          instructors when someone calls out sick, prioritizing by availability
          and qualifications. It also provides{" "}
          <strong>inventory alerts</strong> when retail products run low, and
          surfaces scheduling conflicts or coverage gaps. Think of it as a
          virtual assistant that handles the logistics so you can focus on your
          community.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          AI Engagement Autopilot
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The Engagement Autopilot automates personalized outreach to your
          members. It monitors member behavior and triggers actions: welcome
          series for new sign-ups, re-engagement campaigns for declining
          attendance, birthday greetings, milestone celebrations (10th visit,
          1-year anniversary), and win-back sequences for lapsed members. Each
          automation can generate personalized email or SMS content using AI. You
          review and customize the rules, and the system handles execution in the
          background.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          AI Email Inbox (First-Responder)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Once you connect your studio email under{" "}
          <strong>Settings &gt; Email Inbox</strong>, the AI Email Inbox acts as
          a first-responder for incoming messages. It classifies intent (booking
          questions, billing inquiries, schedule changes, sub requests), looks up
          relevant data, drafts responses, and either sends them automatically
          or queues them for staff review based on your confidence threshold.
          Complex issues and complaints are escalated to human staff. All
          resolutions are logged in the{" "}
          <strong>AI Assistant &gt; Inbox</strong> dashboard.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Churn Risk Prediction
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Every active member receives an AI-generated churn risk score from 0
          (very unlikely to leave) to 100 (very likely to leave). The 12-feature
          ML model considers visit frequency trends, days since last visit,
          membership tenure, cancellation patterns, booking behavior, and
          engagement with communications. Members above the risk threshold appear
          on your dashboard with recommended retention actions. The Retention
          Dashboard shows aggregate risk distribution and trends over time.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          AI Content Generation
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The AI can generate marketing emails, social media posts, class
          descriptions, and SMS messages. In any content editor, click{" "}
          <strong>AI Assist</strong> and describe your goal. The AI drafts
          complete content matching your studio&apos;s brand voice. All generated
          content is fully editable before sending.
        </p>

        <Tip>
          The AI learns from your previous campaigns over time. The more you use
          it, the better it gets at matching your studio&apos;s voice and tone.
        </Tip>
      </>
    ),
  },

  /* ================================================================ */
  /*  7 — Integrations                                                 */
  /* ================================================================ */
  {
    id: "integrations",
    title: "Integrations",
    icon: Plug,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          API Keys and External API
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          AuraFlow provides a REST API for building custom integrations. Generate
          API keys under <strong>Settings &gt; Integrations &gt; API
          Keys</strong>. The creator shows a <strong>granular scope
          selector</strong> so you can lock a key down to just the endpoints an
          integration actually needs (members read, bookings write, payments
          read, etc.) instead of granting blanket access. Revoke any key
          instantly — a single revoke invalidates all traffic for that key.
        </p>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The public REST API lives under <code>/api/v1/external/*</code> and
          covers members, classes, schedules, bookings, memberships, payments,
          and attendance. Interactive API documentation is available at your
          AuraFlow subdomain under <code>/api/docs</code>. Staff access tokens
          are valid for <strong>4 hours</strong> with 30-day refresh tokens;
          stale tokens are cleaned up nightly.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          EMR Integration (FHIR R4 and HL7v2)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          AuraFlow supports electronic medical records integration via FHIR R4
          and HL7v2 protocols. This enables healthcare-focused studios,
          rehabilitation centers, and wellness clinics to exchange patient data
          with EMR systems. Configure the integration under{" "}
          <strong>Settings &gt; Integrations</strong>. Supported resources
          include Patient, Appointment, Encounter, and Observation. HL7v2 ADT
          messages (admit/discharge/transfer) are also supported for legacy
          systems.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Mailchimp Sync
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Connect your Mailchimp account under{" "}
          <strong>Settings &gt; Integrations</strong> to automatically sync your
          member list to a Mailchimp audience. New members are added
          automatically, and membership status changes are reflected in Mailchimp
          tags. This lets you use Mailchimp&apos;s advanced email marketing tools
          alongside AuraFlow&apos;s built-in campaigns.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Zoom (Hybrid + Virtual Classes)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Connect a Zoom Server-to-Server OAuth app under{" "}
          <strong>Settings &gt; Integrations &gt; Zoom</strong>. Any class
          session marked <strong>is_virtual</strong> automatically provisions a
          recurring Zoom meeting in the studio&apos;s timezone. Join links are
          emailed to booked members <strong>one hour before class</strong> —
          and only to members whose active membership has digital access
          (online or all-access scope). In-studio-only members never receive
          Zoom links, so you can run hybrid classes without exposing the stream
          to unpaid viewers.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          ClassPass
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Settings &gt; Integrations &gt; ClassPass</strong>{" "}
          to connect your ClassPass partner account. Once connected, your class
          schedule syncs to ClassPass automatically. ClassPass bookings appear in
          AuraFlow alongside regular member bookings, with ClassPass check-ins
          tracked separately in attendance reports. You control which classes are
          listed and how many ClassPass spots per class are available.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          CSV Import/Export
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Import members, class types, and schedules via CSV under{" "}
          <strong>Settings &gt; Import</strong>. Export member lists, attendance
          records, payment history, and analytics data to CSV from any report
          page using the <strong>Export</strong> button. Dedicated importers for
          MindBody and MomoYoga provide pre-configured column mapping for
          seamless migration.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Webhooks
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Configure outgoing webhooks under{" "}
          <strong>Settings &gt; Webhooks</strong>. Select which events trigger
          notifications (member created, payment processed, class booked,
          check-in recorded, etc.) and specify your endpoint URL. AuraFlow POSTs
          a JSON payload for each event. Failed deliveries are retried
          automatically. Combine webhooks with Zapier or Make for no-code
          automations — for example, send a Slack notification when a payment
          fails or add new members to a Google Sheet.
        </p>

        <Tip>
          Webhooks open up countless integration possibilities without writing
          code. The webhook management page includes a testing tool and delivery
          logs for debugging.
        </Tip>
      </>
    ),
  },

  /* ================================================================ */
  /*  8 — Member Portal                                                */
  /* ================================================================ */
  {
    id: "member-portal",
    title: "Member Portal",
    icon: Globe,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Portal Overview for Members
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The member portal is a separate, member-facing interface at{" "}
          <strong>/portal</strong> where your students manage their own studio
          experience. When a member logs in, they see their personal dashboard
          with upcoming bookings, recent attendance, current membership status,
          and account notifications (expiring class packs, upcoming payments).
          The portal is fully mobile-responsive and can be installed as a home
          screen app (PWA) on any phone or tablet.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Booking Classes
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Members browse your full class schedule in a weekly view showing class
          name, instructor, time, duration, and available spots. Filter by
          category, instructor, or day. Click a class and then{" "}
          <strong>Book</strong> to reserve a spot. If full, join the waitlist.
          Confirmation and reminder emails are sent automatically. Members can
          also book private sessions by selecting a service type, instructor,
          and available time slot.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Managing Memberships
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The <strong>My Membership</strong> section shows everything about the
          member&apos;s current plan: type, start date, next billing date, price,
          payment method, and remaining credits for class packs. The{" "}
          <strong>Billing History</strong> sub-section lists every payment with
          downloadable invoices. Members can update their payment method
          (credit card or bank account) at any time without contacting the
          studio. They can also cancel bookings from <strong>My
          Bookings</strong> within the studio&apos;s cancellation window.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Gift Cards
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Members can purchase and redeem gift cards through the portal. They can
          view their gift card balances and apply them at checkout for classes,
          memberships, or retail purchases.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Videos
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The <strong>Video Library</strong> in the portal provides a
          Netflix-style browsing experience. Members see all videos they have
          access to based on their membership type, organized by category with
          search and filter functionality. They can favorite videos, track
          viewing history, and resume where they left off. The video player is
          optimized for all devices including smartphones and tablets.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Workshops, Courses, and Waivers
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Upcoming workshops and multi-session courses are displayed prominently
          on the portal with enrollment and payment handled directly. If your
          studio requires waivers or health forms, members can review and sign
          them digitally through the portal. Members can also manage their
          profile, communication preferences, and security settings.
        </p>

        <Tip>
          Encouraging members to manage their own billing through the portal
          reduces payment-related inquiries at your front desk. Include a link
          to the billing page in your payment reminder emails.
        </Tip>
      </>
    ),
  },

  /* ================================================================ */
  /*  9 — Settings                                                     */
  /* ================================================================ */
  {
    id: "settings",
    title: "Settings",
    icon: Settings,
    render: () => (
      <>
        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Studio Settings
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Navigate to <strong>Settings &gt; Studio</strong> to configure your
          studio name, upload your logo, enter your physical address, set your
          timezone, and define business hours. The studio name and logo appear on
          all member-facing pages, emails, and receipts. The timezone controls
          how class times display throughout the platform.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Locations
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Manage multiple locations under <strong>Settings &gt;
          Locations</strong>. Each location has its own name, address, timezone,
          rooms, and operating hours. Staff can be assigned to one or multiple
          locations. Switch between locations using the dropdown in the
          top-left corner of the sidebar — all KPIs, schedules, and reports
          update to reflect the chosen location. An &quot;All Locations&quot;
          view provides aggregate reporting.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Communications (Email + SMS)
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Under <strong>Settings &gt; Communications</strong>, configure your
          outbound email and SMS (via Twilio) delivery. AuraFlow uses your
          studio&apos;s own SMTP account (Purelymail, Gmail, Google Workspace,
          Microsoft 365, or any provider) as the <strong>primary</strong> email
          sender so every message appears to come from your studio&apos;s
          domain, not from AuraFlow. If SMTP fails, AuraFlow falls back to your
          studio&apos;s SendGrid account if you have one connected. AuraFlow
          never falls back to a platform email for tenant operations — your
          studio&apos;s identity is always preserved.
        </p>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Customize templates for booking confirmations, cancellation notices,
          class reminders, membership renewal alerts, payment receipts, Zoom
          links, and more. Templates support merge fields and show a live
          preview. Set the &quot;from&quot; name, reply-to address, and
          enable/disable individual message types.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Email Inbox Connection
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Connect your studio email under <strong>Settings &gt; Email
          Inbox</strong> to enable the AI Email Inbox first-responder feature.
          AuraFlow receives incoming member emails via IMAP, the AI
          classifies each message (spam, general question, booking inquiry,
          pricing, schedule, engagement reply, complaint, feedback, or
          cancellation), and either auto-replies for simple questions or routes
          the conversation to the <strong>needs attention</strong> queue for
          staff. Staff can <strong>reclassify</strong> any message to override
          the AI&apos;s guess, <strong>assign</strong> the email to any team
          member (including instructors), reply manually, or mark it{" "}
          <strong>resolved</strong>. Access is gated by the{" "}
          <code>module.email</code> permission — separate from the AI Assistant
          permission so you can grant inbox work to front desk without
          exposing the broader AI tools.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Integrations
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The <strong>Integrations</strong> page (accessible from Settings)
          manages all third-party connections: Stripe, ClassPass, Mailchimp,
          EMR/FHIR, Zoom, and API keys. Each integration has its own setup
          wizard and configuration options.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Import/Export
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The <strong>Import</strong> page (accessible from Settings) supports
          CSV imports for members, class types, and schedules. Dedicated
          importers for MindBody and MomoYoga provide pre-configured column
          mapping. Export options are available throughout the platform on
          individual report pages.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Billing and Plans
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Your AuraFlow platform subscription is managed under{" "}
          <strong>Settings &gt; Billing</strong>. View your current plan, next
          billing date, update your payment method, and review invoice history.
          Upgrade or downgrade at any time — changes take effect at the start
          of your next billing cycle. This is also where you connect or manage
          your Stripe account for processing member payments.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Waivers
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Configure digital waivers and liability forms under{" "}
          <strong>Settings &gt; Waivers</strong>. Create custom waiver templates
          that members sign electronically through the portal. Track which
          members have signed and which need to complete their waivers. Require
          waiver completion before class booking if desired.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Webhooks
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Configure outgoing webhook endpoints under{" "}
          <strong>Settings &gt; Webhooks</strong>. Select events, specify
          endpoint URLs, test deliveries, and view delivery logs. See the
          Integrations section for full details.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Audit Log
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          The <strong>Settings &gt; Audit Log</strong> provides a complete
          history of all administrative actions, logins, and security events
          across your account. Every action is timestamped and attributed to the
          user who performed it. Filter by date range, action type, or user.
          This is invaluable for security reviews, compliance, and
          troubleshooting.
        </p>

        <h3 className="mt-6 text-lg font-semibold text-gray-800">
          Account Management
        </h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Under <strong>Settings &gt; Account</strong>, manage your personal
          account settings, change your password, and configure two-factor
          authentication. This is also where account owners can manage account
          cancellation and data export/deletion requests for privacy compliance
          (GDPR, CCPA).
        </p>

        <Tip>
          AuraFlow takes data privacy seriously. All data is encrypted at rest
          and in transit. Schema-per-tenant database isolation ensures your
          studio&apos;s data is completely separate from other businesses. Enable
          two-factor authentication for all staff accounts for an extra layer
          of security.
        </Tip>
      </>
    ),
  },
];

/* ==================================================================== */
/*  Main page component                                                 */
/* ==================================================================== */
export default function DocsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSection, setActiveSection] = useState("getting-started");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  /* ---- Scrollspy via IntersectionObserver ---- */
  useEffect(() => {
    const observers: IntersectionObserver[] = [];

    SECTIONS.forEach((section) => {
      const el = sectionRefs.current[section.id];
      if (!el) return;
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              setActiveSection(section.id);
            }
          });
        },
        { rootMargin: "-80px 0px -60% 0px", threshold: 0 },
      );
      observer.observe(el);
      observers.push(observer);
    });

    return () => observers.forEach((o) => o.disconnect());
  }, []);

  /* ---- Filter sections based on search ---- */
  const filteredSections = searchQuery.trim()
    ? SECTIONS.filter((s) => {
        const q = searchQuery.toLowerCase();
        return s.title.toLowerCase().includes(q);
      })
    : SECTIONS;

  /* ---- Scroll to section ---- */
  const scrollTo = useCallback((id: string) => {
    const el = sectionRefs.current[id];
    if (el) {
      const yOffset = -88; // account for sticky search bar + nav
      const y = el.getBoundingClientRect().top + window.scrollY + yOffset;
      window.scrollTo({ top: y, behavior: "smooth" });
    }
    setMobileMenuOpen(false);
  }, []);

  return (
    <div className="relative">
      {/* ============================================================ */}
      {/*  Sticky search bar                                           */}
      {/* ============================================================ */}
      <div className="sticky top-[57px] z-40 border-b border-gray-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          {/* Mobile menu toggle */}
          <button
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 lg:hidden"
            onClick={() => setMobileMenuOpen((o) => !o)}
            aria-label="Toggle table of contents"
          >
            {mobileMenuOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>

          {/* Search input */}
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search documentation..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-gray-300 py-2 pl-10 pr-4 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
            />
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/*  Mobile sidebar overlay                                       */}
      {/* ============================================================ */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
      <div
        className={`fixed left-0 top-[113px] z-30 h-[calc(100vh-113px)] w-64 overflow-y-auto border-r border-gray-200 bg-white p-4 transition-transform lg:hidden ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <SidebarContent
          sections={filteredSections}
          activeSection={activeSection}
          onNavigate={scrollTo}
        />
      </div>

      {/* ============================================================ */}
      {/*  Desktop layout: sidebar + main content                       */}
      {/* ============================================================ */}
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex gap-8">
          {/* Desktop sidebar */}
          <aside className="sticky top-[113px] hidden h-[calc(100vh-113px)] w-60 shrink-0 overflow-y-auto border-r border-gray-200 py-6 pr-4 lg:block">
            <SidebarContent
              sections={filteredSections}
              activeSection={activeSection}
              onNavigate={scrollTo}
            />
          </aside>

          {/* Main content */}
          <main className="min-w-0 flex-1 py-8">
            <div className="mb-8">
              <h1 className="text-3xl font-bold text-gray-900">
                AuraFlow User Guide
              </h1>
              <p className="mt-2 text-gray-600">
                Everything you need to know to run your studio with AuraFlow.
                Browse the chapters below or use the search bar to find a
                specific topic.
              </p>
            </div>

            {filteredSections.length === 0 && (
              <div className="rounded-lg border border-gray-200 p-8 text-center">
                <HelpCircle className="mx-auto h-10 w-10 text-gray-300" />
                <p className="mt-3 text-gray-500">
                  No sections match &quot;{searchQuery}&quot;. Try a different
                  search term.
                </p>
              </div>
            )}

            {filteredSections.map((section) => {
              const Icon = section.icon;
              return (
                <section
                  key={section.id}
                  id={section.id}
                  ref={(el) => {
                    sectionRefs.current[section.id] = el;
                  }}
                  className="mb-16 scroll-mt-28"
                >
                  <div className="flex items-center gap-3 border-b border-gray-200 pb-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-100">
                      <Icon className="h-5 w-5 text-indigo-600" />
                    </div>
                    <h2 className="text-2xl font-bold text-gray-900">
                      {section.title}
                    </h2>
                  </div>
                  {section.render()}
                </section>
              );
            })}

            {/* Footer */}
            <div className="mt-12 border-t border-gray-200 pt-8 text-center text-sm text-gray-400">
              <p>
                AuraFlow Studio Management Platform &mdash; Documentation
              </p>
              <p className="mt-1">
                Need more help? Use the AI assistant in your dashboard or email{" "}
                <a
                  href="mailto:support@auraflow.fit"
                  className="text-indigo-600 hover:underline"
                >
                  support@auraflow.fit
                </a>
              </p>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

/* ==================================================================== */
/*  Sidebar content (shared between desktop and mobile)                 */
/* ==================================================================== */
function SidebarContent({
  sections,
  activeSection,
  onNavigate,
}: {
  sections: Section[];
  activeSection: string;
  onNavigate: (id: string) => void;
}) {
  return (
    <nav aria-label="Table of contents">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">
        Chapters
      </p>
      <ul className="space-y-0.5">
        {sections.map((section) => {
          const Icon = section.icon;
          const isActive = activeSection === section.id;
          return (
            <li key={section.id}>
              <button
                onClick={() => onNavigate(section.id)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  isActive
                    ? "border-l-[3px] border-indigo-600 bg-indigo-50 font-semibold text-indigo-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-indigo-600" : "text-gray-400"}`} />
                <span className="truncate">{section.title}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
