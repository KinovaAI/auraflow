export function JsonLd() {
  const organizationSchema = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "AuraFlow",
    url: "https://auraflow.fit",
    logo: "https://auraflow.fit/icon.svg",
    description:
      "The AI-powered studio management platform for yoga, fitness, and wellness studios.",
    // Add social profile URLs here when available
    sameAs: [],
  };

  const softwareSchema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "AuraFlow",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    url: "https://auraflow.fit",
    description:
      "AI-powered studio management platform. Scheduling, memberships, payments, video, teacher training, and more.",
    offers: [
      {
        "@type": "Offer",
        name: "Starter",
        price: "99",
        priceCurrency: "USD",
        description: "For solo instructors",
      },
      {
        "@type": "Offer",
        name: "Growth",
        price: "149",
        priceCurrency: "USD",
        description: "For growing studios",
      },
      {
        "@type": "Offer",
        name: "Scale",
        price: "199",
        priceCurrency: "USD",
        description: "For multi-location studios",
      },
    ],
    aggregateRating: {
      "@type": "AggregateRating",
      ratingValue: "4.9",
      reviewCount: "50",
    },
  };

  const faqSchema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "How do I create an AuraFlow account for my studio?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Visit the AuraFlow signup page and choose the plan that fits your studio. Enter your studio details and create your owner account. Once registered, you'll be guided through a setup checklist that helps you configure your class schedule, add staff, import existing members, and connect payments.",
        },
      },
      {
        "@type": "Question",
        name: "What types of memberships can I create?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "AuraFlow supports Unlimited plans, Class Packs (prepaid bundles), Drop-In (single-visit), and Day Pass. Create custom plans that restrict access to specific class categories. Set up tiered pricing, student discounts, family plans, and intro offers for new members.",
        },
      },
      {
        "@type": "Question",
        name: "How does payment processing work with Stripe?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "AuraFlow uses Stripe for secure payment processing. Members can pay by credit or debit card. Recurring memberships are auto-billed through Stripe. Stripe Connect allows each studio to have its own merchant account with funds deposited on Stripe's standard payout schedule.",
        },
      },
      {
        "@type": "Question",
        name: "What can the AI chatbot assistant do?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The AI assistant analyzes your real-time data and provides accurate answers to questions about revenue, members, and class popularity. It can look up member records, navigate you to the right page, and help with tasks like drafting marketing content.",
        },
      },
      {
        "@type": "Question",
        name: "Is there a mobile app?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "AuraFlow is built as a Progressive Web App (PWA). It works on all devices through the browser. On mobile, add AuraFlow to your home screen for an app-like experience with a custom icon and full-screen mode. No app store download needed.",
        },
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(organizationSchema),
        }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(softwareSchema),
        }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(faqSchema),
        }}
      />
    </>
  );
}
