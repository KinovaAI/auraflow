"use client";

import { useState, useMemo } from "react";
import { Search, ChevronDown, HelpCircle } from "lucide-react";

interface FAQItem {
  question: string;
  answer: string;
  category: string;
}

const FAQ_DATA: FAQItem[] = [
  // ── Getting Started ────────────────────────────────────────────────
  {
    category: "Getting Started",
    question: "How do I create an AuraFlow account for my studio?",
    answer:
      "Visit the AuraFlow signup page and choose the plan that fits your studio. Enter your studio details — name, address, timezone, and type of classes you offer. Create your owner account with your email and a secure password. Once registered, you'll be guided through a setup checklist that helps you configure your class schedule, add staff, import existing members, and connect payments. Your studio is ready to go in minutes.",
  },
  {
    category: "Getting Started",
    question: "I forgot my password. How do I reset it?",
    answer:
      "On the login page, click the \"Forgot Password\" link below the password field. Enter the email address associated with your account and click \"Send Reset Link.\" Check your inbox (and spam/junk folder) for an email from AuraFlow containing a password reset link. Click the link, which is valid for 60 minutes, and create a new secure password.",
  },
  {
    category: "Getting Started",
    question: "How do I connect Stripe for payment processing?",
    answer:
      "Go to Settings > Billing and click \"Connect Stripe Account.\" You'll be redirected to Stripe's onboarding flow where you enter your business information, bank account details, and verify your identity. Once connected, AuraFlow can charge credit cards, debit cards, and ACH bank transfers. Funds are deposited to your connected bank account on Stripe's standard payout schedule (typically two business days).",
  },
  {
    category: "Getting Started",
    question: "How do I connect email and SMS for notifications?",
    answer:
      "Navigate to Settings > Communications to configure outbound email delivery via SendGrid and SMS via Twilio. Set up booking confirmations, cancellation notices, class reminders, membership expiry alerts, and payment receipts. Templates are customizable with merge fields. To enable the AI Email Inbox first-responder, also connect your studio email under Settings > Email Inbox.",
  },
  {
    category: "Getting Started",
    question: "How do I import members from another system?",
    answer:
      "Go to Settings > Import and upload a CSV file. AuraFlow supports flexible column mapping — upload your CSV and map your headers to AuraFlow's fields. Built-in support for MindBody and MomoYoga export formats means the mapping is pre-configured if you're migrating from either platform. The import validates data before processing, flags duplicates, and gives you a summary before finalizing.",
  },
  {
    category: "Getting Started",
    question: "How do I switch between multiple studio locations?",
    answer:
      "Click the location name displayed in the top-left corner of the sidebar. A dropdown appears listing all your studio locations. Select the one you want to switch to, and the entire dashboard updates to show that location's schedule, staff, members, and settings. Each location operates independently with its own data. An \"All Locations\" view provides aggregate reporting.",
  },

  // ── Operations ─────────────────────────────────────────────────────
  {
    category: "Operations",
    question: "How does voice check-in work?",
    answer:
      "Voice check-in uses OpenAI Whisper speech-to-text to make check-in fast and hands-free. On the Check-In page (optimized for a front desk tablet), click the microphone icon or press and hold the spacebar, then say the member's name. AuraFlow transcribes the audio and searches your member database for a match. If found, the member is checked in immediately. Multiple possible matches show a short list to choose from. This is especially useful during busy class transitions.",
  },
  {
    category: "Operations",
    question: "How do I create a new class on the schedule?",
    answer:
      "Go to Schedule and click \"+ New Class.\" Fill in the class details: name, instructor, room, maximum capacity, date, start time, and duration. Toggle \"Recurring\" to create a weekly series. Select the class category for easy filtering. Set waitlist settings and cancellation policy, then save. The class immediately appears on your calendar and is available for member booking.",
  },
  {
    category: "Operations",
    question: "How do waitlists work?",
    answer:
      "Waitlists activate automatically when a class reaches maximum capacity. Members who try to register after that are added in order. When a registered member cancels, the first person on the waitlist is automatically promoted and notified via email and/or SMS. You control the auto-promotion window (e.g., only auto-promote if cancellation is at least 2 hours before class). Staff can also manually promote waitlisted members. AuraFlow offers optional AI-powered waitlist triage that prioritizes by membership tier, loyalty, and churn risk.",
  },
  {
    category: "Operations",
    question: "Can I use AuraFlow on a tablet for front desk check-in?",
    answer:
      "Absolutely! The check-in screen is specifically optimized for tablet use. Set up a tablet at your front desk, open AuraFlow in the browser, and navigate to the check-in screen. For a dedicated kiosk setup, use Check-In > Kiosk Mode — members can search for their own name and tap to check in, and the screen resets automatically. Exit kiosk mode with a staff PIN.",
  },

  // ── Classes & Content ──────────────────────────────────────────────
  {
    category: "Classes & Content",
    question: "How do private sessions work?",
    answer:
      "Private sessions handle one-on-one or small-group appointments. First, create service types under Private Sessions (name, duration, price, eligible instructors). Each instructor sets their availability windows. Staff can book on behalf of members, or members self-book through the portal. After each session, instructors can add progress notes that build a continuous record for any instructor working with that client.",
  },
  {
    category: "Classes & Content",
    question: "How do I create a workshop or teacher training?",
    answer:
      "Navigate to Workshops and click \"+ New Course.\" Enter the name, description, instructor, enrollment capacity, and price. Define each session (date, time, duration, room). For teacher trainings, track required contact hours, set minimum attendance for certification, and configure completion certificates. Enable payment plans for expensive programs. Early-bird pricing can be set with a discounted price and deadline.",
  },
  {
    category: "Classes & Content",
    question: "How do I upload videos to the on-demand library?",
    answer:
      "Navigate to Video and click \"Upload.\" Upload video files directly (MP4, MOV, WebM) or paste a YouTube URL. For each video, add a title, description, category, tags, difficulty level, and thumbnail. Control access by membership type — restrict premium content to unlimited members only, or make some videos public. Videos are processed through Mux for adaptive streaming.",
  },
  {
    category: "Classes & Content",
    question: "How does course enrollment work?",
    answer:
      "Members enroll through the portal or staff can enroll them manually. Payment is collected at enrollment time — either in full or via a payment plan. Enrollment count and waitlist are tracked on the course page. Set enrollment deadlines to prevent late joiners. Communicate with enrolled students using the \"Message Students\" button. AuraFlow tracks attendance across all sessions and can generate completion certificates.",
  },

  // ── People ─────────────────────────────────────────────────────────
  {
    category: "People",
    question: "How do I add a new member?",
    answer:
      "Navigate to Members and click \"Add Member.\" Enter their name, email, phone number, and optional fields like emergency contact and notes. Once saved, they receive a welcome email with a link to set their password and access the member portal. You can optionally assign a membership plan right away.",
  },
  {
    category: "People",
    question: "What are the different user roles and their permissions?",
    answer:
      "AuraFlow uses role-based access control with four staff roles. Owner has full access to everything including billing and account deletion. Admin can do everything except modify billing settings or delete the organization. Instructor can manage their own classes, view their schedule, and access relevant member information. Front Desk handles day-to-day operations like check-in and basic member management. Members have their own portal for booking, videos, and profile management.",
  },
  {
    category: "People",
    question: "How does the AI-powered at-risk member detection work?",
    answer:
      "AuraFlow's AI continuously analyzes member behavior including attendance frequency, booking trends, cancellations, and membership status. When the system detects disengagement (declining visits, multiple cancellations, approaching expiration without renewal), it flags the member as \"at-risk\" with a churn risk score from 0-100. Each flagged member comes with recommended retention actions like sending a personalized email or scheduling a check-in call.",
  },
  {
    category: "People",
    question: "How do I manage instructor availability and substitutes?",
    answer:
      "Each instructor sets their weekly availability under their profile. AuraFlow uses this when assigning classes and private sessions. When an instructor calls out, the AI Sub-Finder automatically contacts available substitutes based on availability and qualifications. Instructors can submit time-off requests for admin approval, and AuraFlow flags classes that need coverage.",
  },

  // ── Business ───────────────────────────────────────────────────────
  {
    category: "Business",
    question: "What types of memberships can I create?",
    answer:
      "AuraFlow supports Unlimited plans (attend any class with no visit limits), Class Packs (prepaid bundles like 10-class or 20-class packs that deduct per check-in), Drop-In (single-visit), and Day Pass (full access for one day). Create custom plans that restrict access to specific class categories. Set up tiered pricing, student discounts, family plans, and intro offers for new members.",
  },
  {
    category: "Business",
    question: "How does payment processing work with Stripe?",
    answer:
      "AuraFlow uses Stripe for secure payment processing. Members can pay by credit or debit card. Recurring memberships are auto-billed through Stripe. View all transactions on the Payments page — successful charges, refunds, and failed payments. Stripe Connect allows each studio to have its own merchant account. Funds are deposited to your connected bank account on Stripe's standard payout schedule.",
  },
  {
    category: "Business",
    question: "How do I use the Point of Sale system?",
    answer:
      "Navigate to Point of Sale for a full POS system for selling merchandise, water, mats, and other products at your front desk. Features include a product catalog, barcode scanning, discount codes, and sales reporting. Integrates with Stripe for payments. Member purchases are linked to their profiles for complete spending history.",
  },
  {
    category: "Business",
    question: "How do gift cards work?",
    answer:
      "Create and sell gift cards from Payments > Gift Cards. Gift cards can be emailed directly to recipients with a personalized message. Recipients redeem them at checkout by entering the gift card code. Partial redemptions are supported with automatic balance tracking. Members can view and manage their gift card balances in the member portal.",
  },
  {
    category: "Business",
    question: "How do I issue a refund?",
    answer:
      "Go to Payments and find the transaction. Click the transaction, then click \"Refund.\" Choose full or partial refund. The refund processes through Stripe and typically appears on the member's statement within 5-10 business days. Alternatively, issue a studio credit instead — credits are stored on the member's account and applied to their next payment.",
  },
  {
    category: "Business",
    question: "How does inventory management work?",
    answer:
      "Navigate to Inventory to manage product stock levels across locations. Each product has a name, SKU, price, cost, and current quantity. Receive low-stock alerts — the AI Office Manager can automatically notify you when items need restocking. Stock adjustments are logged with an audit trail.",
  },

  // ── AI Features ────────────────────────────────────────────────────
  {
    category: "AI Features",
    question: "What can the AI chatbot assistant do?",
    answer:
      "The AI assistant is accessible from any page via the chat bubble icon. Ask questions in plain language: \"What's my revenue this month?\", \"Who are my most active members?\", \"Which classes are most popular on Wednesdays?\" It analyzes your real-time data and provides accurate answers. It can also look up member records, navigate you to the right page, and help with tasks like drafting marketing content. Responses are tailored based on your staff role.",
  },
  {
    category: "AI Features",
    question: "What is the AI Office Manager?",
    answer:
      "The AI Office Manager handles routine operational tasks automatically. It includes the Sub-Finder that contacts available substitute instructors when someone calls out, prioritizing by availability and qualifications. It provides inventory alerts when retail products run low and surfaces scheduling conflicts or coverage gaps. Think of it as a virtual assistant handling logistics.",
  },
  {
    category: "AI Features",
    question: "How does AI Engagement Autopilot work?",
    answer:
      "The Engagement Autopilot automates personalized outreach: welcome series for new sign-ups, re-engagement campaigns for declining attendance, birthday greetings, milestone celebrations (10th visit, 1-year anniversary), and win-back sequences for lapsed members. Each automation generates personalized email or SMS content using AI. You review and customize the rules, and the system handles execution.",
  },
  {
    category: "AI Features",
    question: "What is the AI Email Inbox?",
    answer:
      "Once you connect your studio email under Settings > Email Inbox, the AI acts as a first-responder for incoming messages. It classifies intent (booking questions, billing, schedule changes), looks up relevant data, drafts responses, and either sends them automatically or queues them for staff review. Complex issues and complaints are escalated to human staff. All resolutions are logged and reviewable.",
  },
  {
    category: "AI Features",
    question: "How does churn risk prediction work?",
    answer:
      "Every active member receives an AI-generated churn risk score from 0 (very unlikely to leave) to 100 (very likely to leave). The 12-feature ML model considers visit frequency trends, days since last visit, membership tenure, cancellation patterns, and engagement with communications. High-risk members appear on your dashboard with personalized retention recommendations.",
  },

  // ── Integrations ───────────────────────────────────────────────────
  {
    category: "Integrations",
    question: "How do I connect ClassPass?",
    answer:
      "Go to Settings > Integrations and find ClassPass. Click \"Connect\" and follow the authorization flow. Once connected, your class schedule syncs to ClassPass automatically. ClassPass bookings appear in AuraFlow alongside regular bookings. You control which classes are listed and how many ClassPass spots per class. Revenue from ClassPass is tracked separately in analytics.",
  },
  {
    category: "Integrations",
    question: "What is the EMR integration?",
    answer:
      "AuraFlow supports electronic medical records integration via FHIR R4 and HL7v2 protocols. This enables healthcare-focused studios, rehabilitation centers, and wellness clinics to exchange patient data with EMR systems. Supported FHIR resources include Patient, Appointment, Encounter, and Observation. HL7v2 ADT messages are supported for legacy systems. Configure under Settings > Integrations.",
  },
  {
    category: "Integrations",
    question: "Can I set up custom webhooks?",
    answer:
      "Yes. Go to Settings > Webhooks and click \"Add Endpoint.\" Enter your webhook URL and select events: new bookings, cancellations, payments, member sign-ups, check-ins, and more. Each webhook delivers a JSON payload. Failed deliveries are retried automatically. Combine with Zapier or Make for no-code automations like Slack notifications on failed payments or adding members to Google Sheets.",
  },
  {
    category: "Integrations",
    question: "Does AuraFlow have an API?",
    answer:
      "Yes. AuraFlow provides a REST API with endpoints for members, classes, bookings, payments, and attendance. Generate API keys under Settings > Integrations > API Keys with configurable permissions. API documentation with interactive examples is available at your AuraFlow subdomain under /api/docs.",
  },
  {
    category: "Integrations",
    question: "How does Mailchimp sync work?",
    answer:
      "Connect your Mailchimp account under Settings > Integrations. Your member list syncs automatically to a Mailchimp audience. New members are added, and membership status changes are reflected in Mailchimp tags. This lets you use Mailchimp's advanced email marketing alongside AuraFlow's built-in campaigns.",
  },

  // ── Member Portal ──────────────────────────────────────────────────
  {
    category: "Member Portal",
    question: "How do members book classes?",
    answer:
      "Members log into the portal, browse the schedule by day, week, or month, and filter by class type, instructor, or time. Click \"Book\" on any available class. If full, join the waitlist. Members can also book private sessions by selecting a service, instructor, and time slot. Booking confirmations and reminders are sent via email automatically.",
  },
  {
    category: "Member Portal",
    question: "Can members manage their own billing?",
    answer:
      "Yes. The My Membership section shows their plan type, next billing date, price, and remaining credits. Billing History lists every payment with downloadable invoices. Members can update their payment method (credit card or bank account) at any time without contacting the studio.",
  },
  {
    category: "Member Portal",
    question: "How do members watch on-demand videos?",
    answer:
      "Members navigate to the Video Library in the portal. They see all videos they have access to based on their membership type. Browse by category, search by title or tag, and filter by duration or instructor. Videos stream directly in the browser with standard controls. Members can favorite videos and resume where they left off.",
  },
  {
    category: "Member Portal",
    question: "Is there a mobile app?",
    answer:
      "AuraFlow is built as a Progressive Web App (PWA). It works on all devices through the browser. On mobile, add AuraFlow to your home screen for an app-like experience with a custom icon and full-screen mode. No app store download needed. The interface is fully responsive and optimized for touch.",
  },

  // ── Settings ───────────────────────────────────────────────────────
  {
    category: "Settings",
    question: "How do I configure the audit log?",
    answer:
      "The audit log is always active under Settings > Audit Log. It records all administrative actions, logins, and security events with timestamps and user attribution. Filter by date range, action type, or user. This is invaluable for security reviews, compliance, and troubleshooting. No configuration is needed — it works automatically.",
  },
  {
    category: "Settings",
    question: "How do I set up digital waivers?",
    answer:
      "Go to Settings > Waivers to create custom waiver templates. Members sign them electronically through the portal. Track which members have signed and which need to complete their waivers. Optionally require waiver completion before class booking.",
  },
  {
    category: "Settings",
    question: "How do I manage multiple locations?",
    answer:
      "Under Settings > Locations, each location has its own name, address, timezone, rooms, and hours. Staff can be assigned to one or multiple locations. Switch between locations using the sidebar dropdown. Add a new location by clicking \"+ Add Location\" and filling in the details.",
  },

  // ── Security & Privacy ─────────────────────────────────────────────
  {
    category: "Security & Privacy",
    question: "Is my data secure?",
    answer:
      "All data is encrypted in transit (HTTPS/TLS) and at rest. AuraFlow uses JWT-based authentication with short-lived tokens, role-based access control, and schema-per-tenant database isolation ensuring your studio's data is completely separate from other businesses. Regular security audits follow OWASP best practices. All admin actions are logged in the audit trail.",
  },
  {
    category: "Security & Privacy",
    question: "How is member payment information handled?",
    answer:
      "Payment data is handled entirely by Stripe — AuraFlow never stores credit card numbers. When members enter payment info, it goes directly to Stripe's PCI DSS Level 1 certified infrastructure. AuraFlow only stores a Stripe customer reference ID. Even in a data breach scenario, no payment card data would be exposed.",
  },
  {
    category: "Security & Privacy",
    question: "Can I export or delete my data?",
    answer:
      "Yes. Export member data, payment history, attendance records, and schedules to CSV from their respective pages. For complete data export or deletion (GDPR/CCPA compliance), use Settings > Account or contact support. Data deletion requests are processed promptly with confirmation. Your data belongs to you.",
  },
];

