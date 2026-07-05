import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Contact AuraFlow — Get Started with Your Studio Software",
  description:
    "Contact the AuraFlow team. Get a demo, ask questions, or start your 14-day free trial of the AI-powered studio management platform.",
  alternates: { canonical: "https://auraflow.fit/contact" },
  openGraph: {
    title: "Contact AuraFlow — Get Started with Your Studio Software",
    description:
      "Contact the AuraFlow team. Get a demo, ask questions, or start your 14-day free trial of the AI-powered studio management platform.",
    url: "https://auraflow.fit/contact",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Contact AuraFlow — Get Started with Your Studio Software",
    description:
      "Contact the AuraFlow team. Get a demo, ask questions, or start your 14-day free trial of the AI-powered studio management platform.",
  },
};

export default function ContactLayout({ children }: { children: React.ReactNode }) {
  return children;
}
