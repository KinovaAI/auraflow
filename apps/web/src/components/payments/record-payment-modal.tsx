"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { membersApi, type Member } from "@/lib/members-api";
import { paymentsApi } from "@/lib/payments-api";

interface RecordPaymentModalProps {
  onClose: () => void;
  onRecorded: () => void;
}

export function RecordPaymentModal({
  onClose,
  onRecorded,
}: RecordPaymentModalProps) {
  const queryClient = useQueryClient();
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [paymentType, setPaymentType] = useState("payment");

  const { data: members } = useQuery({
    queryKey: ["members"],
    queryFn: () => membersApi.list({}).then((r) => r.data),
  });

  const mutation = useMutation({
    mutationFn: () =>
      paymentsApi.recordTransaction({
        member_id: selectedMemberId,
        amount_cents: Math.round(parseFloat(amount) * 100),
        type: paymentType,
        description: description.trim() || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["revenue-summary"] });
      toast.success("Payment recorded");
      onRecorded();
    },
    onError: () => toast.error("Failed to record payment"),
  });

  const canSubmit =
    selectedMemberId && amount && parseFloat(amount) > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Record Payment
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-4">
          <div>
            <Label>Member</Label>
            <select
              value={selectedMemberId}
              onChange={(e) => setSelectedMemberId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select a member...</option>
              {members?.map((m: Member) => (
                <option key={m.id} value={m.id}>
                  {m.first_name} {m.last_name} — {m.email}
                </option>
              ))}
            </select>
          </div>

          <div>
            <Label htmlFor="amount">Amount ($)</Label>
            <Input
              id="amount"
              type="number"
              step="0.01"
              min="0"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
            />
          </div>

          <div>
            <Label>Type</Label>
            <select
              value={paymentType}
              onChange={(e) => setPaymentType(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="payment">Payment</option>
              <option value="drop_in">Drop-in</option>
              <option value="retail">Retail</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div>
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g., Drop-in class, water bottle..."
            />
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
            Record Payment
          </Button>
        </div>
      </div>
    </div>
  );
}
