import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Platform Tour — See AuraFlow Studio Management in Action",
  description:
    "Explore AuraFlow's AI-powered features: smart scheduling, automated check-in, membership management, payment processing, video library, and more.",
  alternates: { canonical: "https://auraflow.fit/tour" },
  openGraph: {
    title: "Platform Tour — See AuraFlow Studio Management in Action",
    description:
      "Explore AuraFlow's AI-powered features: smart scheduling, automated check-in, membership management, payment processing, video library, and more.",
    url: "https://auraflow.fit/tour",
    images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Platform Tour — See AuraFlow Studio Management in Action",
    description:
      "Explore AuraFlow's AI-powered features: smart scheduling, automated check-in, membership management, payment processing, video library, and more.",
  },
};

export default function TourLayout({ children }: { children: React.ReactNode }) {
  return children;
}
