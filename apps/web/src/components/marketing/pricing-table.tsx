"use client";

import Link from "next/link";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Plan {
  id: string;
  name: string;
  price: number | null;
  priceDisplay?: string;
  priceNote?: string;
  description: string;
  features: string[];
  highlighted?: boolean;
  contactSales?: boolean;
}

const PLANS: Plan[] = [
  {
    id: "studio",
    name: "Studio",
    price: 99,
    description: "The full white-label platform for up to 10 locations",
    features: [
      "Up to 10 studio locations",
      "Unlimited classes, members & instructors",
      "Full white-label branding",
      "Full RESTful API for custom integrations",
      "Zoom live-streaming & on-demand video",
      "AI-powered studio management",
      "Private sessions with payment links",
      "POS, gift cards & retail",
      "Email & SMS campaigns",
      "Workshops & teacher training",
      "ClassPass & EMR integrations",
      "Advanced analytics & churn prediction",
      "Priority support",
    ],
    highlighted: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: null,
    priceDisplay: "Custom",
    description: "For franchise chains and large studio networks",
    features: [
      "Everything in Studio",
      "Unlimited locations",
      "Dedicated account manager",
      "Custom onboarding & migration",
      "SLA guarantee",
      "Advanced security & compliance",
      "Custom feature development",
    ],
    contactSales: true,
  },
];

interface PricingTableProps {
  onSelectPlan?: (planId: string) => void;
}

export function PricingTable({ onSelectPlan }: PricingTableProps) {
  return (
    <div className="mx-auto grid max-w-4xl gap-8 md:grid-cols-2">
      {PLANS.map((plan) => (
        <div
          key={plan.id}
          className={`relative flex flex-col rounded-xl border p-6 ${
            plan.highlighted
              ? "border-indigo-600 ring-2 ring-indigo-600"
              : "border-gray-200"
          }`}
        >
          {plan.highlighted && (
            <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 px-3 py-0.5 text-xs font-medium text-white">
              Most Popular
            </div>
          )}

          <div className="mb-4">
            <h3 className="text-lg font-semibold text-gray-900">{plan.name}</h3>
            <p className="mt-1 text-sm text-gray-500">{plan.description}</p>
          </div>

          <div className="mb-6 h-16 flex flex-col justify-start">
            {plan.price !== null ? (
              <>
                <div>
                  <span className="text-4xl font-bold text-gray-900">${plan.price}</span>
                  <span className="text-sm text-gray-500">/month</span>
                </div>
                {plan.priceNote ? (
                  <p className="mt-1 text-xs text-gray-400">{plan.priceNote}</p>
                ) : (
                  <p className="mt-1 text-xs text-gray-400">&nbsp;</p>
                )}
              </>
            ) : (
              <>
                <div>
                  <span className="text-4xl font-bold text-gray-900">
                    {plan.priceDisplay || "Contact us"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-400">&nbsp;</p>
              </>
            )}
          </div>

          <ul className="mb-8 flex-1 space-y-3">
            {plan.features.map((feature) => (
              <li key={feature} className="flex items-start gap-2 text-sm text-gray-600">
                <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-600" />
                {feature}
              </li>
            ))}
          </ul>

          {plan.contactSales ? (
            <Link href="/contact">
              <Button variant="outline" className="w-full">
                Contact Sales
              </Button>
            </Link>
          ) : onSelectPlan ? (
            <Button
              onClick={() => onSelectPlan(plan.id)}
              variant={plan.highlighted ? "default" : "outline"}
              className="w-full"
            >
              Start Free Trial
            </Button>
          ) : (
            <Link href={`/signup?plan=${plan.id}`}>
              <Button
                variant={plan.highlighted ? "default" : "outline"}
                className="w-full"
              >
                Start Free Trial
              </Button>
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}
