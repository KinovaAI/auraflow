import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { BookOpen, HelpCircle, ArrowLeft } from "lucide-react";

export const metadata: Metadata = {
  title: "Documentation — AuraFlow Studio Management Platform",
  description:
    "Complete documentation for AuraFlow studio management. API reference, setup guides, integration docs, and feature walkthroughs.",
  alternates: { canonical: "https://auraflow.fit/docs" },
  openGraph: {
    title: "Documentation — AuraFlow Studio Management Platform",
    description:
      "Complete documentation for AuraFlow studio management. API reference, setup guides, integration docs, and feature walkthroughs.",
    url: "https://auraflow.fit/docs",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Documentation — AuraFlow Studio Management Platform",
    description:
      "Complete documentation for AuraFlow studio management. API reference, setup guides, integration docs, and feature walkthroughs.",
  },
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-white">
      {/* Top nav */}
      <nav className="sticky top-0 z-50 border-b border-gray-200 bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2">
              <Image src="/logo.png" alt="AuraFlow" width={100} height={29} />
            </Link>
            <span className="hidden text-sm text-gray-300 sm:inline">|</span>
            <span className="hidden text-sm font-medium text-gray-600 sm:inline">Documentation</span>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/docs"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
            >
              <BookOpen className="h-4 w-4" />
              <span className="hidden sm:inline">User Guide</span>
            </Link>
            <Link
              href="/docs/faq"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
            >
              <HelpCircle className="h-4 w-4" />
              <span className="hidden sm:inline">FAQ</span>
            </Link>
            <Link
              href="/"
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Home
            </Link>
            <Link
              href="/login"
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
            >
              Go to App
            </Link>
          </div>
        </div>
      </nav>
      {children}
    </div>
  );
}