const CATEGORIES = [
  "All",
  "Getting Started",
  "Operations",
  "Classes & Content",
  "People",
  "Business",
  "AI Features",
  "Integrations",
  "Member Portal",
  "Settings",
  "Security & Privacy",
];

export default function FAQPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set());

  const filteredFAQs = useMemo(() => {
    const query = searchQuery.toLowerCase().trim();
    return FAQ_DATA.filter((item) => {
      const matchesCategory =
        activeCategory === "All" || item.category === activeCategory;
      const matchesSearch =
        !query ||
        item.question.toLowerCase().includes(query) ||
        item.answer.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query);
      return matchesCategory && matchesSearch;
    });
  }, [searchQuery, activeCategory]);

  const toggleItem = (index: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const toggleAll = () => {
    if (expandedItems.size === filteredFAQs.length && filteredFAQs.length > 0) {
      setExpandedItems(new Set());
    } else {
      const allIndices = filteredFAQs.map((_, i) => i);
      setExpandedItems(new Set(allIndices));
    }
  };

  const allExpanded =
    filteredFAQs.length > 0 && expandedItems.size === filteredFAQs.length;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:py-12">
      {/* Header */}
      <div className="mb-8 text-center">
        <div className="mb-4 flex items-center justify-center">
          <div className="rounded-full bg-indigo-100 p-3">
            <HelpCircle className="h-8 w-8 text-indigo-600" />
          </div>
        </div>
        <h1 className="mb-2 text-3xl font-bold text-gray-900 sm:text-4xl">
          Frequently Asked Questions
        </h1>
        <p className="text-gray-500">
          Everything you need to know about AuraFlow studio management.
          <br className="hidden sm:inline" /> Can&apos;t find what you&apos;re
          looking for? Reach out to our support team.
        </p>
      </div>

      {/* Search bar */}
      <div className="relative mb-6">
        <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search questions..."
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setExpandedItems(new Set());
          }}
          className="w-full rounded-xl border-2 border-gray-200 py-4 pl-12 pr-4 text-lg text-gray-900 placeholder-gray-400 transition-colors focus:border-indigo-500 focus:outline-none"
        />
      </div>

      {/* Category pills */}
      <div className="mb-6 flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => {
              setActiveCategory(cat);
              setExpandedItems(new Set());
            }}
            className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              activeCategory === cat
                ? "bg-indigo-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {cat}
            {cat !== "All" && (
              <span className="ml-1.5 opacity-70">
                {
                  FAQ_DATA.filter((f) => {
                    if (cat !== f.category) return false;
                    if (!searchQuery.trim()) return true;
                    const q = searchQuery.toLowerCase().trim();
                    return (
                      f.question.toLowerCase().includes(q) ||
                      f.answer.toLowerCase().includes(q)
                    );
                  }).length
                }
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Expand / Collapse All + result count */}
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {filteredFAQs.length === 0
            ? "No results found"
            : `Showing ${filteredFAQs.length} question${filteredFAQs.length !== 1 ? "s" : ""}`}
        </p>
        {filteredFAQs.length > 0 && (
          <button
            onClick={toggleAll}
            className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
          >
            {allExpanded ? "Collapse All" : "Expand All"}
          </button>
        )}
      </div>

      {/* FAQ accordion */}
      <div className="divide-y divide-gray-200 rounded-xl border border-gray-200">
        {filteredFAQs.map((item, idx) => {
          const isOpen = expandedItems.has(idx);
          return (
            <div key={idx}>
              <button
                onClick={() => toggleItem(idx)}
                className="flex w-full items-start gap-4 px-6 py-5 text-left transition-colors hover:bg-gray-50"
              >
                <ChevronDown
                  className={`mt-0.5 h-5 w-5 shrink-0 text-gray-400 transition-transform ${
                    isOpen ? "rotate-180" : ""
                  }`}
                />
                <div className="flex-1">
                  <p className="font-medium text-gray-900">{item.question}</p>
                  <span className="mt-1 inline-block rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500">
                    {item.category}
                  </span>
                </div>
              </button>
              {isOpen && (
                <div className="border-t border-gray-100 bg-gray-50 px-6 py-5 pl-[3.75rem]">
                  <p className="text-gray-600 leading-relaxed">{item.answer}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {filteredFAQs.length === 0 && (
        <div className="mt-8 text-center">
          <HelpCircle className="mx-auto h-12 w-12 text-gray-300" />
          <p className="mt-4 text-gray-500">
            No questions match your search. Try different keywords or{" "}
            <button
              onClick={() => {
                setSearchQuery("");
                setActiveCategory("All");
              }}
              className="text-indigo-600 hover:underline"
            >
              clear your filters
            </button>
            .
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="mt-12 text-center text-sm text-gray-400">
        <p>
          Still have questions? Use the AI assistant in your dashboard or email{" "}
          <a
            href="mailto:support@auraflow.fit"
            className="text-indigo-600 hover:underline"
          >
            support@auraflow.fit
          </a>
        </p>
      </div>
    </div>
  );
}
