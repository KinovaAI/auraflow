"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";

interface InstructorFormModalProps {
  instructor?: Instructor;
  onClose: () => void;
  onCreated: () => void;
}

export function InstructorFormModal({
  instructor,
  onClose,
  onCreated,
}: InstructorFormModalProps) {
  const isEdit = !!instructor;
  const [displayName, setDisplayName] = useState(instructor?.display_name || "");
  const [email, setEmail] = useState(instructor?.email || "");
  const [phone, setPhone] = useState(instructor?.phone || "");
  const [bio, setBio] = useState(instructor?.bio || "");
  const [specialties, setSpecialties] = useState(
    instructor?.specialties?.join(", ") || ""
  );
  const [certifications, setCertifications] = useState(
    instructor?.certifications?.join(", ") || ""
  );
  const [payRateCents, setPayRateCents] = useState(
    instructor?.pay_rate_cents != null
      ? String(instructor.pay_rate_cents / 100)
      : ""
  );
  const [payType, setPayType] = useState(instructor?.pay_type || "per_class");
  const [salaryCents, setSalaryCents] = useState(
    instructor?.salary_cents ? (instructor.salary_cents / 100).toFixed(2) : ""
  );
  const [taxClassification, setTaxClassification] = useState(
    instructor?.tax_classification || "1099"
  );
  const [workshopPayPercent, setWorkshopPayPercent] = useState(
    String(instructor?.workshop_pay_percent ?? 60)
  );
  const [privateSessionPayPercent, setPrivateSessionPayPercent] = useState(
    String(instructor?.private_session_pay_percent ?? 70)
  );
  const [trainingPayPercent, setTrainingPayPercent] = useState(
    String(instructor?.training_pay_percent ?? 50)
  );
  const [color, setColor] = useState(instructor?.color || "#6366F1");

  const mutation = useMutation({
    mutationFn: () => {
      const data: Partial<Instructor> = {
        display_name: displayName.trim(),
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        bio: bio.trim() || undefined,
        specialties: specialties
          ? specialties.split(",").map((s) => s.trim()).filter(Boolean)
          : undefined,
        certifications: certifications
          ? certifications.split(",").map((s) => s.trim()).filter(Boolean)
          : undefined,
        pay_rate_cents: payRateCents
          ? Math.round(parseFloat(payRateCents) * 100)
          : undefined,
        pay_type: payType || undefined,
        salary_cents: salaryCents ? Math.round(parseFloat(salaryCents) * 100) : 0,
        tax_classification: taxClassification || undefined,
        workshop_pay_percent: workshopPayPercent
          ? parseInt(workshopPayPercent)
          : undefined,
        private_session_pay_percent: privateSessionPayPercent
          ? parseInt(privateSessionPayPercent)
          : undefined,
        training_pay_percent: trainingPayPercent
          ? parseInt(trainingPayPercent)
          : undefined,
        color,
      };
      return isEdit
        ? instructorsApi.update(instructor!.id, data)
        : instructorsApi.create(data);
    },
    onSuccess: () => onCreated(),
    onError: () => toast.error(isEdit ? "Failed to update" : "Failed to create"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            {isEdit ? "Edit Instructor" : "Add Instructor"}
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
          <div>
            <Label htmlFor="displayName">Display Name *</Label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Sarah Johnson"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="email">Email *</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="instructor@example.com"
              />
              {!isEdit && email.trim() && (
                <p className="mt-1 text-xs text-gray-400">
                  Login will be created (password: example-studio)
                </p>
              )}
            </div>
            <div>
              <Label htmlFor="phone">Phone</Label>
              <Input
                id="phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
          </div>

          <div>
            <Label htmlFor="bio">Bio</Label>
            <textarea
              id="bio"
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              rows={3}
              className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Brief bio..."
            />
          </div>

          <div>
            <Label htmlFor="specialties">Specialties (comma-separated)</Label>
            <Input
              id="specialties"
              value={specialties}
              onChange={(e) => setSpecialties(e.target.value)}
              placeholder="Vinyasa, Yin, Meditation"
            />
          </div>

          <div>
            <Label htmlFor="certifications">
              Certifications (comma-separated)
            </Label>
            <Input
              id="certifications"
              value={certifications}
              onChange={(e) => setCertifications(e.target.value)}
              placeholder="RYT-200, RYT-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label htmlFor="payType">Pay Type</Label>
              <select
                id="payType"
                value={payType}
                onChange={(e) => setPayType(e.target.value)}
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="per_class">Per Class</option>
                <option value="hourly">Hourly</option>
                <option value="percentage">Percentage</option>
                <option value="salary">Salary</option>
              </select>
            </div>
            <div>
              <Label htmlFor="payRate">
                {payType === "percentage" ? "Pay Rate (%)" : "Pay Rate ($)"}
              </Label>
              <Input
                id="payRate"
                type="number"
                step={payType === "percentage" ? "1" : "0.01"}
                value={payRateCents}
                onChange={(e) => setPayRateCents(e.target.value)}
                placeholder={payType === "percentage" ? "50" : "50.00"}
              />
            </div>
            <div>
              <Label htmlFor="salary">Monthly Salary ($)</Label>
              <Input
                id="salary"
                type="number"
                step="0.01"
                value={salaryCents}
                onChange={(e) => setSalaryCents(e.target.value)}
                placeholder="1000.00"
              />
            </div>
            <div>
              <Label htmlFor="tax">Tax Classification</Label>
              <select
                id="tax"
                value={taxClassification}
                onChange={(e) => setTaxClassification(e.target.value)}
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="1099">1099</option>
                <option value="W2">W-2</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label htmlFor="workshopPay">Workshop Pay %</Label>
              <Input
                id="workshopPay"
                type="number"
                min="0"
                max="100"
                value={workshopPayPercent}
                onChange={(e) => setWorkshopPayPercent(e.target.value)}
                placeholder="60"
              />
            </div>
            <div>
              <Label htmlFor="privatePay">Private Session %</Label>
              <Input
                id="privatePay"
                type="number"
                min="0"
                max="100"
                value={privateSessionPayPercent}
                onChange={(e) => setPrivateSessionPayPercent(e.target.value)}
                placeholder="70"
              />
            </div>
            <div>
              <Label htmlFor="trainingPay">Training Pay %</Label>
              <Input
                id="trainingPay"
                type="number"
                min="0"
                max="100"
                value={trainingPayPercent}
                onChange={(e) => setTrainingPayPercent(e.target.value)}
                placeholder="50"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="color">Color</Label>
            <div className="flex items-center gap-2">
              <input
                id="color"
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="h-10 w-10 cursor-pointer rounded border border-gray-300"
              />
              <span className="text-sm text-gray-500">{color}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!displayName.trim() || (!isEdit && !email.trim()) || mutation.isPending}
          >
            {mutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isEdit ? "Save Changes" : "Add Instructor"}
          </Button>
        </div>
      </div>
    </div>
  );
}
