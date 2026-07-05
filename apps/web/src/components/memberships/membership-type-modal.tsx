"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  membershipTypesApi,
  type MembershipType,
} from "@/lib/memberships-api";

interface MembershipTypeModalProps {
  studioId: string;
  membershipType?: MembershipType | null;
  onClose: () => void;
}

export function MembershipTypeModal({
  studioId,
  membershipType,
  onClose,
}: MembershipTypeModalProps) {
  const queryClient = useQueryClient();
  const isEditing = !!membershipType;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<string>("unlimited");
  const [accessScope, setAccessScope] = useState<string>("in_studio");
  const [priceStr, setPriceStr] = useState("");
  const [billingPeriod, setBillingPeriod] = useState("monthly");
  const [classCount, setClassCount] = useState("");
  const [durationDays, setDurationDays] = useState("");
  const [autoRenew, setAutoRenew] = useState(true);
  const [freezeAllowed, setFreezeAllowed] = useState(false);
  const [isPublic, setIsPublic] = useState(true);

  useEffect(() => {
    if (membershipType) {
      setName(membershipType.name);
      setDescription(membershipType.description || "");
      setType(membershipType.type);
      setAccessScope(membershipType.access_scope || "in_studio");
      setPriceStr((membershipType.price_cents / 100).toFixed(2));
      setBillingPeriod(membershipType.billing_period || "monthly");
      setClassCount(
        membershipType.class_count ? String(membershipType.class_count) : ""
      );
      setDurationDays(
        membershipType.duration_days ? String(membershipType.duration_days) : ""
      );
      setAutoRenew(membershipType.auto_renew);
      setFreezeAllowed(membershipType.freeze_allowed);
      setIsPublic(membershipType.is_public);
    }
  }, [membershipType]);

  const createMutation = useMutation({
    mutationFn: (data: Partial<MembershipType> & { studio_id: string; name: string; type: string; price_cents: number }) =>
      membershipTypesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["membership-types"] });
      toast.success("Membership type created");
      onClose();
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || "Failed to create membership type"),
  });

  const updateMutation = useMutation({
    mutationFn: (data: Partial<MembershipType>) =>
      membershipTypesApi.update(membershipType!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["membership-types"] });
      toast.success("Membership type updated");
      onClose();
    },
    onError: () => toast.error("Failed to update membership type"),
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const handleSubmit = () => {
    const priceCents = Math.round((parseFloat(priceStr) || 0) * 100);
    const payload: Record<string, unknown> = {
      studio_id: studioId,
      name: name.trim(),
      description: description.trim() || undefined,
      type,
      access_scope: accessScope,
      price_cents: priceCents,
      billing_period: billingPeriod || null,
      duration_days: durationDays ? parseInt(durationDays, 10) : undefined,
      auto_renew: autoRenew,
      freeze_allowed: freezeAllowed,
      is_public: isPublic,
    };

    if (type === "class_pack") {
      payload.class_count = classCount ? parseInt(classCount, 10) : undefined;
    }

    if (isEditing) {
      updateMutation.mutate(payload as Partial<MembershipType>);
    } else {
      createMutation.mutate(
        payload as Partial<MembershipType> & {
          studio_id: string;
          name: string;
          type: string;
          price_cents: number;
        }
      );
    }
  };

  const canSubmit = name.trim() && (priceStr === "" || parseFloat(priceStr) >= 0);

  const selectClass =
    "flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEditing ? "Edit Membership Type" : "Add Custom Type"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
          {/* Name */}
          <div>
            <Label htmlFor="mt-name">Name</Label>
            <Input
              id="mt-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Unlimited Monthly"
            />
          </div>

          {/* Description */}
          <div>
            <Label htmlFor="mt-desc">Description</Label>
            <Input
              id="mt-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description..."
            />
          </div>

          {/* Type */}
          <div>
            <Label>Type</Label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className={selectClass}
            >
              <option value="unlimited">Unlimited</option>
              <option value="class_pack">Class Pack</option>
              <option value="single_class">Single Class</option>
              <option value="intro_offer">Intro Offer</option>
              <option value="day_pass">Day Pass</option>
            </select>
          </div>

          {/* Access Scope */}
          <div>
            <Label>Access Scope</Label>
            <div className="mt-1 flex gap-4">
              {[
                { value: "in_studio", label: "In-Studio" },
                { value: "online", label: "Online" },
                { value: "all_access", label: "All-Access" },
              ].map((opt) => (
                <label
                  key={opt.value}
                  className="flex items-center gap-2 text-sm text-gray-700"
                >
                  <input
                    type="radio"
                    name="access_scope"
                    value={opt.value}
                    checked={accessScope === opt.value}
                    onChange={(e) => setAccessScope(e.target.value)}
                    className="h-4 w-4 border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>

          {/* Price */}
          <div>
            <Label htmlFor="mt-price">Price ($)</Label>
            <Input
              id="mt-price"
              type="number"
              step="0.01"
              min="0"
              value={priceStr}
              onChange={(e) => setPriceStr(e.target.value)}
              placeholder="0.00"
            />
          </div>

          {/* Billing Period */}
          <div>
            <Label>Billing Period</Label>
            <select
              value={billingPeriod}
              onChange={(e) => setBillingPeriod(e.target.value)}
              className={selectClass}
            >
              <option value="">None (Free)</option>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="semi_annual">Semi-Annual</option>
              <option value="yearly">Yearly</option>
              <option value="one_time">One-Time</option>
            </select>
          </div>

          {/* Class Count (only for class_pack) */}
          {type === "class_pack" && (
            <div>
              <Label htmlFor="mt-classes">Class Count</Label>
              <Input
                id="mt-classes"
                type="number"
                min="1"
                value={classCount}
                onChange={(e) => setClassCount(e.target.value)}
                placeholder="e.g., 10"
              />
            </div>
          )}

          {/* Duration Days */}
          <div>
            <Label htmlFor="mt-duration">Duration (days)</Label>
            <Input
              id="mt-duration"
              type="number"
              min="1"
              value={durationDays}
              onChange={(e) => setDurationDays(e.target.value)}
              placeholder="e.g., 30"
            />
          </div>

          {/* Toggles */}
          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={autoRenew}
                onChange={(e) => setAutoRenew(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              Auto-Renew
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={freezeAllowed}
                onChange={(e) => setFreezeAllowed(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              Freeze Allowed
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={isPublic}
                onChange={(e) => setIsPublic(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              Is Public
            </label>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!canSubmit || isPending}
          >
            {isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isEditing ? "Save Changes" : "Create Type"}
          </Button>
        </div>
      </div>
    </div>
  );
}
