"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { CreditCard, ShieldCheck, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SaveCardViaSquareModal } from "@/components/payments/save-card-square-modal";

export default function PaymentMethodsPage() {
  const searchParams = useSearchParams();
  const isSetup = searchParams.get("setup") === "1";
  const [showModal, setShowModal] = useState(false);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Payment Methods</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage the payment methods on your account.
        </p>
      </div>

      {isSetup && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600" />
          <div>
            <p className="text-sm font-medium text-amber-800">
              Welcome to our new system! Please set up your payment method to continue your membership.
            </p>
            <p className="mt-1 text-xs text-amber-600">
              Click the button below to securely add your credit card. Your existing membership will continue without interruption.
            </p>
          </div>
        </div>
      )}

      <Card className="mx-auto max-w-lg">
        <CardHeader>
          <div className="flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-indigo-600" />
            <CardTitle className="text-base">
              Manage Payment Methods
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-3 rounded-md bg-gray-50 p-4">
            <ShieldCheck className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-600" />
            <p className="text-sm text-gray-600">
              Your card is tokenized and saved by Square. The studio never
              sees your full card number.
            </p>
          </div>

          <Button
            className="w-full"
            onClick={() => setShowModal(true)}
          >
            <CreditCard className="mr-2 h-4 w-4" />
            Add / Update Card
          </Button>
        </CardContent>
      </Card>

      {showModal && (
        <SaveCardViaSquareModal
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
