"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  googleAdsApi,
  type GoogleAdsConfig,
  type GoogleAdsConfigUpdate,
} from "@/lib/google-ads-api";

interface Props {
  config: GoogleAdsConfig | null;
  onSaved: () => void;
}

export function GoogleAdsConfigForm({ config, onSaved }: Props) {
  const [maxMonthlySpend, setMaxMonthlySpend] = useState(
    config ? (config.max_monthly_spend_cents / 100).toString() : "500"
  );
  const [targetLat, setTargetLat] = useState(
    config?.target_latitude?.toString() || ""
  );
  const [targetLng, setTargetLng] = useState(
    config?.target_longitude?.toString() || ""
  );
  const [radiusMiles, setRadiusMiles] = useState(
    config?.target_radius_miles?.toString() || "15"
  );
  const [brandVoice, setBrandVoice] = useState(config?.brand_voice || "");
  const [negativeKeywords, setNegativeKeywords] = useState(
    config?.negative_keywords?.join(", ") || ""
  );
  const [approvalThreshold, setApprovalThreshold] = useState(
    config ? (config.approval_threshold_cents / 100).toString() : "100"
  );

  const saveMutation = useMutation({
    mutationFn: (data: GoogleAdsConfigUpdate) =>
      googleAdsApi.updateConfig(data).then((r) => r.data.data),
    onSuccess: () => onSaved(),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: GoogleAdsConfigUpdate = {
      max_monthly_spend_cents: Math.round(parseFloat(maxMonthlySpend) * 100),
      target_radius_miles: parseInt(radiusMiles),
      approval_threshold_cents: Math.round(
        parseFloat(approvalThreshold) * 100
      ),
    };
    if (targetLat) data.target_latitude = parseFloat(targetLat);
    if (targetLng) data.target_longitude = parseFloat(targetLng);
    if (brandVoice) data.brand_voice = brandVoice;
    if (negativeKeywords) {
      data.negative_keywords = negativeKeywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
    }
    saveMutation.mutate(data);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Google Ads Configuration</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Budget */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Max Monthly Spend ($)
              </label>
              <input
                type="number"
                min="50"
                step="50"
                required
                value={maxMonthlySpend}
                onChange={(e) => setMaxMonthlySpend(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                Campaigns auto-pause at 95% of this cap
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Approval Threshold ($)
              </label>
              <input
                type="number"
                min="10"
                step="10"
                required
                value={approvalThreshold}
                onChange={(e) => setApprovalThreshold(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                AI will ask for your approval above this amount
              </p>
            </div>
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Location Targeting
            </label>
            <div className="mt-1 grid gap-3 sm:grid-cols-3">
              <div>
                <input
                  type="number"
                  step="0.000001"
                  value={targetLat}
                  onChange={(e) => setTargetLat(e.target.value)}
                  placeholder="Latitude"
                  className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <input
                  type="number"
                  step="0.000001"
                  value={targetLng}
                  onChange={(e) => setTargetLng(e.target.value)}
                  placeholder="Longitude"
                  className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={radiusMiles}
                  onChange={(e) => setRadiusMiles(e.target.value)}
                  placeholder="Radius (miles)"
                  className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Enter your studio&apos;s coordinates and targeting radius
            </p>
          </div>

          {/* Brand Voice */}
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Brand Voice (optional)
            </label>
            <textarea
              value={brandVoice}
              onChange={(e) => setBrandVoice(e.target.value)}
              rows={2}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="e.g. Warm, community-focused, emphasize inclusivity and beginner-friendly classes"
            />
          </div>

          {/* Negative Keywords */}
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Negative Keywords (optional)
            </label>
            <input
              type="text"
              value={negativeKeywords}
              onChange={(e) => setNegativeKeywords(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              placeholder="jobs, certification, online, free (comma-separated)"
            />
            <p className="mt-1 text-xs text-gray-500">
              Words that should never trigger your ads
            </p>
          </div>

          {saveMutation.isError && (
            <p className="text-sm text-red-600">
              Failed to save. Please try again.
            </p>
          )}

          <div className="flex justify-end">
            <Button type="submit" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-1 h-4 w-4" />
              )}
              Save Configuration
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
