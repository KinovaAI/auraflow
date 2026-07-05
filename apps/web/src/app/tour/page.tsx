"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowRight,
  ArrowLeft,
  LayoutDashboard,
  Calendar,
  UserRound,
  BookOpen,
  Users,
  UserCheck,
  Users2,
  Clock,
  Video,
  IdCard,
  Mail,
  CreditCard,
  ShoppingCart,
  Package,
  Building2,
  Sparkles,
  BarChart3,
  Plug,
  Upload,
  Settings,
  Check,
  ChevronRight,
  Play,
} from "lucide-react";

/* ━━━ Types ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

interface TourSection {
  id: string;
  icon: React.ElementType;
  title: string;
  headline: string;
  description: string;
  features: string[];
  mockup: () => React.ReactNode;
  accentFrom: string;
  accentTo: string;
}

/* ━━━ Shared Mockup Shell ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

function MockupShell({
  children,
  activeIdx,
}: {
  children: React.ReactNode;
  activeIdx: number;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl">
      {/* Title bar */}
      <div className="flex items-center gap-1.5 border-b border-gray-100 bg-gray-50 px-3 py-2">
        <div className="h-2.5 w-2.5 rounded-full bg-red-400" />
        <div className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
        <div className="h-2.5 w-2.5 rounded-full bg-green-400" />
        <div className="ml-2 h-3 w-40 rounded-full bg-gray-200" />
      </div>
      <div className="flex">
        {/* Mini sidebar */}
        <div className="hidden w-10 flex-shrink-0 border-r border-gray-100 bg-gray-900 py-2 sm:block">
          {Array.from({ length: 10 }).map((_, i) => (
            <div
              key={i}
              className={`mx-auto mb-1.5 h-4 w-4 rounded ${
                i === activeIdx ? "bg-indigo-500" : "bg-gray-700"
              }`}
            />
          ))}
        </div>
        {/* Content */}
        <div className="flex-1 p-3 sm:p-4">{children}</div>
      </div>
    </div>
  );
}

/* ━━━ Individual Mockups ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

function DashboardMockup() {
  return (
    <MockupShell activeIdx={0}>
      {/* KPI cards */}
      <div className="mb-3 grid grid-cols-4 gap-2">
        {[
          { label: "Revenue", val: "$12.4k", color: "text-emerald-600", bg: "bg-emerald-50" },
          { label: "Members", val: "248", color: "text-indigo-600", bg: "bg-indigo-50" },
          { label: "Classes Today", val: "12", color: "text-purple-600", bg: "bg-purple-50" },
          { label: "Attendance", val: "91%", color: "text-amber-600", bg: "bg-amber-50" },
        ].map((k) => (
          <div key={k.label} className={`rounded-lg border border-gray-100 ${k.bg} p-2 text-center`}>
            <div className={`text-xs font-bold ${k.color}`}>{k.val}</div>
            <div className="text-[7px] text-gray-400">{k.label}</div>
          </div>
        ))}
      </div>
      {/* Today's schedule mini */}
      <div className="mb-3 rounded-lg border border-gray-100 bg-gray-50 p-2">
        <div className="mb-1 text-[8px] font-semibold text-gray-600">Today&apos;s Schedule</div>
        {["9:00 AM — Vinyasa Flow", "10:30 AM — Hot Yoga", "12:00 PM — Pilates", "5:30 PM — Power Yoga"].map((c) => (
          <div key={c} className="flex items-center gap-2 border-t border-gray-100 py-1">
            <div className="h-2 w-2 rounded-full bg-indigo-400" />
            <span className="text-[8px] text-gray-600">{c}</span>
          </div>
        ))}
      </div>
      {/* Quick actions */}
      <div className="flex gap-2">
        {["Add Class", "New Member", "Check In"].map((a) => (
          <div key={a} className="rounded bg-indigo-500 px-2 py-1 text-[7px] font-medium text-white">{a}</div>
        ))}
      </div>
    </MockupShell>
  );
}

