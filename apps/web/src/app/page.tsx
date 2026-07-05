import Image from "next/image";
import Link from "next/link";
import {
  Calendar,
  Users,
  CreditCard,
  Video,
  Brain,
  ArrowRight,
  BarChart3,
  ShieldCheck,
  UserCog,
  ShoppingBag,
  Package,
  Bot,
  Plug,
  Upload,
  Zap,
  Star,
  Check,
  Lock,
  Mic,
  GraduationCap,
  Gift,
  Mail,
  TrendingDown,
  FileText,
  Globe,
  Heart,
  Activity,
  Send,
  MonitorPlay,
  Bookmark,
  UserCircle,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { PricingTable } from "@/components/marketing/pricing-table";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AuraFlow — AI-Powered Yoga & Fitness Studio Management Software",
  description:
    "The #1 AI-powered studio management platform. Replace MindBody with smarter scheduling, payments, memberships, and AI automation. 14-day free trial.",
  alternates: { canonical: "https://auraflow.fit" },
  openGraph: {
    title: "AuraFlow — AI-Powered Yoga & Fitness Studio Management Software",
    description:
      "The #1 AI-powered studio management platform. Replace MindBody with smarter scheduling, payments, memberships, and AI automation. 14-day free trial.",
    url: "https://auraflow.fit",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AuraFlow — AI-Powered Yoga & Fitness Studio Management Software",
    description:
      "The #1 AI-powered studio management platform. Replace MindBody with smarter scheduling, payments, memberships, and AI automation. 14-day free trial.",
  },
};

/* ── Inline mini-components for the dashboard mockups ──────────────────── */

