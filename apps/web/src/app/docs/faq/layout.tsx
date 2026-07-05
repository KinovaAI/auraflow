import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "FAQ — AuraFlow Studio Management Software",
  description:
    "Frequently asked questions about AuraFlow studio management platform. Pricing, features, migration from MindBody, integrations, and support.",
  alternates: { canonical: "https://auraflow.fit/docs/faq" },
  openGraph: {
    title: "FAQ — AuraFlow Studio Management Software",
    description:
      "Frequently asked questions about AuraFlow studio management platform. Pricing, features, migration from MindBody, integrations, and support.",
    url: "https://auraflow.fit/docs/faq",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "FAQ — AuraFlow Studio Management Software",
    description:
      "Frequently asked questions about AuraFlow studio management platform. Pricing, features, migration from MindBody, integrations, and support.",
  },
};

export default function FAQLayout({ children }: { children: React.ReactNode }) {
  return children;
}