function ScheduleMockup() {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const blocks = [
    { day: 0, top: "8%", h: "18%", color: "bg-indigo-400", label: "Vinyasa" },
    { day: 0, top: "42%", h: "15%", color: "bg-emerald-400", label: "Pilates" },
    { day: 1, top: "15%", h: "16%", color: "bg-purple-400", label: "Hot Yoga" },
    { day: 1, top: "50%", h: "18%", color: "bg-indigo-400", label: "Restorative" },
    { day: 2, top: "8%", h: "20%", color: "bg-emerald-400", label: "HIIT" },
    { day: 2, top: "45%", h: "15%", color: "bg-amber-400", label: "Meditation" },
    { day: 3, top: "12%", h: "18%", color: "bg-indigo-400", label: "Vinyasa" },
    { day: 3, top: "55%", h: "15%", color: "bg-purple-400", label: "Yin" },
    { day: 4, top: "8%", h: "15%", color: "bg-emerald-400", label: "Power" },
    { day: 4, top: "38%", h: "20%", color: "bg-indigo-400", label: "Sculpt" },
    { day: 5, top: "10%", h: "22%", color: "bg-purple-400", label: "Workshop" },
  ];
  return (
    <MockupShell activeIdx={1}>
      {/* Nav bar */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <div className="h-5 w-12 rounded bg-indigo-100 text-center text-[8px] leading-5 font-medium text-indigo-700">Today</div>
          <div className="h-5 w-5 rounded bg-gray-100 text-center text-[8px] text-gray-400">&lt;</div>
          <div className="h-5 w-5 rounded bg-gray-100 text-center text-[8px] text-gray-400">&gt;</div>
          <span className="ml-1 text-[8px] font-medium text-gray-500">Mar 3 – 9, 2026</span>
        </div>
        <div className="flex gap-0.5">
          <div className="h-5 w-8 rounded-l bg-gray-100 text-center text-[7px] leading-5 text-gray-500">Day</div>
          <div className="h-5 w-9 rounded-r bg-indigo-500 text-center text-[7px] leading-5 font-medium text-white">Week</div>
        </div>
      </div>
      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-gray-200 bg-gray-200">
        {days.map((d) => (
          <div key={d} className="bg-gray-50 py-1 text-center text-[7px] font-medium text-gray-500">{d}</div>
        ))}
        {days.map((_, dayIdx) => (
          <div key={dayIdx} className="relative h-28 bg-white">
            {blocks
              .filter((b) => b.day === dayIdx)
              .map((b, i) => (
                <div
                  key={i}
                  className={`absolute left-0.5 right-0.5 rounded ${b.color} px-0.5 opacity-90`}
                  style={{ top: b.top, height: b.h }}
                >
                  <span className="text-[6px] font-medium text-white">{b.label}</span>
                </div>
              ))}
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function PrivateSessionsMockup() {
  return (
    <MockupShell activeIdx={2}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Private Sessions</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ New Session</div>
      </div>
      {[
        { time: "9:00 AM", client: "Sarah Chen", type: "1-on-1 Yoga", vis: "Private" },
        { time: "11:00 AM", client: "Mike Johnson", type: "PT Session", vis: "Semi-Private" },
        { time: "2:00 PM", client: "Ava Williams", type: "Meditation", vis: "Private" },
        { time: "4:30 PM", client: "James Brown", type: "1-on-1 Pilates", vis: "Private" },
      ].map((s) => (
        <div key={s.time} className="flex items-center gap-2 border-t border-gray-100 py-1.5">
          <span className="w-14 text-[8px] font-medium text-gray-500">{s.time}</span>
          <div className="h-6 w-6 rounded-full bg-indigo-100 text-center text-[8px] leading-6 font-bold text-indigo-600">
            {s.client[0]}
          </div>
          <div className="flex-1">
            <div className="text-[8px] font-medium text-gray-700">{s.client}</div>
            <div className="text-[7px] text-gray-400">{s.type}</div>
          </div>
          <span className={`rounded-full px-1.5 py-0.5 text-[6px] font-medium ${s.vis === "Private" ? "bg-gray-100 text-gray-600" : "bg-blue-50 text-blue-600"}`}>
            {s.vis}
          </span>
        </div>
      ))}
    </MockupShell>
  );
}

function WorkshopsMockup() {
  return (
    <MockupShell activeIdx={3}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Workshops & Courses</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ Create</div>
      </div>
      <div className="mb-2 flex gap-1">
        {["All", "Workshop", "Course", "Retreat", "TT"].map((t, i) => (
          <div key={t} className={`rounded-full px-2 py-0.5 text-[7px] font-medium ${i === 0 ? "bg-indigo-500 text-white" : "bg-gray-100 text-gray-500"}`}>{t}</div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {[
          { title: "Yoga Retreat", status: "Published", enrolled: "12/20", color: "bg-emerald-400" },
          { title: "200hr TT Program", status: "Published", enrolled: "8/15", color: "bg-purple-400" },
          { title: "Meditation Course", status: "Draft", enrolled: "0/25", color: "bg-amber-400" },
          { title: "Anatomy Workshop", status: "Published", enrolled: "18/20", color: "bg-indigo-400" },
        ].map((w) => (
          <div key={w.title} className="rounded-lg border border-gray-100 p-2">
            <div className={`mb-1 h-8 rounded ${w.color} opacity-20`} />
            <div className="text-[8px] font-semibold text-gray-700">{w.title}</div>
            <div className="flex items-center justify-between">
              <span className={`text-[7px] font-medium ${w.status === "Draft" ? "text-gray-400" : "text-emerald-600"}`}>{w.status}</span>
              <span className="text-[7px] text-gray-400">{w.enrolled}</span>
            </div>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function MembersMockup() {
  const rows = [
    { name: "Sarah Chen", email: "sarah@email.com", visits: "34", status: "Active" },
    { name: "Mike Johnson", email: "mike@email.com", visits: "22", status: "Active" },
    { name: "Ava Williams", email: "ava@email.com", visits: "8", status: "At Risk" },
    { name: "James Brown", email: "james@email.com", visits: "45", status: "Active" },
    { name: "Lisa Park", email: "lisa@email.com", visits: "16", status: "Active" },
  ];
  return (
    <MockupShell activeIdx={4}>
      <div className="mb-2 flex items-center gap-2">
        <div className="h-6 flex-1 rounded border border-gray-200 bg-gray-50 px-2 text-[8px] leading-6 text-gray-400">Search members...</div>
        <div className="rounded bg-gray-100 px-2 py-1 text-[7px] font-medium text-gray-500">Filter</div>
        <div className="rounded bg-indigo-500 px-2 py-1 text-[7px] font-medium text-white">+ Add Member</div>
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="grid grid-cols-5 bg-gray-50 px-2 py-1">
          {["Name", "Email", "Visits", "Membership", "Status"].map((h) => (
            <div key={h} className="text-[7px] font-semibold text-gray-500">{h}</div>
          ))}
        </div>
        {rows.map((r) => (
          <div key={r.name} className="grid grid-cols-5 items-center border-t border-gray-100 px-2 py-1.5">
            <div className="flex items-center gap-1">
              <div className="h-4 w-4 rounded-full bg-indigo-100 text-center text-[7px] leading-4 font-bold text-indigo-600">{r.name[0]}</div>
              <span className="text-[8px] font-medium text-gray-800">{r.name}</span>
            </div>
            <div className="text-[7px] text-gray-500">{r.email}</div>
            <div className="text-[8px] text-gray-600">{r.visits}</div>
            <div className="text-[7px] text-gray-500">Unlimited</div>
            <span className={`w-fit rounded-full px-1.5 py-0.5 text-[7px] font-medium ${r.status === "Active" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>
              {r.status}
            </span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function InstructorsMockup() {
  return (
    <MockupShell activeIdx={5}>
      <div className="mb-2 text-[9px] font-semibold text-gray-700">Instructors</div>
      <div className="grid grid-cols-3 gap-2">
        {[
          { name: "Maya Rodriguez", specs: "Vinyasa, Hot Yoga", classes: 12 },
          { name: "David Kim", specs: "Pilates, HIIT", classes: 8 },
          { name: "Emma Lewis", specs: "Meditation, Yin", classes: 6 },
          { name: "Alex Turner", specs: "Power Yoga", classes: 10 },
          { name: "Priya Sharma", specs: "Restorative", classes: 5 },
          { name: "Chris Watts", specs: "Sculpt, Barre", classes: 9 },
        ].map((inst) => (
          <div key={inst.name} className="rounded-lg border border-gray-100 p-2 text-center">
            <div className="mx-auto mb-1 h-8 w-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-400 text-center text-[10px] leading-8 font-bold text-white">
              {inst.name.split(" ").map((n) => n[0]).join("")}
            </div>
            <div className="text-[8px] font-medium text-gray-700">{inst.name}</div>
            <div className="text-[7px] text-gray-400">{inst.specs}</div>
            <div className="mt-1 text-[7px] text-indigo-600">{inst.classes} classes/wk</div>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function StaffMockup() {
  return (
    <MockupShell activeIdx={6}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Staff & Roles</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ Invite</div>
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="grid grid-cols-4 bg-gray-50 px-2 py-1">
          {["Name", "Role", "Location", "Status"].map((h) => (
            <div key={h} className="text-[7px] font-semibold text-gray-500">{h}</div>
          ))}
        </div>
        {[
          { name: "Don Harris", role: "Owner", loc: "All Locations", active: true },
          { name: "Maya Rodriguez", role: "Instructor", loc: "Downtown", active: true },
          { name: "Sam Lee", role: "Front Desk", loc: "Downtown", active: true },
          { name: "Taylor Kim", role: "Admin", loc: "Midtown", active: true },
          { name: "Jordan Ellis", role: "Instructor", loc: "Midtown", active: false },
        ].map((s) => (
          <div key={s.name} className="grid grid-cols-4 items-center border-t border-gray-100 px-2 py-1.5">
            <span className="text-[8px] font-medium text-gray-700">{s.name}</span>
            <span className={`w-fit rounded-full px-1.5 py-0.5 text-[7px] font-medium ${
              s.role === "Owner" ? "bg-indigo-100 text-indigo-700" :
              s.role === "Admin" ? "bg-purple-100 text-purple-700" :
              s.role === "Instructor" ? "bg-emerald-100 text-emerald-700" :
              "bg-gray-100 text-gray-600"
            }`}>{s.role}</span>
            <span className="text-[7px] text-gray-500">{s.loc}</span>
            <span className={`text-[7px] font-medium ${s.active ? "text-green-600" : "text-gray-400"}`}>
              {s.active ? "Active" : "Inactive"}
            </span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function TimeClockMockup() {
  return (
    <MockupShell activeIdx={7}>
      {/* Clock in panel */}
      <div className="mb-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-center">
        <div className="text-[10px] font-bold text-indigo-700">Clock In / Out</div>
        <div className="mt-1 text-lg font-bold text-indigo-900">10:42 AM</div>
        <div className="mt-1 flex justify-center gap-2">
          <div className="rounded bg-emerald-500 px-3 py-1 text-[8px] font-semibold text-white">Clock In</div>
          <div className="rounded bg-gray-200 px-3 py-1 text-[8px] font-medium text-gray-500">Clock Out</div>
        </div>
      </div>
      {/* Timesheet */}
      <div className="text-[8px] font-semibold text-gray-600 mb-1">This Week&apos;s Timesheet</div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        {[
          { day: "Mon", in: "8:00 AM", out: "4:00 PM", hrs: "8.0" },
          { day: "Tue", in: "9:00 AM", out: "5:00 PM", hrs: "8.0" },
          { day: "Wed", in: "8:30 AM", out: "4:30 PM", hrs: "8.0" },
          { day: "Thu", in: "—", out: "—", hrs: "—" },
        ].map((r) => (
          <div key={r.day} className="grid grid-cols-4 border-t border-gray-100 px-2 py-1 first:border-t-0">
            <span className="text-[7px] font-medium text-gray-600">{r.day}</span>
            <span className="text-[7px] text-gray-500">{r.in}</span>
            <span className="text-[7px] text-gray-500">{r.out}</span>
            <span className="text-[7px] font-medium text-gray-700">{r.hrs}h</span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function VideoMockup() {
  return (
    <MockupShell activeIdx={8}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Video Library</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ Upload</div>
      </div>
      <div className="mb-2 flex gap-1">
        {["All", "Yoga", "Pilates", "Meditation", "HIIT"].map((c, i) => (
          <div key={c} className={`rounded-full px-2 py-0.5 text-[7px] font-medium ${i === 0 ? "bg-indigo-500 text-white" : "bg-gray-100 text-gray-500"}`}>{c}</div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[
          { title: "Morning Vinyasa", src: "Zoom", views: "234", color: "bg-indigo-300" },
          { title: "Power Yoga Flow", src: "YouTube", views: "189", color: "bg-purple-300" },
          { title: "Gentle Stretch", src: "Mux", views: "156", color: "bg-emerald-300" },
          { title: "HIIT Burn", src: "Zoom", views: "312", color: "bg-amber-300" },
          { title: "Yin & Restore", src: "YouTube", views: "98", color: "bg-pink-300" },
          { title: "Core Pilates", src: "Mux", views: "201", color: "bg-blue-300" },
        ].map((v) => (
          <div key={v.title} className="rounded-lg border border-gray-100 overflow-hidden">
            <div className={`relative h-10 ${v.color} opacity-30`}>
              <Play className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 text-gray-600" />
            </div>
            <div className="p-1.5">
              <div className="text-[7px] font-medium text-gray-700">{v.title}</div>
              <div className="flex items-center justify-between">
                <span className="text-[6px] text-gray-400">{v.src}</span>
                <span className="text-[6px] text-gray-400">{v.views} views</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function MembershipsMockup() {
  return (
    <MockupShell activeIdx={9}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Membership Plans</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ New Plan</div>
      </div>
      <div className="space-y-2">
        {[
          { name: "Unlimited Monthly", price: "$149/mo", members: 86, scope: "All Access", color: "border-indigo-300 bg-indigo-50" },
          { name: "8-Class Pack", price: "$99/mo", members: 42, scope: "In-Studio", color: "border-emerald-300 bg-emerald-50" },
          { name: "Online Only", price: "$29/mo", members: 34, scope: "Video", color: "border-purple-300 bg-purple-50" },
          { name: "Drop-In", price: "$20/class", members: 28, scope: "Per Visit", color: "border-amber-300 bg-amber-50" },
        ].map((m) => (
          <div key={m.name} className={`flex items-center justify-between rounded-lg border p-2 ${m.color}`}>
            <div>
              <div className="text-[8px] font-semibold text-gray-700">{m.name}</div>
              <div className="text-[7px] text-gray-500">{m.scope}</div>
            </div>
            <div className="text-right">
              <div className="text-[9px] font-bold text-gray-800">{m.price}</div>
              <div className="text-[7px] text-gray-400">{m.members} active</div>
            </div>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function MarketingMockup() {
  return (
    <MockupShell activeIdx={0}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Marketing Campaigns</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ Create</div>
      </div>
      <div className="mb-2 flex gap-1">
        {["All", "Email", "SMS", "Google Ads", "Meta Ads"].map((t, i) => (
          <div key={t} className={`rounded-full px-2 py-0.5 text-[7px] font-medium ${i === 0 ? "bg-indigo-500 text-white" : "bg-gray-100 text-gray-500"}`}>{t}</div>
        ))}
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        {[
          { name: "Spring Promo", type: "Email", status: "Sent", opens: "68%", color: "bg-green-100 text-green-700" },
          { name: "New Class Alert", type: "SMS", status: "Sent", opens: "82%", color: "bg-green-100 text-green-700" },
          { name: "Summer Campaign", type: "Email", status: "Draft", opens: "—", color: "bg-gray-100 text-gray-500" },
          { name: "Retargeting", type: "Meta", status: "Active", opens: "3.2% CTR", color: "bg-blue-100 text-blue-700" },
        ].map((c) => (
          <div key={c.name} className="grid grid-cols-4 items-center border-t border-gray-100 px-2 py-1.5 first:border-t-0">
            <span className="text-[8px] font-medium text-gray-700">{c.name}</span>
            <span className="text-[7px] text-gray-500">{c.type}</span>
            <span className={`w-fit rounded-full px-1.5 py-0.5 text-[6px] font-medium ${c.color}`}>{c.status}</span>
            <span className="text-[7px] text-gray-500">{c.opens}</span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function PaymentsMockup() {
  return (
    <MockupShell activeIdx={1}>
      {/* Revenue cards */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        {[
          { label: "This Month", val: "$12,480", trend: "+12%", color: "text-emerald-600" },
          { label: "Last Month", val: "$11,120", trend: "", color: "text-gray-600" },
          { label: "Outstanding", val: "$340", trend: "3 failed", color: "text-red-500" },
        ].map((r) => (
          <div key={r.label} className="rounded-lg border border-gray-100 bg-gray-50 p-2 text-center">
            <div className={`text-[10px] font-bold ${r.color}`}>{r.val}</div>
            <div className="text-[7px] text-gray-400">{r.label}</div>
            {r.trend && <div className={`text-[7px] font-medium ${r.color}`}>{r.trend}</div>}
          </div>
        ))}
      </div>
      {/* Transaction table */}
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="grid grid-cols-4 bg-gray-50 px-2 py-1">
          {["Member", "Amount", "Type", "Date"].map((h) => (
            <div key={h} className="text-[7px] font-semibold text-gray-500">{h}</div>
          ))}
        </div>
        {[
          { member: "Sarah Chen", amount: "$149.00", type: "Membership", date: "Mar 1" },
          { member: "Mike Johnson", amount: "$20.00", type: "Drop-In", date: "Mar 1" },
          { member: "Ava Williams", amount: "$99.00", type: "8-Pack", date: "Feb 28" },
          { member: "James Brown", amount: "$25.00", type: "Retail", date: "Feb 28" },
        ].map((t) => (
          <div key={t.member + t.date} className="grid grid-cols-4 border-t border-gray-100 px-2 py-1.5">
            <span className="text-[8px] font-medium text-gray-700">{t.member}</span>
            <span className="text-[8px] text-gray-600">{t.amount}</span>
            <span className="text-[7px] text-gray-500">{t.type}</span>
            <span className="text-[7px] text-gray-400">{t.date}</span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function POSMockup() {
  return (
    <MockupShell activeIdx={2}>
      <div className="grid grid-cols-5 gap-2">
        {/* Product grid */}
        <div className="col-span-3">
          <div className="mb-2 flex gap-1">
            {["All", "Mats", "Apparel", "Drinks", "Accessories"].map((c, i) => (
              <div key={c} className={`rounded-full px-1.5 py-0.5 text-[7px] font-medium ${i === 0 ? "bg-indigo-500 text-white" : "bg-gray-100 text-gray-500"}`}>{c}</div>
            ))}
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { name: "Yoga Mat", price: "$45" },
              { name: "Water Bottle", price: "$12" },
              { name: "Tank Top", price: "$28" },
              { name: "Strap Set", price: "$15" },
              { name: "Towel", price: "$18" },
              { name: "Block", price: "$10" },
            ].map((p) => (
              <div key={p.name} className="rounded-lg border border-gray-100 p-1.5 text-center hover:border-indigo-200">
                <div className="mb-1 h-6 rounded bg-gray-100" />
                <div className="text-[7px] font-medium text-gray-700">{p.name}</div>
                <div className="text-[7px] font-bold text-indigo-600">{p.price}</div>
              </div>
            ))}
          </div>
        </div>
        {/* Cart sidebar */}
        <div className="col-span-2 rounded-lg border border-gray-200 bg-gray-50 p-2">
          <div className="mb-1 text-[8px] font-semibold text-gray-700">Cart</div>
          {[
            { item: "Yoga Mat", qty: 1, price: "$45.00" },
            { item: "Water Bottle", qty: 2, price: "$24.00" },
          ].map((c) => (
            <div key={c.item} className="flex items-center justify-between border-t border-gray-200 py-1">
              <span className="text-[7px] text-gray-600">{c.item} x{c.qty}</span>
              <span className="text-[7px] font-medium text-gray-700">{c.price}</span>
            </div>
          ))}
          <div className="mt-1 border-t border-gray-300 pt-1">
            <div className="flex justify-between text-[8px] font-bold text-gray-800">
              <span>Total</span><span>$69.00</span>
            </div>
          </div>
          <div className="mt-1.5 rounded bg-indigo-500 py-1 text-center text-[7px] font-semibold text-white">Checkout</div>
        </div>
      </div>
    </MockupShell>
  );
}

function InventoryMockup() {
  return (
    <MockupShell activeIdx={3}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[9px] font-semibold text-gray-700">Inventory</span>
        <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">+ Add Product</div>
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <div className="grid grid-cols-5 bg-gray-50 px-2 py-1">
          {["Product", "SKU", "Price", "Stock", "Status"].map((h) => (
            <div key={h} className="text-[7px] font-semibold text-gray-500">{h}</div>
          ))}
        </div>
        {[
          { name: "Premium Mat", sku: "MAT-001", price: "$45", stock: 24, status: "In Stock" },
          { name: "Water Bottle", sku: "BTL-001", price: "$12", stock: 3, status: "Low Stock" },
          { name: "Tank Top (S)", sku: "TOP-S01", price: "$28", stock: 12, status: "In Stock" },
          { name: "Yoga Strap", sku: "STP-001", price: "$15", stock: 0, status: "Out of Stock" },
          { name: "Cork Block", sku: "BLK-001", price: "$10", stock: 18, status: "In Stock" },
        ].map((p) => (
          <div key={p.sku} className="grid grid-cols-5 items-center border-t border-gray-100 px-2 py-1.5">
            <span className="text-[8px] font-medium text-gray-700">{p.name}</span>
            <span className="font-mono text-[7px] text-gray-400">{p.sku}</span>
            <span className="text-[8px] text-gray-600">{p.price}</span>
            <span className="text-[8px] text-gray-600">{p.stock}</span>
            <span className={`w-fit rounded-full px-1.5 py-0.5 text-[6px] font-medium ${
              p.status === "In Stock" ? "bg-green-100 text-green-700" :
              p.status === "Low Stock" ? "bg-yellow-100 text-yellow-700" :
              "bg-red-100 text-red-700"
            }`}>{p.status}</span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function FacilitiesMockup() {
  return (
    <MockupShell activeIdx={4}>
      <div className="mb-2 text-[9px] font-semibold text-gray-700">Facilities & Equipment</div>
      <div className="mb-3 grid grid-cols-3 gap-2">
        {[
          { name: "Main Studio", capacity: "30 people", status: "Available" },
          { name: "Hot Room", capacity: "20 people", status: "In Use" },
          { name: "Private Room", capacity: "4 people", status: "Available" },
        ].map((r) => (
          <div key={r.name} className="rounded-lg border border-gray-100 p-2 text-center">
            <div className="mx-auto mb-1 h-6 w-6 rounded bg-indigo-100 text-center text-[10px] leading-6">🏠</div>
            <div className="text-[8px] font-semibold text-gray-700">{r.name}</div>
            <div className="text-[7px] text-gray-400">{r.capacity}</div>
            <span className={`mt-0.5 inline-block rounded-full px-1.5 py-0.5 text-[6px] font-medium ${
              r.status === "Available" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
            }`}>{r.status}</span>
          </div>
        ))}
      </div>
      <div className="text-[8px] font-semibold text-gray-600 mb-1">Equipment</div>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        {[
          { item: "Yoga Mats (Studio)", qty: "30", condition: "Good" },
          { item: "Reformers (Pilates)", qty: "8", condition: "Good" },
          { item: "Sound System", qty: "2", condition: "Maintenance" },
        ].map((e) => (
          <div key={e.item} className="grid grid-cols-3 border-t border-gray-100 px-2 py-1 first:border-t-0">
            <span className="text-[7px] font-medium text-gray-700">{e.item}</span>
            <span className="text-[7px] text-gray-500">Qty: {e.qty}</span>
            <span className={`text-[7px] font-medium ${e.condition === "Good" ? "text-green-600" : "text-amber-600"}`}>{e.condition}</span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function AIMockup() {
  return (
    <MockupShell activeIdx={5}>
      <div className="mb-3 grid grid-cols-2 gap-2">
        {/* Content generator */}
        <div className="rounded-lg border border-gray-200 p-2">
          <div className="mb-1 text-[8px] font-semibold text-gray-700">AI Content Generator</div>
          <div className="mb-1 flex gap-1">
            {["Email", "Social", "SMS"].map((t, i) => (
              <div key={t} className={`rounded px-1.5 py-0.5 text-[7px] font-medium ${i === 0 ? "bg-indigo-500 text-white" : "bg-gray-100 text-gray-500"}`}>{t}</div>
            ))}
          </div>
          <div className="mb-1 h-4 rounded border border-gray-200 bg-gray-50 px-1 text-[7px] leading-4 text-gray-400">Describe your content...</div>
          <div className="flex gap-1">
            {["Professional", "Friendly", "Urgent"].map((tone, i) => (
              <div key={tone} className={`rounded-full px-1.5 py-0.5 text-[6px] ${i === 1 ? "bg-indigo-100 text-indigo-600" : "bg-gray-50 text-gray-400"}`}>{tone}</div>
            ))}
          </div>
          <div className="mt-1 rounded bg-indigo-500 py-0.5 text-center text-[7px] font-medium text-white">Generate</div>
        </div>
        {/* Churn risk */}
        <div className="rounded-lg border border-gray-200 p-2">
          <div className="mb-1 text-[8px] font-semibold text-gray-700">Churn Risk Detection</div>
          {[
            { name: "Ava Williams", risk: "High", visits: "1 visit in 30d" },
            { name: "Tom Baker", risk: "Medium", visits: "3 visits in 30d" },
            { name: "Liz Reed", risk: "High", visits: "0 visits in 30d" },
          ].map((m) => (
            <div key={m.name} className="flex items-center justify-between border-t border-gray-100 py-1">
              <div>
                <div className="text-[7px] font-medium text-gray-700">{m.name}</div>
                <div className="text-[6px] text-gray-400">{m.visits}</div>
              </div>
              <span className={`rounded-full px-1.5 py-0.5 text-[6px] font-medium ${
                m.risk === "High" ? "bg-red-100 text-red-700" : "bg-yellow-100 text-yellow-700"
              }`}>{m.risk}</span>
            </div>
          ))}
        </div>
      </div>
    </MockupShell>
  );
}

function AnalyticsMockup() {
  const bars = [35, 52, 48, 65, 58, 72, 68, 80, 75, 88, 82, 95];
  return (
    <MockupShell activeIdx={6}>
      {/* KPI row */}
      <div className="mb-3 grid grid-cols-4 gap-2">
        {[
          { label: "Revenue", val: "$12.4k", delta: "+12%", color: "text-emerald-600" },
          { label: "Members", val: "248", delta: "+8%", color: "text-indigo-600" },
          { label: "Classes", val: "86", delta: "+5%", color: "text-purple-600" },
          { label: "Attendance", val: "91%", delta: "+3%", color: "text-amber-600" },
        ].map((k) => (
          <div key={k.label} className="rounded-lg border border-gray-100 bg-gray-50 p-1.5 text-center">
            <div className={`text-[10px] font-bold ${k.color}`}>{k.val}</div>
            <div className="text-[7px] text-gray-400">{k.label}</div>
            <div className="text-[7px] font-medium text-emerald-500">{k.delta}</div>
          </div>
        ))}
      </div>
      {/* Bar chart */}
      <div className="rounded-lg border border-gray-100 bg-gray-50 p-2">
        <div className="mb-1 text-[8px] font-medium text-gray-600">Revenue Trend (12 months)</div>
        <div className="flex h-16 items-end gap-1">
          {bars.map((h, i) => (
            <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-indigo-500 to-purple-400" style={{ height: `${h}%` }} />
          ))}
        </div>
      </div>
    </MockupShell>
  );
}

function IntegrationsMockup() {
  return (
    <MockupShell activeIdx={7}>
      <div className="mb-2 text-[9px] font-semibold text-gray-700">Integrations</div>
      <div className="grid grid-cols-2 gap-2">
        {[
          { name: "Stripe", desc: "Payment processing", status: "Connected", color: "bg-green-100 text-green-700" },
          { name: "ClassPass", desc: "Marketplace", status: "Connected", color: "bg-green-100 text-green-700" },
          { name: "SendGrid", desc: "Email delivery", status: "Connected", color: "bg-green-100 text-green-700" },
          { name: "Twilio", desc: "SMS messaging", status: "Not Connected", color: "bg-gray-100 text-gray-500" },
          { name: "Zoom", desc: "Virtual classes", status: "Connected", color: "bg-green-100 text-green-700" },
          { name: "Gusto", desc: "Payroll", status: "Not Connected", color: "bg-gray-100 text-gray-500" },
          { name: "QuickBooks", desc: "Accounting", status: "Not Connected", color: "bg-gray-100 text-gray-500" },
          { name: "Google Ads", desc: "Advertising", status: "Connected", color: "bg-green-100 text-green-700" },
        ].map((int) => (
          <div key={int.name} className="flex items-center justify-between rounded-lg border border-gray-100 p-2">
            <div>
              <div className="text-[8px] font-semibold text-gray-700">{int.name}</div>
              <div className="text-[7px] text-gray-400">{int.desc}</div>
            </div>
            <span className={`rounded-full px-1.5 py-0.5 text-[6px] font-medium ${int.color}`}>{int.status}</span>
          </div>
        ))}
      </div>
    </MockupShell>
  );
}

function ImportMockup() {
  return (
    <MockupShell activeIdx={8}>
      <div className="mb-2 text-[9px] font-semibold text-gray-700">Data Import</div>
      <div className="mb-3 grid grid-cols-2 gap-2">
        {["Members", "Classes", "Instructors", "Memberships", "Attendance"].map((type) => (
          <div key={type} className="flex items-center gap-2 rounded-lg border border-dashed border-gray-300 p-2">
            <Upload className="h-3 w-3 text-gray-400" />
            <div>
              <div className="text-[8px] font-medium text-gray-700">Import {type}</div>
              <div className="text-[7px] text-gray-400">Upload CSV file</div>
            </div>
          </div>
        ))}
      </div>
      {/* Preview table */}
      <div className="rounded-lg border border-gray-200 p-2">
        <div className="mb-1 text-[8px] font-semibold text-gray-600">Preview — members.csv</div>
        <div className="overflow-hidden rounded border border-gray-200">
          <div className="grid grid-cols-4 bg-gray-50 px-2 py-0.5">
            {["Name", "Email", "Phone", "Plan"].map((h) => (
              <div key={h} className="text-[6px] font-semibold text-gray-500">{h}</div>
            ))}
          </div>
          {[
            ["Sarah Chen", "sarah@...", "555-0101", "Unlimited"],
            ["Mike J.", "mike@...", "555-0102", "8-Pack"],
          ].map((row, i) => (
            <div key={i} className="grid grid-cols-4 border-t border-gray-100 px-2 py-0.5">
              {row.map((cell, j) => (
                <div key={j} className="text-[6px] text-gray-600">{cell}</div>
              ))}
            </div>
          ))}
        </div>
        <div className="mt-1 flex items-center gap-2">
          <div className="rounded bg-indigo-500 px-2 py-0.5 text-[7px] font-medium text-white">Dry Run</div>
          <div className="rounded bg-emerald-500 px-2 py-0.5 text-[7px] font-medium text-white">Import</div>
          <span className="text-[7px] text-gray-400">2 rows ready</span>
        </div>
      </div>
    </MockupShell>
  );
}

function SettingsMockup() {
  return (
    <MockupShell activeIdx={9}>
      <div className="mb-2 flex gap-1">
        {["General", "Billing", "Communications", "Locations"].map((tab, i) => (
          <div key={tab} className={`rounded-t px-2 py-1 text-[7px] font-medium ${i === 0 ? "border-b-2 border-indigo-500 text-indigo-700" : "text-gray-400"}`}>{tab}</div>
        ))}
      </div>
      <div className="space-y-2 rounded-lg border border-gray-200 p-3">
        {[
          { label: "Studio Name", value: "Your Studio" },
          { label: "Timezone", value: "America/Los_Angeles" },
          { label: "Currency", value: "USD ($)" },
          { label: "Default Class Duration", value: "60 minutes" },
          { label: "Cancellation Policy", value: "2 hours before" },
        ].map((f) => (
          <div key={f.label} className="flex items-center justify-between border-b border-gray-100 pb-1.5 last:border-b-0">
            <span className="text-[8px] font-medium text-gray-600">{f.label}</span>
            <div className="h-5 w-32 rounded border border-gray-200 bg-gray-50 px-1.5 text-[8px] leading-5 text-gray-700">{f.value}</div>
          </div>
        ))}
        <div className="pt-1">
          <div className="rounded bg-indigo-500 px-3 py-1 text-center text-[7px] font-semibold text-white">Save Changes</div>
        </div>
      </div>
    </MockupShell>
  );
}

/* ━━━ Section Data ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

const SECTIONS: TourSection[] = [
  {
    id: "dashboard",
    icon: LayoutDashboard,
    title: "Dashboard",
    headline: "Your command center at a glance",
    description: "See today's classes, revenue metrics, member activity, and quick actions — all on a single screen. Real-time KPIs update as your day progresses.",
    features: [
      "Live revenue, member count, and class stats",
      "Today's schedule with attendance counts",
      "Quick action buttons for common tasks",
      "At-a-glance notifications and alerts",
      "Period-over-period comparison indicators",
    ],
    mockup: DashboardMockup,
    accentFrom: "from-blue-500",
    accentTo: "to-indigo-600",
  },
  {
    id: "schedule",
    icon: Calendar,
    title: "Schedule",
    headline: "Your entire schedule, beautifully organized",
    description: "Build your weekly schedule with recurring series or one-off classes. Toggle between Day and Week views, assign instructors and rooms, and manage waitlists — all from one calendar.",
    features: [
      "Day and Week calendar views with color-coded classes",
      "Recurring series with flexible RRULE patterns",
      "Check-in, no-show, and waitlist management per session",
      "Instructor and room assignment per class",
      "Upload recordings directly from session detail",
      "Automatic Zoom recording import to video library",
    ],
    mockup: ScheduleMockup,
    accentFrom: "from-indigo-500",
    accentTo: "to-blue-600",
  },
  {
    id: "private-sessions",
    icon: UserRound,
    title: "Private Sessions",
    headline: "One-on-one and small group bookings",
    description: "Manage private sessions with visibility controls, instructor availability, and easy booking. Perfect for personal training, private yoga, and specialized services.",
    features: [
      "Private and semi-private visibility badges",
      "Instructor availability calendar integration",
      "Client self-booking through member portal",
      "Custom service types and pricing",
      "Session notes and progress tracking",
    ],
    mockup: PrivateSessionsMockup,
    accentFrom: "from-violet-500",
    accentTo: "to-purple-600",
  },
  {
    id: "workshops",
    icon: BookOpen,
    title: "Workshops & Courses",
    headline: "Multi-session programs made simple",
    description: "Create workshops, courses, teacher training programs, and retreats. Track enrollment, manage the Draft → Published → Completed lifecycle, and offer virtual attendance.",
    features: [
      "Four event types: Workshop, Course, Teacher Training, Retreat",
      "Draft → Published → Completed lifecycle management",
      "Enrollment tracking with capacity limits",
      "Multi-session scheduling with date ranges",
      "Virtual/hybrid support with video integration",
    ],
    mockup: WorkshopsMockup,
    accentFrom: "from-amber-500",
    accentTo: "to-orange-600",
  },
  {
    id: "members",
    icon: Users,
    title: "Members",
    headline: "Know every member inside and out",
    description: "Complete member profiles with attendance history, membership status, payment records, and visit tracking. Automated at-risk alerts keep you ahead of churn.",
    features: [
      "Searchable directory with filters (status, membership, visits)",
      "Full member profiles with visit and payment history",
      "Attendance tracking with check-in and no-show counts",
      "Automated at-risk detection for low-attendance members",
      "Self-service member portal for booking and account management",
    ],
    mockup: MembersMockup,
    accentFrom: "from-emerald-500",
    accentTo: "to-green-600",
  },
  {
    id: "instructors",
    icon: UserCheck,
    title: "Instructors",
    headline: "Manage your teaching team",
    description: "Instructor profiles with specialties, contact info, and schedule linking. See each instructor's weekly class load and availability at a glance.",
    features: [
      "Instructor profile cards with avatar and specialties",
      "Weekly class count and schedule overview",
      "Contact information and bio",
      "Linked to schedule for class assignment",
      "Instructor-specific reporting in analytics",
    ],
    mockup: InstructorsMockup,
    accentFrom: "from-teal-500",
    accentTo: "to-cyan-600",
  },
  {
    id: "staff",
    icon: Users2,
    title: "Staff & Roles",
    headline: "Role-based access for your entire team",
    description: "Invite staff with specific roles — Owner, Admin, Instructor, or Front Desk. Each role gets tailored permissions, and roles can be set per-location for multi-studio operations.",
    features: [
      "Four role levels: Owner, Admin, Instructor, Front Desk",
      "Granular permission assignment per role",
      "Per-location role assignment for multi-studio",
      "Email invite workflow with secure invite tokens",
      "Active/inactive staff status management",
    ],
    mockup: StaffMockup,
    accentFrom: "from-indigo-500",
    accentTo: "to-violet-600",
  },
  {
    id: "time-clock",
    icon: Clock,
    title: "Time Clock",
    headline: "Track hours and simplify payroll",
    description: "Staff clock in and out with a single click. View timesheets by day, week, or pay period. Approve hours and compile payroll data — all without spreadsheets.",
    features: [
      "One-click clock in / clock out",
      "Shift type categorization (teaching, admin, training)",
      "Weekly timesheet view with daily totals",
      "Manager approval workflow for timesheet sign-off",
      "Payroll compilation for export to Gusto/QuickBooks",
    ],
    mockup: TimeClockMockup,
    accentFrom: "from-sky-500",
    accentTo: "to-blue-600",
  },
  {
    id: "video",
    icon: Video,
    title: "Video Library",
    headline: "On-demand video from multiple sources",
    description: "Upload class recordings, import from YouTube, or auto-capture from Zoom sessions. Build a categorized video library your members can stream anytime.",
    features: [
      "Multi-source support: YouTube, Mux, and Zoom",
      "Automatic Zoom recording import after live classes",
      "Category and tag-based organization",
      "View count and engagement analytics",
      "Member-gated access by membership type",
    ],
    mockup: VideoMockup,
    accentFrom: "from-purple-500",
    accentTo: "to-pink-600",
  },
  {
    id: "memberships",
    icon: IdCard,
    title: "Memberships",
    headline: "Flexible plans for every member",
    description: "Create unlimited membership types — monthly unlimited, class packs, online-only, drop-ins. Stripe auto-billing handles recurring charges while you manage freezes and cancellations.",
    features: [
      "Unlimited membership plan types with custom pricing",
      "Access scopes: In-Studio, Online, or All Access",
      "Stripe auto-recurring billing integration",
      "Freeze, cancel, and upgrade workflows",
      "Active member count per plan type",
    ],
    mockup: MembershipsMockup,
    accentFrom: "from-rose-500",
    accentTo: "to-pink-600",
  },
  {
    id: "marketing",
    icon: Mail,
    title: "Marketing",
    headline: "Reach members across every channel",
    description: "Create email campaigns, send SMS messages, and manage Google and Meta ad integrations — all from one marketing hub. Track open rates, click-through, and conversions.",
    features: [
      "Email campaign builder with templates",
      "SMS messaging via Twilio integration",
      "Google Ads and Meta/Facebook Ads management",
      "Campaign status tracking (Draft, Sent, Active)",
      "Open rate, CTR, and conversion analytics",
    ],
    mockup: MarketingMockup,
    accentFrom: "from-orange-500",
    accentTo: "to-red-600",
  },
  {
    id: "payments",
    icon: CreditCard,
    title: "Payments",
    headline: "Complete revenue visibility",
    description: "Powered by Stripe Connect, see every transaction across memberships, drop-ins, packages, and retail. Revenue summary cards, transaction history, and failed payment alerts.",
    features: [
      "Stripe Connect secure payment processing",
      "Revenue summary with month-over-month comparison",
      "Full transaction history with search and filters",
      "Failed payment alerts and retry management",
      "Refund processing directly from transaction detail",
    ],
    mockup: PaymentsMockup,
    accentFrom: "from-emerald-500",
    accentTo: "to-teal-600",
  },
  {
    id: "pos",
    icon: ShoppingCart,
    title: "Point of Sale",
    headline: "In-studio retail, simplified",
    description: "A visual product grid with category browsing and a cart sidebar. Process sales with multiple payment methods and view daily summaries at close.",
    features: [
      "Visual product grid with category tabs",
      "Cart management with quantity adjustments",
      "Multiple payment methods (card, cash, account credit)",
      "Daily sales summary and register close reports",
      "Inventory auto-deduction on sale",
    ],
    mockup: POSMockup,
    accentFrom: "from-amber-500",
    accentTo: "to-yellow-600",
  },
  {
    id: "inventory",
    icon: Package,
    title: "Inventory",
    headline: "Track every product and stock level",
    description: "Manage your product catalog with SKUs, pricing, and tax settings. Real-time stock tracking with low-stock alerts and reorder points to prevent stockouts.",
    features: [
      "Product management with SKU, price, and tax config",
      "Real-time stock level tracking",
      "Low stock alerts and reorder point notifications",
      "Stock adjustment history with reason codes",
      "Auto-sync with Point of Sale transactions",
    ],
    mockup: InventoryMockup,
    accentFrom: "from-stone-500",
    accentTo: "to-gray-600",
  },
  {
    id: "facilities",
    icon: Building2,
    title: "Facilities",
    headline: "Rooms, equipment, and maintenance",
    description: "Map out your studio's rooms with capacity info, manage equipment inventory, and track maintenance requests — so everything runs smoothly.",
    features: [
      "Room management with capacity and availability",
      "Equipment inventory and condition tracking",
      "Maintenance request submission and status tracking",
      "Room assignment linking to schedule",
      "Capacity planning for class size limits",
    ],
    mockup: FacilitiesMockup,
    accentFrom: "from-cyan-500",
    accentTo: "to-blue-600",
  },
  {
    id: "ai",
    icon: Sparkles,
    title: "AI Assistant",
    headline: "AI that works for your business",
    description: "Generate marketing content in seconds — emails, social posts, SMS messages — with tone selection. Plus, AI-powered churn detection flags at-risk members before they leave.",
    features: [
      "AI content generation for Email, Social, and SMS",
      "Tone selection: Professional, Friendly, Urgent",
      "Draft approval workflow before sending",
      "Churn risk detection with engagement scoring",
      "Actionable member retention recommendations",
    ],
    mockup: AIMockup,
    accentFrom: "from-pink-500",
    accentTo: "to-rose-600",
  },
  {
    id: "analytics",
    icon: BarChart3,
    title: "Analytics",
    headline: "Data-driven decisions for your studio",
    description: "Revenue trends, attendance patterns, membership distribution, and instructor activity — all visualized with charts and period-over-period comparisons.",
    features: [
      "Revenue and attendance trend line charts",
      "Membership type distribution breakdowns",
      "Instructor activity and class fill rates",
      "Period-over-period comparison (month, quarter, year)",
      "Exportable reports for offline analysis",
    ],
    mockup: AnalyticsMockup,
    accentFrom: "from-indigo-500",
    accentTo: "to-purple-600",
  },
  {
    id: "integrations",
    icon: Plug,
    title: "Integrations",
    headline: "Connect your favorite tools",
    description: "One-click connections to Stripe, ClassPass, Zoom, SendGrid, Twilio, Google Ads, and payroll providers like Gusto and QuickBooks. Manage all connections in one place.",
    features: [
      "Stripe Connect for payment processing",
      "ClassPass marketplace integration",
      "Zoom for virtual class hosting and recording",
      "SendGrid/Twilio for email and SMS delivery",
      "Gusto and QuickBooks for payroll and accounting",
    ],
    mockup: IntegrationsMockup,
    accentFrom: "from-gray-500",
    accentTo: "to-slate-600",
  },
  {
    id: "import",
    icon: Upload,
    title: "Data Import",
    headline: "Migrate your data in minutes",
    description: "CSV import for members, classes, instructors, memberships, and attendance. Dry-run preview shows exactly what will be imported before you commit.",
    features: [
      "CSV upload for Members, Classes, Instructors, Memberships, Attendance",
      "Column mapping with auto-detection",
      "Dry-run preview showing parsed data before import",
      "Progress tracking with row-by-row status",
      "Error reporting with row-level detail",
    ],
    mockup: ImportMockup,
    accentFrom: "from-violet-500",
    accentTo: "to-indigo-600",
  },
  {
    id: "settings",
    icon: Settings,
    title: "Settings",
    headline: "Configure every detail",
    description: "Studio settings, billing configuration, communication preferences, and multi-location management — all organized in intuitive tabs.",
    features: [
      "General settings: name, timezone, currency, defaults",
      "Billing configuration and Stripe account management",
      "Communication preferences for email and SMS",
      "Location management for multi-studio operations",
      "Cancellation policies and booking rules",
    ],
    mockup: SettingsMockup,
    accentFrom: "from-slate-500",
    accentTo: "to-gray-600",
  },
];

/* ━━━ Tour Page Component ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

export default function TourPage() {
  const [activeIdx, setActiveIdx] = useState(0);
  const sectionRefs = useRef<(HTMLDivElement | null)[]>([]);
  const active = SECTIONS[activeIdx];

  // Scroll to section when sidebar is clicked
  const scrollTo = (idx: number) => {
    setActiveIdx(idx);
    sectionRefs.current[idx]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Update active section on scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = sectionRefs.current.indexOf(entry.target as HTMLDivElement);
            if (idx !== -1) setActiveIdx(idx);
          }
        }
      },
      { rootMargin: "-40% 0px -50% 0px", threshold: 0 }
    );

    sectionRefs.current.forEach((ref) => {
      if (ref) observer.observe(ref);
    });

    return () => observer.disconnect();
  }, []);

  return (
    <div className="min-h-screen bg-white">
      {/* ── Top Bar ─────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-gray-200 bg-white/90 backdrop-blur-lg">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Link href="/">
            <Image src="/logo.png" alt="AuraFlow" width={120} height={34} priority />
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/" className="hidden text-sm font-medium text-gray-500 hover:text-gray-900 sm:block">
              Home
            </Link>
            <Link
              href="/signup"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 hover:bg-indigo-700"
            >
              Start Free Trial
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ──────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-800 px-6 py-16 text-center">
        <div className="pointer-events-none absolute inset-0">
          <div className="animate-float absolute -left-20 -top-20 h-60 w-60 rounded-full bg-white/10 blur-3xl" />
          <div className="animate-float-delayed absolute -right-20 bottom-0 h-48 w-48 rounded-full bg-purple-400/15 blur-3xl" />
        </div>
        <div className="relative">
          <h1 className="text-4xl font-extrabold text-white sm:text-5xl">
            See every feature in action
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-indigo-100">
            Walk through all 20 modules of the AuraFlow platform —
            from scheduling to AI-powered insights.
          </p>
          <button
            onClick={() => scrollTo(0)}
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-bold text-indigo-700 shadow-xl transition-all hover:-translate-y-0.5 hover:shadow-2xl"
          >
            Start the Tour
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </section>

      {/* ── Main Tour Layout ──────────────────────────────────────────── */}
      <div className="mx-auto max-w-7xl lg:flex">
        {/* Sidebar nav */}
        <aside className="sticky top-[57px] hidden h-[calc(100vh-57px)] w-56 flex-shrink-0 overflow-y-auto border-r border-gray-100 bg-gray-50/50 py-4 lg:block">
          <nav className="space-y-0.5 px-2">
            {SECTIONS.map((s, i) => (
              <button
                key={s.id}
                onClick={() => scrollTo(i)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-all ${
                  i === activeIdx
                    ? "bg-indigo-50 font-semibold text-indigo-700"
                    : "text-gray-500 hover:bg-gray-100 hover:text-gray-800"
                }`}
              >
                <s.icon className={`h-4 w-4 flex-shrink-0 ${i === activeIdx ? "text-indigo-600" : "text-gray-400"}`} />
                <span className="truncate">{s.title}</span>
                {i === activeIdx && (
                  <ChevronRight className="ml-auto h-3.5 w-3.5 text-indigo-400" />
                )}
              </button>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <main className="flex-1 px-4 sm:px-8 py-8">
          {SECTIONS.map((section, sIdx) => (
            <div
              key={section.id}
              ref={(el) => { sectionRefs.current[sIdx] = el; }}
              className="mb-20 scroll-mt-[80px]"
            >
              {/* Section number & badge */}
              <div className="mb-6 flex items-center gap-3">
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${section.accentFrom} ${section.accentTo} shadow-lg`}>
                  <section.icon className="h-5 w-5 text-white" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-gray-400">
                    {String(sIdx + 1).padStart(2, "0")} / {SECTIONS.length}
                  </span>
                  <h2 className="text-2xl font-extrabold text-gray-900 sm:text-3xl">
                    {section.headline}
                  </h2>
                </div>
              </div>

              <p className="mb-8 max-w-2xl text-gray-500 leading-relaxed">
                {section.description}
              </p>

              {/* Mockup + Features side by side */}
              <div className="grid gap-8 lg:grid-cols-5">
                {/* Mockup — takes 3 of 5 cols */}
                <div className="lg:col-span-3">
                  <section.mockup />
                </div>

                {/* Features — takes 2 of 5 cols */}
                <div className="lg:col-span-2">
                  <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-gray-400">
                    Key Features
                  </h3>
                  <ul className="space-y-3">
                    {section.features.map((feat) => (
                      <li key={feat} className="flex items-start gap-3">
                        <div className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${section.accentFrom} ${section.accentTo}`}>
                          <Check className="h-3 w-3 text-white" />
                        </div>
                        <span className="text-sm text-gray-600">{feat}</span>
                      </li>
                    ))}
                  </ul>

                  {/* Navigate to next */}
                  {sIdx < SECTIONS.length - 1 && (
                    <button
                      onClick={() => scrollTo(sIdx + 1)}
                      className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-indigo-600 hover:text-indigo-700"
                    >
                      Next: {SECTIONS[sIdx + 1].title}
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Divider */}
              {sIdx < SECTIONS.length - 1 && (
                <hr className="mt-16 border-gray-100" />
              )}
            </div>
          ))}

          {/* ── Final CTA ─────────────────────────────────────────────── */}
          <div className="relative mt-8 overflow-hidden rounded-2xl bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-700 px-8 py-16 text-center">
            <div className="pointer-events-none absolute inset-0">
              <div className="absolute -right-20 -top-20 h-48 w-48 rounded-full bg-white/10 blur-3xl" />
              <div className="absolute -bottom-20 -left-20 h-48 w-48 rounded-full bg-purple-400/10 blur-3xl" />
            </div>
            <div className="relative">
              <h2 className="text-3xl font-extrabold text-white sm:text-4xl">
                Ready to transform your studio?
              </h2>
              <p className="mx-auto mt-4 max-w-lg text-indigo-100">
                All 20 modules. One platform. Start your free 14-day trial —
                no credit card required.
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
                  href="/"
                  className="inline-flex items-center gap-2 rounded-xl border border-white/30 bg-white/10 px-8 py-4 text-sm font-bold text-white backdrop-blur-sm transition-all hover:bg-white/20"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back to Home
                </Link>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
