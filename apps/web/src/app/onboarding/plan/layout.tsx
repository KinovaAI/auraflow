import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Choose Your Plan — AuraFlow Studio Management Pricing",
  description:
    "AuraFlow pricing plans for yoga, fitness, and wellness studios. Start at $99/month. 14-day free trial. No credit card required.",
  alternates: { canonical: "https://auraflow.fit/onboarding/plan" },
  openGraph: {
    title: "Choose Your Plan — AuraFlow Studio Management Pricing",
    description:
      "AuraFlow pricing plans for yoga, fitness, and wellness studios. Start at $99/month. 14-day free trial. No credit card required.",
    url: "https://auraflow.fit/onboarding/plan",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Choose Your Plan — AuraFlow Studio Management Pricing",
    description:
      "AuraFlow pricing plans for yoga, fitness, and wellness studios. Start at $99/month. 14-day free trial. No credit card required.",
  },
};

export default function PlanLayout({ children }: { children: React.ReactNode }) {
  return children;
}
