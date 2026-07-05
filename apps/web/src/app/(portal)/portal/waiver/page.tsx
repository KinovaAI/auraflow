"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { portalApi } from "@/lib/portal-api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle2, AlertTriangle, FileCheck } from "lucide-react";
import toast from "react-hot-toast";

export default function PortalWaiverPage() {
  const qc = useQueryClient();
  const [signatureText, setSignatureText] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["portal-waiver"],
    queryFn: () => portalApi.getWaiverStatus().then((r) => r.data.data),
  });

  const signMutation = useMutation({
    mutationFn: (body: { template_id: string; signature_text: string }) =>
      portalApi.signWaiver(body),
    onSuccess: () => {
      toast.success("Waiver signed successfully!");
      qc.invalidateQueries({ queryKey: ["portal-waiver"] });
      setSignatureText("");
    },
    onError: () => {
      toast.error("Failed to sign waiver. Please try again.");
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  // No active waiver template
  if (!data?.template) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-gray-900">Liability Waiver</h1>
        <Card>
          <CardContent className="py-8 text-center">
            <FileCheck className="mx-auto h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">
              No waiver is currently required.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { template, status } = data;
  const needsSignature = !status.signed || status.expired || status.needs_resign;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-gray-900">Liability Waiver</h1>

      {/* Status banner */}
      {!needsSignature ? (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-600" />
          <div>
            <p className="text-sm font-medium text-emerald-800">
              Waiver Signed
            </p>
            <p className="text-xs text-emerald-600">
              Signed on{" "}
              {status.signed_at
                ? new Date(status.signed_at).toLocaleDateString()
                : "—"}
              {status.expires_at && (
                <> · Expires {new Date(status.expires_at).toLocaleDateString()}</>
              )}
            </p>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-600" />
          <div>
            <p className="text-sm font-medium text-amber-800">
              {status.expired
                ? "Your waiver has expired"
                : status.needs_resign
                  ? "A new waiver version requires your signature"
                  : "Please sign the waiver to book classes"}
            </p>
          </div>
        </div>
      )}

      {/* Waiver content */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {template.title}{" "}
            <span className="text-xs font-normal text-gray-400">
              (v{template.version})
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-80 overflow-y-auto rounded border bg-gray-50 p-4 text-sm leading-relaxed text-gray-700 whitespace-pre-wrap">
            {template.content}
          </div>

          {needsSignature && (
            <div className="mt-6 space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Type your full name to sign
                </label>
                <input
                  type="text"
                  value={signatureText}
                  onChange={(e) => setSignatureText(e.target.value)}
                  placeholder="Your full legal name"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <Button
                onClick={() =>
                  signMutation.mutate({
                    template_id: template.id,
                    signature_text: signatureText.trim(),
                  })
                }
                disabled={
                  !signatureText.trim() || signMutation.isPending
                }
                className="w-full"
              >
                {signMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Signing...
                  </>
                ) : (
                  "I Agree — Sign Waiver"
                )}
              </Button>
              <p className="text-center text-xs text-gray-400">
                By signing, you acknowledge that you have read and agree to the
                terms above.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
