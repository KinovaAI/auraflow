"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  metaAdsApi,
  type MetaAdsConfig,
  type MetaAdsConfigUpdate,
} from "@/lib/meta-ads-api";

interface Props {
  config: MetaAdsConfig | null;
  onSaved: () => void;
}

export function MetaAdsConfigForm({ config, onSaved }: Props) {
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
  const [ageMin, setAgeMin] = useState(
    config?.target_age_min?.toString() || "18"
  );
  const [ageMax, setAgeMax] = useState(
    config?.target_age_max?.toString() || "65"
  );
  const [interests, setInterests] = useState(
    config?.target_interests?.join(", ") || ""
  );
  const [brandVoice, setBrandVoice] = useState(config?.brand_voice || "");
  const [pixelId, setPixelId] = useState(config?.meta_pixel_id || "");
  const [pageId, setPageId] = useState(config?.default_page_id || "");
  const [instagramId, setInstagramId] = useState(
    config?.instagram_account_id || ""
  );
  const [approvalThreshold, setApprovalThreshold] = useState(
    config ? (config.approval_threshold_cents / 100).toString() : "100"
  );

  const saveMutation = useMutation({
    mutationFn: (data: MetaAdsConfigUpdate) =>
      metaAdsApi.updateConfig(data).then((r) => r.data.data),
    onSuccess: () => onSaved(),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: MetaAdsConfigUpdate = {
      max_monthly_spend_cents: Math.round(parseFloat(maxMonthlySpend) * 100),
      target_radius_miles: parseInt(radiusMiles),
      target_age_min: parseInt(ageMin),
      target_age_max: parseInt(ageMax),
      approval_threshold_cents: Math.round(
        parseFloat(approvalThreshold) * 100
      ),
    };
    if (targetLat) data.target_latitude = parseFloat(targetLat);
    if (targetLng) data.target_longitude = parseFloat(targetLng);
    if (brandVoice) data.brand_voice = brandVoice;
    if (pixelId) data.meta_pixel_id = pixelId;
    if (pageId) data.default_page_id = pageId;
    if (instagramId) data.instagram_account_id = instagramId;
    if (interests) {
      data.target_interests = interests
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
    }
    saveMutation.mutate(data);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Facebook & Instagram Ads Configuration
        </CardTitle>
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
              <input
                type="number"
                step="0.000001"
                value={targetLat}
                onChange={(e) => setTargetLat(e.target.value)}
                placeholder="Latitude"
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <input
                type="number"
                step="0.000001"
                value={targetLng}
                onChange={(e) => setTargetLng(e.target.value)}
                placeholder="Longitude"
                className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
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

          {/* Age & Gender */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Age Range
              </label>
              <div className="mt-1 flex items-center gap-2">
                <input
                  type="number"
                  min="13"
                  max="65"
                  value={ageMin}
                  onChange={(e) => setAgeMin(e.target.value)}
                  className="block w-20 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <span className="text-gray-500">to</span>
                <input
                  type="number"
                  min="18"
                  max="65"
                  value={ageMax}
                  onChange={(e) => setAgeMax(e.target.value)}
                  className="block w-20 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Interests (optional)
              </label>
              <input
                type="text"
                value={interests}
                onChange={(e) => setInterests(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="yoga, fitness, pilates (comma-separated)"
              />
            </div>
          </div>

          {/* Meta-specific IDs */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Meta Pixel ID
              </label>
              <input
                type="text"
                value={pixelId}
                onChange={(e) => setPixelId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="e.g. 123456789"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Facebook Page ID
              </label>
              <input
                type="text"
                value={pageId}
                onChange={(e) => setPageId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="e.g. 123456789"
              />
              <p className="mt-1 text-xs text-gray-500">Required for ad creatives</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Instagram Account ID
              </label>
              <input
                type="text"
                value={instagramId}
                onChange={(e) => setInstagramId(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="Optional"
              />
            </div>
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
