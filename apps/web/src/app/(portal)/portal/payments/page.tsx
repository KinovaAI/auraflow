"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Loader2,
  Receipt,
  Download,
  CheckCircle2,
  Clock,
  XCircle,
} from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import { Card, CardContent } from "@/components/ui/card";

function formatCents(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function statusBadge(status: string) {
  switch (status) {
    case "succeeded":
    case "paid":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
          <CheckCircle2 className="h-3 w-3" />
          Paid
        </span>
      );
    case "pending":
    case "processing":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-yellow-50 px-2 py-0.5 text-xs font-medium text-yellow-700">
          <Clock className="h-3 w-3" />
          Pending
        </span>
      );
    case "failed":
    case "refunded":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
          <XCircle className="h-3 w-3" />
          {status === "refunded" ? "Refunded" : "Failed"}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
          {status}
        </span>
      );
  }
}

async function handleDownloadInvoice(invoiceId: string) {
  try {
    const resp = await portalApi.getInvoicePdf(invoiceId);
    const url = resp.data?.data?.url;
    if (url) {
      window.open(url, "_blank");
    }
  } catch {
    toast.error("Failed to download invoice");
  }
}

export default function PaymentsPage() {
  const { data: payments, isLoading } = useQuery({
    queryKey: ["portal-payments"],
    queryFn: () => portalApi.getPaymentHistory().then((r) => r.data),
  });

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Payment History</h1>
        <p className="mt-1 text-sm text-gray-500">
          View your past payments and download invoices.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      ) : !payments || payments.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Receipt className="mx-auto mb-3 h-10 w-10 text-gray-300" />
            <p className="text-gray-500">No payment history yet.</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-left">
                  <th className="px-4 py-3 font-medium text-gray-500">Date</th>
                  <th className="px-4 py-3 font-medium text-gray-500">
                    Description
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-500">
                    Amount
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-500">
                    Status
                  </th>
                  <th className="px-4 py-3 font-medium text-gray-500"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {payments.map((payment) => (
                  <tr key={payment.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3 text-gray-900">
                      {formatDate(payment.payment_date)}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {payment.description || "--"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">
                      {formatCents(payment.amount_cents)}
                    </td>
                    <td className="px-4 py-3">
                      {statusBadge(payment.status)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {payment.stripe_invoice_id && (
                        <button
                          onClick={() =>
                            handleDownloadInvoice(payment.stripe_invoice_id!)
                          }
                          className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800"
                        >
                          <Download className="h-4 w-4" />
                          Invoice
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
