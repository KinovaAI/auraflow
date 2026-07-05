import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Get Started — Set Up Your Studio on AuraFlow",
  description:
    "Set up your yoga, fitness, or wellness studio on AuraFlow in minutes. AI-powered scheduling, payments, and member management.",
  alternates: { canonical: "https://auraflow.fit/onboarding" },
  openGraph: {
    title: "Get Started — Set Up Your Studio on AuraFlow",
    description:
      "Set up your yoga, fitness, or wellness studio on AuraFlow in minutes. AI-powered scheduling, payments, and member management.",
    url: "https://auraflow.fit/onboarding",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Get Started — Set Up Your Studio on AuraFlow",
    description:
      "Set up your yoga, fitness, or wellness studio on AuraFlow in minutes. AI-powered scheduling, payments, and member management.",
  },
};

export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
