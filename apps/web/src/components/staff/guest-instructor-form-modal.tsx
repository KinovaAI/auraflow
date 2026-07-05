"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { guestInstructorsApi, type GuestInstructor } from "@/lib/guest-instructors-api";

interface GuestInstructorFormModalProps {
  /** Pass an existing guest to edit; omit for create. */
  guest?: GuestInstructor;
  studioId?: string;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * Add or edit a guest instructor (1099 contractor for workshops).
 * Form fields cover advertising (name, bio, photo), contact, address,
 * tax info (encrypted at rest), and the per-guest revenue split that
 * drives 1099 reporting.
 */
export function GuestInstructorFormModal({
  guest,
  studioId,
  onClose,
  onSaved,
}: GuestInstructorFormModalProps) {
  const isEdit = !!guest;

  const [name, setName] = useState(guest?.name || "");
  const [bio, setBio] = useState(guest?.bio || "");
  const [photoUrl, setPhotoUrl] = useState(guest?.photo_url || "");
  const [email, setEmail] = useState(guest?.email || "");
  const [phone, setPhone] = useState(guest?.phone || "");
  const [addressLine1, setAddressLine1] = useState(guest?.address_line1 || "");
  const [city, setCity] = useState(guest?.city || "");
  const [state, setState] = useState(guest?.state || "");
  const [postalCode, setPostalCode] = useState(guest?.postal_code || "");
  const [taxId, setTaxId] = useState(guest?.tax_id || "");
  const [revenueShare, setRevenueShare] = useState<number>(
    guest?.revenue_share_percent_to_guest ?? 60,
  );
  const [notes, setNotes] = useState(guest?.notes || "");

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        studio_id: studioId,
        name: name.trim(),
        bio: bio.trim() || undefined,
        photo_url: photoUrl.trim() || undefined,
        email: email.trim().toLowerCase() || undefined,
        phone: phone.trim() || undefined,
        address_line1: addressLine1.trim() || undefined,
        city: city.trim() || undefined,
        state: state.trim() || undefined,
        postal_code: postalCode.trim() || undefined,
        tax_id: taxId.trim() || undefined,
        revenue_share_percent_to_guest: revenueShare,
        notes: notes.trim() || undefined,
      };
      if (isEdit && guest) {
        return guestInstructorsApi.update(guest.id, payload);
      }
      return guestInstructorsApi.create(payload);
    },
    onSuccess: () => {
      toast.success(isEdit ? "Guest instructor updated" : "Guest instructor added");
      onSaved();
    },
    onError: () => toast.error("Failed to save guest instructor"),
  });

  const canSubmit = name.trim().length > 0
    && revenueShare >= 0 && revenueShare <= 100;
  const studioShare = 100 - revenueShare;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-2xl rounded-lg bg-white shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 shrink-0">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? "Edit Guest Instructor" : "Add Guest Instructor"}
          </h2>
          <button onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Guest instructors are 1099 contractors who teach workshops only.
            California labor law prohibits them from teaching regular classes
            or courses — the system enforces this automatically.
          </div>

          {/* ── Basic info ──────────────────────────────────────── */}
          <div>
            <Label htmlFor="gi-name">Name *</Label>
            <Input id="gi-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div>
            <Label htmlFor="gi-bio">Bio (shown on workshop pages)</Label>
            <textarea
              id="gi-bio"
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              rows={3}
              className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <Label htmlFor="gi-photo">Photo URL</Label>
            <Input
              id="gi-photo"
              type="url"
              value={photoUrl}
              onChange={(e) => setPhotoUrl(e.target.value)}
              placeholder="https://…/photo.jpg"
            />
          </div>

          {/* ── Contact ─────────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="gi-email">Email</Label>
              <Input
                id="gi-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="gi-phone">Phone</Label>
              <Input
                id="gi-phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
          </div>

          {/* ── Address (for 1099 mailing) ─────────────────────── */}
          <div>
            <Label htmlFor="gi-addr">Address</Label>
            <Input
              id="gi-addr"
              value={addressLine1}
              onChange={(e) => setAddressLine1(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="gi-city">City</Label>
              <Input id="gi-city" value={city} onChange={(e) => setCity(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="gi-state">State</Label>
              <Input
                id="gi-state"
                value={state}
                onChange={(e) => setState(e.target.value)}
                maxLength={2}
              />
            </div>
            <div>
              <Label htmlFor="gi-zip">ZIP</Label>
              <Input
                id="gi-zip"
                value={postalCode}
                onChange={(e) => setPostalCode(e.target.value)}
              />
            </div>
          </div>

          {/* ── Tax ID (encrypted) ─────────────────────────────── */}
          <div>
            <Label htmlFor="gi-tax">Tax ID (SSN or EIN)</Label>
            <Input
              id="gi-tax"
              value={taxId}
              onChange={(e) => setTaxId(e.target.value)}
              placeholder="123-45-6789 or 12-3456789"
            />
            <p className="mt-1 text-xs text-gray-500">
              Encrypted at rest. Used only for end-of-year 1099 reporting.
            </p>
          </div>

          {/* ── Revenue split ──────────────────────────────────── */}
          <div className="rounded-md border border-indigo-200 bg-indigo-50/50 p-3 space-y-3">
            <Label htmlFor="gi-share">Revenue Split</Label>
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <input
                  id="gi-share"
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={revenueShare}
                  onChange={(e) => setRevenueShare(parseInt(e.target.value, 10))}
                  className="w-full"
                />
              </div>
              <div className="text-sm font-semibold whitespace-nowrap">
                {revenueShare}% guest / {studioShare}% studio
              </div>
            </div>
            <p className="text-xs text-gray-600">
              Default is 60/40 in the guest&apos;s favor; adjust per agreement.
              The 1099 report applies whatever value is set here against
              workshop revenue at year-end.
            </p>
          </div>

          {/* ── Notes ──────────────────────────────────────────── */}
          <div>
            <Label htmlFor="gi-notes">Internal notes</Label>
            <textarea
              id="gi-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Booking history, agency contact, etc."
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4 shrink-0">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            disabled={!canSubmit || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEdit ? "Save Changes" : "Add Guest Instructor"}
          </Button>
        </div>
      </div>
    </div>
  );
}
