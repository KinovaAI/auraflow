import { notFound } from "next/navigation";
import Link from "next/link";
import { Check, ArrowRight, Star } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Feature {
  title: string;
  description: string;
}

interface Testimonial {
  quote: string;
  author: string;
  role: string;
}

interface LandingPageData {
  id: string;
  slug: string;
  title: string;
  hero_headline: string | null;
  hero_subheadline: string | null;
  hero_cta_text: string;
  hero_cta_url: string | null;
  features_json: Feature[];
  testimonials_json: Testimonial[];
  meta_title: string | null;
  meta_description: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
}

async function getPage(slug: string): Promise<LandingPageData | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/lp/${slug}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json.data;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = await getPage(slug);
  if (!page) return { title: "Page Not Found" };
  const title = page.meta_title || page.title;
  const description = page.meta_description || page.hero_subheadline || "";
  return {
    title,
    description,
    alternates: { canonical: `https://auraflow.fit/lp/${slug}` },
    openGraph: {
      title,
      description,
      url: `https://auraflow.fit/lp/${slug}`,
      images: [{ url: "https://auraflow.fit/og-image.png", width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image" as const,
      title,
      description,
    },
  };
}

const PRICING = [
  { name: "Starter", price: "$79", period: "/mo", features: ["1 Location", "Class Scheduling", "Member Management", "Basic Analytics", "Email Support"] },
  { name: "Growth", price: "$129", period: "/mo", features: ["Up to 3 Locations", "Everything in Starter", "Private Sessions", "Payments & POS", "Video Library", "Marketing Tools"], popular: true },
  { name: "Scale", price: "$199", period: "/mo", features: ["Up to 10 Locations", "Everything in Growth", "AI Marketing Manager", "Google & Meta Ads", "Advanced Analytics", "Priority Support"] },
  { name: "Enterprise", price: "$399", period: "/mo", features: ["Unlimited Locations", "Everything in Scale", "Dedicated Account Manager", "Custom Integrations", "White-label Options", "SLA Guarantee"] },
];

export default async function PublicLandingPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = await getPage(slug);
  if (!page) notFound();

  const ctaUrl = page.hero_cta_url || "https://auraflow.fit/signup";
  const utm = [
    page.utm_source && `utm_source=${page.utm_source}`,
    page.utm_medium && `utm_medium=${page.utm_medium}`,
    page.utm_campaign && `utm_campaign=${page.utm_campaign}`,
  ].filter(Boolean).join("&");
  const ctaHref = utm ? `${ctaUrl}${ctaUrl.includes("?") ? "&" : "?"}${utm}` : ctaUrl;

  return (
    <div className="min-h-screen bg-white">
      {/* ── Nav ──────────────────────────────────────────────────────── */}
      <nav className="border-b border-gray-100 bg-white/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="text-xl font-bold">
            <span className="text-indigo-600">Aura</span>
            <span className="text-gray-900">Flow</span>
          </Link>
          <a
            href={ctaHref}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors"
          >
            {page.hero_cta_text || "Get Started"}
          </a>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-500 py-24 text-white">
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PHBhdHRlcm4gaWQ9ImciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgcGF0dGVyblVuaXRzPSJ1c2VyU3BhY2VPblVzZSI+PGNpcmNsZSBjeD0iMzAiIGN5PSIzMCIgcj0iMSIgZmlsbD0icmdiYSgyNTUsMjU1LDI1NSwwLjEpIi8+PC9wYXR0ZXJuPjwvZGVmcz48cmVjdCBmaWxsPSJ1cmwoI2cpIiB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIi8+PC9zdmc+')] opacity-50" />
        <div className="relative mx-auto max-w-4xl px-6 text-center">
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl">
            {page.hero_headline || page.title}
          </h1>
          {page.hero_subheadline && (
            <p className="mx-auto mt-6 max-w-2xl text-lg text-white/90 sm:text-xl">
              {page.hero_subheadline}
            </p>
          )}
          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <a
              href={ctaHref}
              className="inline-flex items-center gap-2 rounded-xl bg-white px-8 py-4 text-lg font-bold text-indigo-600 shadow-xl hover:bg-gray-50 transition-colors"
            >
              {page.hero_cta_text || "Get Started"} <ArrowRight className="h-5 w-5" />
            </a>
            <span className="text-sm text-white/70">No credit card required</span>
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────────── */}
      {page.features_json?.length > 0 && (
        <section className="py-20">
          <div className="mx-auto max-w-6xl px-6">
            <h2 className="text-center text-3xl font-bold text-gray-900">
              Everything you need to grow your studio
            </h2>
            <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {page.features_json.map((f, i) => (
                <div key={i} className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm hover:shadow-md transition-shadow">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                    <Check className="h-5 w-5" />
                  </div>
                  <h3 className="mt-4 text-lg font-semibold text-gray-900">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-600">{f.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Pricing ──────────────────────────────────────────────────── */}
      <section className="bg-gray-50 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold text-gray-900">Simple, transparent pricing</h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-gray-500">
            Start free for 14 days. No credit card required.
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {PRICING.map((plan) => (
              <div
                key={plan.name}
                className={`relative rounded-2xl border bg-white p-6 ${
                  plan.popular ? "border-indigo-400 ring-2 ring-indigo-400 shadow-lg" : "border-gray-200"
                }`}
              >
                {plan.popular && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-xs font-semibold text-white">
                    Most Popular
                  </span>
                )}
                <h3 className="text-lg font-semibold text-gray-900">{plan.name}</h3>
                <div className="mt-2">
                  <span className="text-3xl font-bold text-gray-900">{plan.price}</span>
                  <span className="text-sm text-gray-500">{plan.period}</span>
                </div>
                <ul className="mt-6 space-y-3">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                      <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-500" />
                      {f}
                    </li>
                  ))}
                </ul>
                <a
                  href={ctaHref}
                  className={`mt-6 block rounded-lg px-4 py-2.5 text-center text-sm font-semibold transition-colors ${
                    plan.popular
                      ? "bg-indigo-600 text-white hover:bg-indigo-700"
                      : "border border-gray-300 text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  Start Free Trial
                </a>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Testimonials ─────────────────────────────────────────────── */}
      {page.testimonials_json?.length > 0 && (
        <section className="py-20">
          <div className="mx-auto max-w-6xl px-6">
            <h2 className="text-center text-3xl font-bold text-gray-900">
              Trusted by studio owners everywhere
            </h2>
            <div className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {page.testimonials_json.map((t, i) => (
                <div key={i} className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
                  <div className="flex gap-1">
                    {[...Array(5)].map((_, s) => (
                      <Star key={s} className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                    ))}
                  </div>
                  <blockquote className="mt-4 text-sm leading-relaxed text-gray-700">
                    &ldquo;{t.quote}&rdquo;
                  </blockquote>
                  <div className="mt-4 border-t border-gray-100 pt-4">
                    <p className="text-sm font-semibold text-gray-900">{t.author}</p>
                    <p className="text-xs text-gray-500">{t.role}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ── Final CTA ────────────────────────────────────────────────── */}
      <section className="bg-gradient-to-r from-indigo-600 to-purple-600 py-16">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-3xl font-bold text-white">Ready to transform your studio?</h2>
          <p className="mt-3 text-lg text-white/80">
            Join hundreds of studio owners who trust AuraFlow to run their business.
          </p>
          <a
            href={ctaHref}
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white px-8 py-4 text-lg font-bold text-indigo-600 shadow-xl hover:bg-gray-50 transition-colors"
          >
            {page.hero_cta_text || "Get Started"} <ArrowRight className="h-5 w-5" />
          </a>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-gray-100 bg-white py-8">
        <div className="mx-auto max-w-6xl px-6 text-center text-sm text-gray-400">
          &copy; {new Date().getFullYear()} AuraFlow. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