function MockupWindow({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl ${className}`}>
      {/* Title bar */}
      <div className="flex items-center gap-1.5 border-b border-gray-100 bg-gray-50 px-3 py-2">
        <div className="h-2.5 w-2.5 rounded-full bg-red-400" />
        <div className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
        <div className="h-2.5 w-2.5 rounded-full bg-green-400" />
        <div className="ml-2 h-3 w-40 rounded-full bg-gray-200" />
      </div>
      <div className="flex">
        {/* Mini sidebar */}
        <div className="hidden w-12 flex-shrink-0 border-r border-gray-100 bg-gray-900 py-3 sm:block">
          {[...Array(7)].map((_, i) => (
            <div key={i} className={`mx-auto mb-2 h-5 w-5 rounded ${i === 0 ? "bg-indigo-500" : "bg-gray-700"}`} />
          ))}
        </div>
        {/* Content */}
        <div className="flex-1 p-3">{children}</div>
      </div>
    </div>
  );
}

function ScheduleMockup() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const classes = [
    { day: 0, top: "10%", h: "18%", color: "bg-indigo-400" },
    { day: 1, top: "25%", h: "15%", color: "bg-emerald-400" },
    { day: 1, top: "55%", h: "18%", color: "bg-indigo-400" },
    { day: 2, top: "10%", h: "20%", color: "bg-purple-400" },
    { day: 2, top: "45%", h: "15%", color: "bg-emerald-400" },
    { day: 3, top: "20%", h: "18%", color: "bg-indigo-400" },
    { day: 3, top: "60%", h: "15%", color: "bg-amber-400" },
    { day: 4, top: "10%", h: "15%", color: "bg-emerald-400" },
    { day: 4, top: "40%", h: "20%", color: "bg-purple-400" },
    { day: 5, top: "15%", h: "22%", color: "bg-indigo-400" },
  ];
  return (
    <div>
      {/* Nav */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <div className="h-5 w-12 rounded bg-indigo-100 text-center text-[8px] leading-5 font-medium text-indigo-700">Today</div>
          <div className="h-5 w-5 rounded bg-gray-100" />
          <div className="h-5 w-5 rounded bg-gray-100" />
          <div className="h-3 w-24 rounded bg-gray-200" />
        </div>
        <div className="flex gap-0.5">
          <div className="h-5 w-8 rounded-l bg-indigo-100 text-center text-[7px] leading-5 font-medium text-indigo-700">Day</div>
          <div className="h-5 w-9 rounded-r bg-indigo-500 text-center text-[7px] leading-5 font-medium text-white">Week</div>
        </div>
      </div>
      {/* Grid */}
      <div className="grid grid-cols-7 gap-px rounded-lg border border-gray-200 bg-gray-200 overflow-hidden">
        {days.map((d) => (
          <div key={d} className="bg-gray-50 py-1 text-center text-[8px] font-medium text-gray-500">{d}</div>
        ))}
        {days.map((_, dayIdx) => (
          <div key={dayIdx} className="relative h-32 bg-white">
            {classes
              .filter((c) => c.day === dayIdx)
              .map((c, i) => (
                <div
                  key={i}
                  className={`absolute left-0.5 right-0.5 rounded ${c.color} opacity-80`}
                  style={{ top: c.top, height: c.h }}
                />
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function MembersMockup() {
  const rows = [
    { name: "Sarah Chen", email: "sarah@email.com", visits: "34", status: "Active" },
    { name: "Mike Johnson", email: "mike@email.com", visits: "22", status: "Active" },
    { name: "Ava Williams", email: "ava@email.com", visits: "8", status: "At Risk" },
    { name: "James Brown", email: "james@email.com", visits: "45", status: "Active" },
  ];
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <div className="h-6 flex-1 rounded border border-gray-200 bg-gray-50 px-2 text-[8px] leading-6 text-gray-400">Search members...</div>
        <div className="h-6 rounded bg-indigo-500 px-2 text-[8px] leading-6 font-medium text-white">+ Add</div>
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="grid grid-cols-4 bg-gray-50 px-2 py-1">
          {["Name", "Email", "Visits", "Status"].map((h) => (
            <div key={h} className="text-[7px] font-semibold text-gray-500">{h}</div>
          ))}
        </div>
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-4 border-t border-gray-100 px-2 py-1.5">
            <div className="text-[8px] font-medium text-gray-800">{r.name}</div>
            <div className="text-[8px] text-gray-500">{r.email}</div>
            <div className="text-[8px] text-gray-600">{r.visits}</div>
            <div>
              <span className={`rounded-full px-1.5 py-0.5 text-[7px] font-medium ${r.status === "Active" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>
                {r.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalyticsMockup() {
  const bars = [35, 52, 48, 65, 58, 72, 68, 80, 75, 88, 82, 95];
  return (
    <div>
      {/* KPI row */}
      <div className="mb-3 grid grid-cols-4 gap-2">
        {[
          { label: "Revenue", value: "$12.4k", color: "text-emerald-600" },
          { label: "Members", value: "248", color: "text-indigo-600" },
          { label: "Classes", value: "86", color: "text-purple-600" },
          { label: "Attendance", value: "91%", color: "text-amber-600" },
        ].map((k) => (
          <div key={k.label} className="rounded-lg border border-gray-100 bg-gray-50 p-1.5 text-center">
            <div className={`text-[10px] font-bold ${k.color}`}>{k.value}</div>
            <div className="text-[7px] text-gray-400">{k.label}</div>
          </div>
        ))}
      </div>
      {/* Chart */}
      <div className="rounded-lg border border-gray-100 bg-gray-50 p-2">
        <div className="mb-1 text-[8px] font-medium text-gray-600">Revenue Trend</div>
        <div className="flex h-20 items-end gap-1">
          {bars.map((h, i) => (
            <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-indigo-500 to-purple-400" style={{ height: `${h}%` }} />
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Feature Tour Data ─────────────────────────────────────────────────── */

interface TourFeature {
  icon: LucideIcon;
  title: string;
  desc: string;
}

interface TourCategory {
  id: string;
  label: string;
  color: string;         // tailwind color name (indigo, purple, etc.)
  bgClass: string;       // badge bg
  textClass: string;     // badge text
  iconBg: string;        // icon circle bg gradient from
  dotColor: string;      // icon dot bg
  features: TourFeature[];
}

const TOUR_CATEGORIES: TourCategory[] = [
  {
    id: "operations",
    label: "Operations",
    color: "indigo",
    bgClass: "bg-indigo-50",
    textClass: "text-indigo-700",
    iconBg: "from-indigo-500 to-indigo-600",
    dotColor: "bg-indigo-100 text-indigo-600",
    features: [
      { icon: BarChart3, title: "Smart Dashboard", desc: "Real-time KPIs, revenue metrics, attendance rates, and daily studio overview at a glance." },
      { icon: Mic, title: "Voice Check-In", desc: "Browser-based speech recognition lets members check in hands-free when they arrive." },
      { icon: Calendar, title: "Class Scheduling", desc: "Full calendar with waitlist management, capacity limits, recurring series, and instructor assignment." },
    ],
  },
  {
    id: "classes",
    label: "Classes & Content",
    color: "purple",
    bgClass: "bg-purple-50",
    textClass: "text-purple-700",
    iconBg: "from-purple-500 to-purple-600",
    dotColor: "bg-purple-100 text-purple-600",
    features: [
      { icon: Lock, title: "Private Sessions", desc: "One-on-one and small group bookings with instructor matching, availability, and visibility controls." },
      { icon: GraduationCap, title: "Workshops & Training", desc: "Workshops, teacher trainings, retreats, and multi-session courses with enrollment tracking." },
      { icon: Video, title: "On-Demand Video Library", desc: "Stream classes anytime from YouTube, Mux, and Zoom with member-gated access and view analytics." },
    ],
  },
  {
    id: "people",
    label: "People",
    color: "emerald",
    bgClass: "bg-emerald-50",
    textClass: "text-emerald-700",
    iconBg: "from-emerald-500 to-emerald-600",
    dotColor: "bg-emerald-100 text-emerald-600",
    features: [
      { icon: Users, title: "Member Management", desc: "Full member directory with AI-powered insights, visit history, churn risk scores, and engagement metrics." },
      { icon: UserCog, title: "Instructor Profiles", desc: "Instructor bios, availability calendars, specialties, certifications, and class assignment." },
      { icon: ShieldCheck, title: "Staff Management", desc: "Role-based permissions, time clock, timesheet approval, and granular access controls." },
    ],
  },
  {
    id: "business",
    label: "Business",
    color: "amber",
    bgClass: "bg-amber-50",
    textClass: "text-amber-700",
    iconBg: "from-amber-500 to-amber-600",
    dotColor: "bg-amber-100 text-amber-600",
    features: [
      { icon: CreditCard, title: "Membership Plans", desc: "Flexible plans with auto-renewal, membership freezing, proration, and upgrade/downgrade flows." },
      { icon: Wallet, title: "Payment Processing", desc: "Stripe Connect integration for secure payments, refunds, revenue tracking, and automated billing." },
      { icon: ShoppingBag, title: "Point of Sale", desc: "In-studio retail with product grid, cart, checkout, and daily sales summaries." },
      { icon: Package, title: "Inventory Management", desc: "Track stock levels by SKU with low-stock alerts, reorder points, and auto-deduct on sale." },
      { icon: Gift, title: "Gift Cards", desc: "Purchase, email delivery, balance tracking, and redemption — all built in." },
    ],
  },
  {
    id: "ai",
    label: "AI Features",
    color: "rose",
    bgClass: "bg-rose-50",
    textClass: "text-rose-700",
    iconBg: "from-rose-500 to-pink-600",
    dotColor: "bg-rose-100 text-rose-600",
    features: [
      { icon: Bot, title: "AI Chatbot Assistant", desc: "In-app AI assistant that helps staff navigate features, answer questions, and complete tasks." },
      { icon: Brain, title: "AI Office Manager", desc: "Automated instructor substitution via SMS, inventory monitoring, and operational task handling." },
      { icon: Heart, title: "AI Engagement Autopilot", desc: "Automated member outreach, re-engagement campaigns, and personalized communication at scale." },
      { icon: Mail, title: "AI Email Inbox", desc: "AI first-responder for studio email — drafts replies, categorizes messages, and flags urgent items." },
      { icon: TrendingDown, title: "Churn Risk Prediction", desc: "ML-powered scoring identifies at-risk members before they leave, with automated alert triggers." },
      { icon: FileText, title: "AI Content Generation", desc: "Generate newsletters, marketing copy, social posts, and SMS campaigns with tone and style controls." },
    ],
  },
  {
    id: "integrations",
    label: "Integrations & API",
    color: "sky",
    bgClass: "bg-sky-50",
    textClass: "text-sky-700",
    iconBg: "from-sky-500 to-cyan-600",
    dotColor: "bg-sky-100 text-sky-600",
    features: [
      { icon: Globe, title: "External REST API", desc: "50+ endpoints powering BioAlignPro, MyYogi.ai, and MyYogi Academy integrations." },
      { icon: Activity, title: "EMR Integration", desc: "FHIR R4 and HL7v2 support for healthcare system interoperability and clinical data exchange." },
      { icon: Send, title: "Mailchimp Auto-Sync", desc: "Automatic member list synchronization with Mailchimp for seamless email marketing." },
      { icon: Bookmark, title: "ClassPass Marketplace", desc: "ClassPass integration to list classes on the marketplace and sync bookings automatically." },
      { icon: Upload, title: "CSV Import/Export", desc: "Bulk import and export for members, classes, transactions, and all studio data." },
      { icon: Plug, title: "Platform Connectors", desc: "Stripe Connect, SendGrid, Twilio, and Zoom — all connected from one dashboard." },
    ],
  },
  {
    id: "portal",
    label: "Member Portal",
    color: "violet",
    bgClass: "bg-violet-50",
    textClass: "text-violet-700",
    iconBg: "from-violet-500 to-violet-600",
    dotColor: "bg-violet-100 text-violet-600",
    features: [
      { icon: Calendar, title: "Self-Service Booking", desc: "Members browse the schedule, book classes, join waitlists, and manage reservations on their own." },
      { icon: CreditCard, title: "Membership & Payments", desc: "View plan details, update payment methods, download invoices, and manage billing." },
      { icon: Gift, title: "Gift Card Portal", desc: "Purchase gift cards, send via email, check balances, and redeem — all self-service." },
      { icon: MonitorPlay, title: "On-Demand Video Access", desc: "Stream the full video library based on membership level with progress tracking." },
      { icon: UserCircle, title: "Profile & Notifications", desc: "Update personal info, communication preferences, and notification settings." },
    ],
  },
];


/* ── Page ───────────────────────────────────────────────────────────────── */

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* ── Sticky Nav ─────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-white/10 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-end px-6 py-3">
          <div className="flex items-center gap-5">
            <Link href="/tour" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Tour</Link>
            <Link href="#pricing" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Pricing</Link>
            <Link href="#features" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Features</Link>
            <Link href="/docs" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Docs</Link>
            <Link href="/login" className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors">Log in</Link>
            <Link
              href="/signup"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:bg-indigo-700 hover:shadow-xl hover:shadow-indigo-600/30"
            >
              Start Free Trial
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ───────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-800 px-6 pb-32 pt-20">
        {/* Decorative blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="animate-float absolute -left-40 -top-40 h-96 w-96 rounded-full bg-gradient-to-br from-white/10 to-transparent blur-3xl" />
          <div className="animate-float-delayed absolute -right-20 top-20 h-72 w-72 rounded-full bg-gradient-to-bl from-purple-400/20 to-transparent blur-3xl" />
          <div className="animate-float-slow absolute -bottom-32 left-1/3 h-80 w-80 rounded-full bg-gradient-to-tr from-indigo-400/15 to-transparent blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-7xl">
          <div className="mx-auto max-w-3xl text-center">
            {/* Large brand logo */}
            <div className="mb-10 flex justify-center">
              <div className="rounded-2xl bg-white/95 px-8 py-5 shadow-2xl shadow-black/20 backdrop-blur-sm">
                <Image
                  src="/logo-full.png"
                  alt="AuraFlow — Studio Management Software"
                  width={360}
                  height={103}
                  style={{ width: "auto", height: "auto", maxWidth: 360 }}
                  priority
                />
              </div>
            </div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 text-sm text-white/90 backdrop-blur-sm">
              <Zap className="h-3.5 w-3.5" />
              AI-powered studio management
            </div>
            <h1 className="text-5xl font-extrabold leading-tight tracking-tight text-white sm:text-6xl">
              Run your studio
              <br />
              <span className="bg-gradient-to-r from-white via-indigo-200 to-white bg-clip-text text-transparent">
                like never before
              </span>
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-indigo-100">
              Private sessions, livestream classes, on-demand video, AI-powered
              ad campaigns, POS with inventory, payroll integrations, and 20+
              modules — the all-in-one platform to run and grow your studio.
            </p>
            <div className="mt-10 flex items-center justify-center gap-4">
              <Link
                href="/signup"
                className="group inline-flex items-center gap-2 rounded-xl bg-white px-7 py-3.5 text-sm font-bold text-indigo-700 shadow-xl shadow-black/10 transition-all hover:-translate-y-0.5 hover:shadow-2xl"
              >
                Start Free Trial
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <Link
                href="/tour"
                className="inline-flex items-center gap-2 rounded-xl border border-white/30 bg-white/10 px-7 py-3.5 text-sm font-bold text-white backdrop-blur-sm transition-all hover:bg-white/20"
              >
                Take a Tour
              </Link>
            </div>
            <p className="mt-4 text-xs text-indigo-200/70">
              No credit card required · 14-day free trial · Cancel anytime
            </p>
          </div>

          {/* Dashboard mockup preview */}
          <div className="relative mx-auto mt-16 max-w-4xl">
            <div className="absolute -inset-4 rounded-2xl bg-gradient-to-b from-white/10 to-transparent blur-xl" />
            <MockupWindow className="relative">
              <ScheduleMockup />
            </MockupWindow>
          </div>
        </div>
      </section>


      {/* ── Platform Tour ────────────────────────────────────────────── */}
      <section id="features" className="px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mx-auto max-w-2xl text-center">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-indigo-50 px-4 py-1.5 text-sm font-medium text-indigo-700">
              <Star className="h-3.5 w-3.5" />
              Platform Tour
            </div>
            <h2 className="text-4xl font-extrabold text-gray-900">
              Everything your studio needs
            </h2>
            <p className="mt-4 text-lg text-gray-500">
              Replace MindBody, Mariana Tek, and a dozen other tools with one
              AI-powered platform. 7 categories, 30+ features, zero compromises.
            </p>
          </div>

          {/* Category quick-jump pills */}
          <div className="mt-12 flex flex-wrap items-center justify-center gap-2">
            {TOUR_CATEGORIES.map((cat) => (
              <a
                key={cat.id}
                href={`#tour-${cat.id}`}
                className={`rounded-full ${cat.bgClass} ${cat.textClass} px-4 py-1.5 text-xs font-semibold transition-all hover:shadow-md`}
              >
                {cat.label}
              </a>
            ))}
          </div>

          {/* Category sections */}
          <div className="mt-20 space-y-28">
            {TOUR_CATEGORIES.map((cat, catIdx) => (
              <div key={cat.id} id={`tour-${cat.id}`} className="scroll-mt-24">
                {/* Category header */}
                <div className="mb-10 flex items-center gap-4">
                  <div className={`flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${cat.iconBg} shadow-lg`}>
                    <span className="text-xl font-bold text-white">{cat.label.charAt(0)}</span>
                  </div>
                  <div>
                    <div className={`mb-1 inline-flex items-center gap-1.5 rounded-full ${cat.bgClass} ${cat.textClass} px-3 py-1 text-xs font-semibold uppercase tracking-wider`}>
                      {cat.label}
                    </div>
                    <p className="text-sm text-gray-400">
                      {cat.features.length} feature{cat.features.length !== 1 ? "s" : ""}
                    </p>
                  </div>
                </div>

                {/* Feature cards */}
                <div className={`grid gap-5 ${cat.features.length <= 3 ? "md:grid-cols-2 lg:grid-cols-3" : cat.features.length <= 4 ? "md:grid-cols-2 lg:grid-cols-4" : cat.features.length === 5 ? "md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" : "md:grid-cols-2 lg:grid-cols-3"}`}>
                  {cat.features.map((f) => (
                    <div
                      key={f.title}
                      className="group rounded-2xl border border-gray-100 bg-white p-6 shadow-sm transition-all hover:-translate-y-1 hover:shadow-xl hover:shadow-gray-200/50"
                    >
                      <div className={`mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br ${cat.iconBg} shadow-lg`}>
                        <f.icon className="h-5 w-5 text-white" />
                      </div>
                      <h3 className="text-base font-bold text-gray-900">{f.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-gray-500">{f.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Platform Stats Banner ──────────────────────────────────────── */}
      <section className="overflow-hidden bg-gray-50 px-6 py-16">
        <div className="mx-auto max-w-5xl">
          <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
            {[
              { value: "30+", label: "Features" },
              { value: "7", label: "Categories" },
              { value: "50+", label: "API Endpoints" },
              { value: "6", label: "AI Modules" },
            ].map((s) => (
              <div key={s.label} className="text-center">
                <div className="text-3xl font-extrabold text-indigo-600">{s.value}</div>
                <div className="mt-1 text-sm font-medium text-gray-500">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pricing ────────────────────────────────────────────────────── */}
      <section id="pricing" className="bg-gray-50 px-6 py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-4xl font-extrabold text-gray-900">
              Simple, transparent pricing
            </h2>
            <p className="mt-4 text-lg text-gray-500">
              Start free for 14 days. No credit card required. Cancel anytime.
            </p>
          </div>
          <PricingTable />
        </div>
      </section>

      {/* ── CTA Banner ─────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-700 px-6 py-20">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -right-40 -top-40 h-80 w-80 rounded-full bg-white/10 blur-3xl" />
          <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-purple-400/10 blur-3xl" />
        </div>
        <div className="relative mx-auto max-w-3xl text-center">
          <h2 className="text-4xl font-extrabold text-white">
            Ready to transform your studio?
          </h2>
          <p className="mt-4 text-lg text-indigo-100">
            Join hundreds of studios using AuraFlow to streamline operations,
            grow revenue, and deliver amazing experiences.
          </p>
          <div className="mt-8 flex items-center justify-center gap-4">
            <Link
              href="/signup"
              className="group inline-flex items-center gap-2 rounded-xl bg-white px-8 py-4 text-sm font-bold text-indigo-700 shadow-xl transition-all hover:-translate-y-0.5 hover:shadow-2xl"
            >
              Start Free Trial
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/tour"
              className="inline-flex items-center gap-2 rounded-xl border border-white/30 bg-white/10 px-8 py-4 text-sm font-bold text-white backdrop-blur-sm transition-all hover:bg-white/20"
            >
              See it in action
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-gray-100 bg-white px-6 py-16">
        <div className="mx-auto grid max-w-7xl gap-12 md:grid-cols-5">
          <div>
            <Image src="/logo.png" alt="AuraFlow" width={110} height={32} />
            <p className="mt-3 text-sm text-gray-400">
              The AI-powered studio management platform.
            </p>
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Product</h4>
            <ul className="mt-4 space-y-2">
              <li><Link href="/tour" className="text-sm text-gray-600 hover:text-gray-900">Tour</Link></li>
              <li><Link href="#features" className="text-sm text-gray-600 hover:text-gray-900">Features</Link></li>
              <li><Link href="#pricing" className="text-sm text-gray-600 hover:text-gray-900">Pricing</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Resources</h4>
            <ul className="mt-4 space-y-2">
              <li><Link href="/docs" className="text-sm text-gray-600 hover:text-gray-900">Documentation</Link></li>
              <li><Link href="/docs/faq" className="text-sm text-gray-600 hover:text-gray-900">FAQ</Link></li>
              <li><Link href="/contact" className="text-sm text-gray-600 hover:text-gray-900">Contact Us</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Account</h4>
            <ul className="mt-4 space-y-2">
              <li><Link href="/signup" className="text-sm text-gray-600 hover:text-gray-900">Start Free Trial</Link></li>
              <li><Link href="/login" className="text-sm text-gray-600 hover:text-gray-900">Log in</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400">Legal</h4>
            <ul className="mt-4 space-y-2">
              <li><a href="/privacy" className="text-sm text-gray-400 hover:text-white transition-colors">Privacy Policy</a></li>
              <li><a href="/terms" className="text-sm text-gray-400 hover:text-white transition-colors">Terms of Service</a></li>
            </ul>
          </div>
        </div>
        <div className="mx-auto mt-12 max-w-7xl border-t border-gray-100 pt-8 text-center text-xs text-gray-400">
          &copy; {new Date().getFullYear()} AuraFlow. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
