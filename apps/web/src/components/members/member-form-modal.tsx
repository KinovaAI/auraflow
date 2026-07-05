"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { membersApi, type Member } from "@/lib/members-api";

interface MemberFormModalProps {
  member?: Member;
  onClose: () => void;
  onCreated: () => void;
}

export function MemberFormModal({
  member,
  onClose,
  onCreated,
}: MemberFormModalProps) {
  const isEdit = !!member;
  const [firstName, setFirstName] = useState(member?.first_name || "");
  const [lastName, setLastName] = useState(member?.last_name || "");
  const [email, setEmail] = useState(member?.email || "");
  const [phone, setPhone] = useState(member?.phone || "");
  const [city, setCity] = useState(member?.city || "");
  const [state, setState] = useState(member?.state || "");
  const [emergName, setEmergName] = useState(
    member?.emergency_contact_name || ""
  );
  const [emergPhone, setEmergPhone] = useState(
    member?.emergency_contact_phone || ""
  );

  const mutation = useMutation({
    mutationFn: () => {
      const data: Partial<Member> = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        city: city.trim() || undefined,
        state: state.trim() || undefined,
        emergency_contact_name: emergName.trim() || undefined,
        emergency_contact_phone: emergPhone.trim() || undefined,
      };
      return isEdit
        ? membersApi.update(member!.id, data)
        : membersApi.create(data);
    },
    onSuccess: () => onCreated(),
    onError: () =>
      toast.error(isEdit ? "Failed to update" : "Failed to create"),
  });

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const canSubmit = firstName.trim() && lastName.trim() && emailValid;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? "Edit Member" : "Add Member"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="firstName">First Name *</Label>
              <Input
                id="firstName"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="lastName">Last Name *</Label>
              <Input
                id="lastName"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
              />
            </div>
          </div>

          <div>
            <Label htmlFor="email">Email *</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="phone">Phone</Label>
            <Input
              id="phone"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="city">City</Label>
              <Input
                id="city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="state">State</Label>
              <Input
                id="state"
                value={state}
                onChange={(e) => setState(e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="emergName">Emergency Contact</Label>
              <Input
                id="emergName"
                value={emergName}
                onChange={(e) => setEmergName(e.target.value)}
                placeholder="Contact name"
              />
            </div>
            <div>
              <Label htmlFor="emergPhone">Emergency Phone</Label>
              <Input
                id="emergPhone"
                value={emergPhone}
                onChange={(e) => setEmergPhone(e.target.value)}
              />
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isEdit ? "Save Changes" : "Add Member"}
          </Button>
        </div>
      </div>
    </div>
  );
}
