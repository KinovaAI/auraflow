"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  CreditCard,
  FileText,
  Download,
  ExternalLink,
  Receipt,
  ArrowUpCircle,
  ArrowDownCircle,
  Sparkles,
  Check,
  X,
  AlertTriangle,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { paymentsApi, type PlatformInvoice } from "@/lib/payments-api";
import { apiClient } from "@/lib/api-client";
import { SquareBillingSection } from "@/components/billing/square-billing-section";
import { ManagedBillingSection } from "@/components/billing/managed-billing-section";

// ── Types ────────────────────────────────────────────────────────────────────

interface Plan {
  id: string;
  name: string;
  price_cents: number;
  price_display: string;
  interval: string;
  tagline: string;
  features: string[];
  limits: Record<string, number>;
  popular?: boolean;
}

interface CurrentBilling {
  plan_id: string;
  plan_name: string;
  plan_price_cents: number;
  plan_price_display: string;
  status: string;
  has_stripe_subscription: boolean;
  trial_ends_at?: string | null;
  subscription_status?: string | null;
  current_period_end?: string | null;
  cancel_at_period_end?: boolean | null;
}

interface PlanChangePreview {
  current_plan_id: string;
  new_plan_id: string;
  direction: string;
  new_price_cents: number;
  new_price_display: string;
  proration_amount_cents?: number | null;
  immediate_charge: boolean;
}

interface PlanChangeResult {
  previous_plan_id: string;
  new_plan_id: string;
  direction: string;
  new_price_display: string;
  subscription_id?: string | null;
  message: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function InvoiceStatusBadge({ status }: { status: PlatformInvoice["status"] }) {
  const styles: Record<string, string> = {
    paid: "bg-green-50 text-green-700",
    open: "bg-yellow-50 text-yellow-700",
    draft: "bg-gray-100 text-gray-500",
    void: "bg-red-50 text-red-600",
    uncollectible: "bg-red-50 text-red-600",
  };

  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        styles[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {status}
    </span>
  );
}

function formatCurrency(amountCents: number, currency: string = "usd") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(amountCents / 100);
}

function PlanStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; style: string }> = {
    trial: {
      label: "Trial",
      style: "bg-blue-50 text-blue-700",
    },
    active: {
      label: "Active",
      style: "bg-green-50 text-green-700",
    },
    suspended: {
      label: "Suspended",
      style: "bg-red-50 text-red-600",
    },
    cancelled: {
      label: "Cancelled",
      style: "bg-gray-100 text-gray-500",
    },
  };
  const info = map[status] || { label: status, style: "bg-gray-100 text-gray-500" };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${info.style}`}>
      {info.label}
    </span>
  );
}

// ── Confirmation Modal ───────────────────────────────────────────────────────

function PlanChangeModal({
  plan,
  preview,
  previewLoading,
  direction,
  onConfirm,
  onCancel,
  isSubmitting,
}: {
  plan: Plan;
  preview: PlanChangePreview | null;
  previewLoading: boolean;
  direction: string;
  onConfirm: () => void;
  onCancel: () => void;
  isSubmitting: boolean;
}) {
  const isUpgrade = direction === "upgrade";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2">
            {isUpgrade ? (
              <ArrowUpCircle className="h-5 w-5 text-indigo-600" />
            ) : (
              <ArrowDownCircle className="h-5 w-5 text-amber-600" />
            )}
            <h3 className="text-lg font-semibold text-gray-900">
              {isUpgrade ? "Upgrade" : "Downgrade"} to {plan.name}
            </h3>
          </div>
          <button
            onClick={onCancel}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div className="rounded-lg bg-gray-50 p-4">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium text-gray-700">
                {plan.name} Plan
              </span>
              <span className="text-xl font-bold text-gray-900">
                {plan.price_display}
                <span className="text-sm font-normal text-gray-500">/mo</span>
              </span>
            </div>
            <p className="mt-1 text-xs text-gray-500">{plan.tagline}</p>
          </div>

          {previewLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
              <span className="ml-2 text-sm text-gray-500">
                Calculating proration...
              </span>
            </div>
          ) : preview?.proration_amount_cents != null ? (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
              <p className="text-sm font-medium text-indigo-900">
                Proration adjustment
              </p>
              <p className="mt-1 text-2xl font-bold text-indigo-700">
                {formatCurrency(preview.proration_amount_cents)}
              </p>
              <p className="mt-1 text-xs text-indigo-600">
                {isUpgrade
                  ? "This amount will be charged now, reflecting the remaining time in your current billing period."
                  : "This credit will be applied to your next invoice."}
              </p>
            </div>
          ) : null}

          {!isUpgrade && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
              <p className="text-xs text-amber-800">
                Downgrading may disable features not available on the {plan.name} plan.
                Your data will be preserved, but some functionality will be restricted.
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t bg-gray-50 px-6 py-4">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            disabled={isSubmitting || previewLoading}
            className={
              isUpgrade
                ? "bg-indigo-600 hover:bg-indigo-700"
                : "bg-amber-600 hover:bg-amber-700"
            }
          >
            {isSubmitting && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isUpgrade ? "Confirm Upgrade" : "Confirm Downgrade"}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Plan Card ────────────────────────────────────────────────────────────────

function PlanCard({
  plan,
  isCurrent,
  direction,
  onSelect,
}: {
  plan: Plan;
  isCurrent: boolean;
  direction: "upgrade" | "downgrade" | "same";
  onSelect: (plan: Plan) => void;
}) {
  const isUpgrade = direction === "upgrade";
  const isDowngrade = direction === "downgrade";

  return (
    <div
      className={`relative flex flex-col rounded-xl border-2 p-6 transition-shadow ${
        isCurrent
          ? "border-indigo-600 bg-indigo-50/30 shadow-md"
          : plan.popular
            ? "border-indigo-200 shadow-sm hover:shadow-md"
            : "border-gray-200 hover:shadow-md"
      }`}
    >
      {/* Popular badge */}
      {plan.popular && !isCurrent && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-3 py-1 text-xs font-semibold text-white shadow-sm">
            <Sparkles className="h-3 w-3" />
            Most Popular
          </span>
        </div>
      )}

      {/* Current plan badge */}
      {isCurrent && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600 px-3 py-1 text-xs font-semibold text-white shadow-sm">
            <CheckCircle2 className="h-3 w-3" />
            Current Plan
          </span>
        </div>
      )}

      {/* Plan name and pricing */}
      <div className="mb-4 mt-2 text-center">
        <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
        <p className="mt-1 text-sm text-gray-500">{plan.tagline}</p>
        <div className="mt-4">
          <span className="text-4xl font-extrabold text-gray-900">
            {plan.price_display}
          </span>
          <span className="text-base text-gray-500">/mo</span>
        </div>
      </div>

      {/* Features */}
      <ul className="mb-6 flex-1 space-y-2">
        {plan.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2 text-sm">
            <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-600" />
            <span className="text-gray-600">{feature}</span>
          </li>
        ))}
      </ul>

      {/* Limits */}
      <div className="mb-4 rounded-md bg-gray-50 p-3">
        <div className="flex justify-between text-xs text-gray-500">
          <span>Members</span>
          <span className="font-medium text-gray-700">
            {plan.limits.members === -1
              ? "Unlimited"
              : plan.limits.members.toLocaleString()}
          </span>
        </div>
        <div className="mt-1 flex justify-between text-xs text-gray-500">
          <span>Instructors</span>
          <span className="font-medium text-gray-700">
            {plan.limits.instructors === -1
              ? "Unlimited"
              : plan.limits.instructors}
          </span>
        </div>
        <div className="mt-1 flex justify-between text-xs text-gray-500">
          <span>Locations</span>
          <span className="font-medium text-gray-700">
            {plan.limits.locations === -1
              ? "Unlimited"
              : plan.limits.locations}
          </span>
        </div>
      </div>

      {/* Action button */}
      {isCurrent ? (
        <Button disabled variant="outline" className="w-full">
          Current Plan
        </Button>
      ) : isUpgrade ? (
        <Button
          onClick={() => onSelect(plan)}
          className="w-full bg-indigo-600 hover:bg-indigo-700"
        >
          <ArrowUpCircle className="mr-2 h-4 w-4" />
          Upgrade
        </Button>
      ) : isDowngrade ? (
        <Button
          onClick={() => onSelect(plan)}
          variant="outline"
          className="w-full border-amber-300 text-amber-700 hover:bg-amber-50"
        >
          <ArrowDownCircle className="mr-2 h-4 w-4" />
          Downgrade
        </Button>
      ) : null}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function BillingSettingsPage() {
  const queryClient = useQueryClient();
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);

  // ── Queries ────────────────────────────────────────────────────────

  const { data: billing, isLoading: billingLoading } = useQuery({
    queryKey: ["billing-current"],
    queryFn: () =>
      apiClient
        .get<CurrentBilling>("/organizations/billing/current")
        .then((r) => r.data),
  });

  const { data: plans, isLoading: plansLoading } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: () =>
      apiClient
        .get<Plan[]>("/organizations/billing/plans")
        .then((r) => r.data),
  });

  const {
    data: invoices,
    isLoading: invoicesLoading,
  } = useQuery({
    queryKey: ["billing-invoices"],
    queryFn: () =>
      paymentsApi.listBillingInvoices().then((r) => r.data.data),
  });

  const {
    data: preview,
    isLoading: previewLoading,
  } = useQuery({
    queryKey: ["billing-preview", selectedPlan?.id],
    queryFn: () =>
      apiClient
        .get<PlanChangePreview>(
          `/organizations/billing/preview-change/${selectedPlan!.id}`
        )
        .then((r) => r.data),
    enabled: !!selectedPlan,
  });

  // ── Mutations ──────────────────────────────────────────────────────

  const changePlanMutation = useMutation({
    mutationFn: (planId: string) =>
      apiClient
        .post<PlanChangeResult>("/organizations/billing/change-plan", {
          plan_id: planId,
        })
        .then((r) => r.data),
    onSuccess: (result) => {
      toast.success(result.message);
      setSelectedPlan(null);
      queryClient.invalidateQueries({ queryKey: ["billing-current"] });
      queryClient.invalidateQueries({ queryKey: ["billing-plans"] });
      queryClient.invalidateQueries({ queryKey: ["billing-invoices"] });
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || "Failed to change plan";
      toast.error(detail);
    },
  });

  // ── Loading state ──────────────────────────────────────────────────

  if (billingLoading || plansLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  const currentPlanId = billing?.plan_id || "trial";
  const planOrder = ["starter", "growth", "scale", "enterprise"];

  function getDirection(planId: string): "upgrade" | "downgrade" | "same" {
    if (planId === currentPlanId) return "same";
    const currentIdx = planOrder.indexOf(currentPlanId);
    const newIdx = planOrder.indexOf(planId);
    return newIdx > currentIdx ? "upgrade" : "downgrade";
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      {/* Payment Processor — Square / Stripe Connect status + invoice history */}
      <SquareBillingSection />

      {/* Managed billing (open-core self-host, AURAFLOW_BILLING_MODE=managed) */}
      <ManagedBillingSection />

      {/* Current Plan Summary */}
      {billing && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-indigo-600" />
                <CardTitle className="text-base">
                  Current Plan
                </CardTitle>
              </div>
              <PlanStatusBadge status={billing.status} />
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-6">
              <div>
                <p className="text-2xl font-bold text-gray-900">
                  {billing.plan_name}
                </p>
                <p className="text-sm text-gray-500">
                  {billing.plan_price_display}/month
                </p>
              </div>
              {billing.current_period_end && (
                <div className="rounded-md bg-gray-50 px-4 py-2">
                  <p className="text-xs text-gray-500">Next billing date</p>
                  <p className="text-sm font-medium text-gray-900">
                    {format(
                      new Date(billing.current_period_end),
                      "MMMM d, yyyy"
                    )}
                  </p>
                </div>
              )}
              {billing.trial_ends_at && billing.status === "trial" && (
                <div className="rounded-md bg-blue-50 px-4 py-2">
                  <p className="text-xs text-blue-600">Trial ends</p>
                  <p className="text-sm font-medium text-blue-900">
                    {format(
                      new Date(billing.trial_ends_at),
                      "MMMM d, yyyy"
                    )}
                  </p>
                </div>
              )}
              {billing.cancel_at_period_end && (
                <div className="rounded-md bg-red-50 px-4 py-2">
                  <p className="text-xs text-red-600">
                    Cancels at end of period
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Plan Selection Cards */}
      {plans && plans.length > 0 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold text-gray-900">
            Available Plans
          </h2>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                isCurrent={plan.id === currentPlanId}
                direction={getDirection(plan.id)}
                onSelect={setSelectedPlan}
              />
            ))}
          </div>
        </div>
      )}

      {/* Platform Invoices Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Receipt className="h-5 w-5 text-indigo-600" />
            <CardTitle className="text-base">Billing History</CardTitle>
          </div>
          <p className="text-xs text-gray-400">
            Invoices for your AuraFlow platform subscription
          </p>
        </CardHeader>
        <CardContent>
          {invoicesLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : !invoices?.length ? (
            <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
              <FileText className="mx-auto h-8 w-8 text-gray-300" />
              <p className="mt-2 text-sm text-gray-500">No invoices yet</p>
              <p className="mt-1 text-xs text-gray-400">
                Invoices will appear here once your subscription generates them
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Date
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Invoice
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Period
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      Amount
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                      PDF
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {invoices.map((inv) => (
                    <tr key={inv.id} className="hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {format(new Date(inv.created * 1000), "MMM d, yyyy")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-900">
                        {inv.number || "--"}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                        {format(new Date(inv.period_start * 1000), "MMM d")}
                        {" - "}
                        {format(new Date(inv.period_end * 1000), "MMM d, yyyy")}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-sm font-medium text-gray-900">
                        {formatCurrency(inv.amount_due, inv.currency)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <InvoiceStatusBadge status={inv.status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {inv.invoice_pdf && (
                            <a
                              href={inv.invoice_pdf}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-gray-400 hover:text-indigo-600"
                              title="Download PDF"
                            >
                              <Download className="h-4 w-4" />
                            </a>
                          )}
                          {inv.hosted_invoice_url && (
                            <a
                              href={inv.hosted_invoice_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-gray-400 hover:text-indigo-600"
                              title="View invoice"
                            >
                              <ExternalLink className="h-4 w-4" />
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Plan Change Confirmation Modal */}
      {selectedPlan && (
        <PlanChangeModal
          plan={selectedPlan}
          preview={preview || null}
          previewLoading={previewLoading}
          direction={getDirection(selectedPlan.id)}
          onConfirm={() => changePlanMutation.mutate(selectedPlan.id)}
          onCancel={() => setSelectedPlan(null)}
          isSubmitting={changePlanMutation.isPending}
        />
      )}
    </div>
  );
}
