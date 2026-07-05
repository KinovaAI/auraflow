import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Providers } from "@/components/providers";
import { JsonLd } from "@/components/json-ld";
import { AnalyticsScripts } from "@/components/tracking/analytics-scripts";
import "@/styles/globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "AuraFlow — Studio Management Platform",
    template: "%s | AuraFlow",
  },
  description:
    "The AI-powered studio management platform. Scheduling, memberships, payments, video, teacher training, and more.",
  verification: {
    google: "T6ECEogQdAHMYQJ6Na-FzRIukC1tue1djwvwIcYg9Ak",
  },
  manifest: "/manifest.json",
  icons: {
    icon: "/icon.svg",
    apple: "/apple-icon",
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://auraflow.fit",
    siteName: "AuraFlow",
    title: "AuraFlow — AI-Powered Studio Management Platform",
    description: "The AI-powered alternative to MindBody. Scheduling, memberships, payments, video, and more.",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AuraFlow — AI-Powered Studio Management Platform",
    description: "The AI-powered alternative to MindBody. Scheduling, memberships, payments, video, and more.",
    images: ["https://auraflow.fit/og-image.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#4F46E5",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <head>
        <JsonLd />
      </head>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
        <AnalyticsScripts />
      </body>
    </html>
  );
}
