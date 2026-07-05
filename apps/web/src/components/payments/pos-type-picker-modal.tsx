"use client";

/**
 * AuraFlow — POS Type Picker Modal
 *
 * Lists active membership types for the studio and offers an ad-hoc
 * amount entry. Hands the picked plan (or ad-hoc amount) to whatever
 * parent (typically POSChargeModal) will actually run the charge.
 *
 * Extracted from members/[id]/page.tsx in the 2026-06-07 audit pass
 * so the component is reusable + unit-testable.
 */
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api-client";

export type POSTypePickerArgs = {
  amount_cents: number;
  description: string;
  membership_type_id?: string;
};

type MT = {
  id: string;
  name: string;
  price_cents: number;
  type: string;
  billing_period?: string;
  is_active?: boolean;
  is_public?: boolean;
};

export function POSTypePickerModal({
  onClose,
  onPick,
}: {
  memberId: string;     // kept for parity with caller; not used internally
  onClose: () => void;
  onPick: (args: POSTypePickerArgs) => void;
}) {
  const [types, setTypes] = useState<MT[]>([]);
  const [loading, setLoading] = useState(true);
  const [adhoc, setAdhoc] = useState({ amount: "", description: "" });
  const [search, setSearch] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const studiosResp = await apiClient.get<Array<{ id: string }>>("/studios");
        const sid = studiosResp.data?.[0]?.id;
        if (!sid) {
          toast.error("No studio configured for this org");
          setLoading(false);
          return;
        }
        const resp = await apiClient.get<MT[]>(
          `/memberships/types?studio_id=${sid}&active_only=true`,
        );
        const arr = Array.isArray(resp.data) ? resp.data : [];
        setTypes(arr.filter((t) => (t.is_active ?? true) && t.price_cents > 0));
      } catch {
        toast.error("Could not load membership types");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = types.filter(
    (t) => !search.trim() || t.name.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="max-h-[95vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-4 shadow-xl sm:p-6">
        <h3 className="text-lg font-semibold text-gray-900">Sell via Square POS</h3>
        <p className="mt-1 text-sm text-gray-500">
          Pick a plan or class pack. Hardware will prompt the member to tap their card; card is saved on file automatically.
        </p>

        {loading ? (
          <div className="mt-6 flex justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
          </div>
        ) : types.length === 0 ? (
          <p className="mt-6 text-center text-sm text-gray-500">
            No membership types configured. Add one in Settings → Memberships.
          </p>
        ) : (
          <>
            {types.length > 8 && (
              <input
                type="text"
                placeholder="Search plans…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="mt-4 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                autoFocus
              />
            )}
            <div className="mt-4 max-h-64 space-y-2 overflow-y-auto">
              {filtered.map((t) => (
                <button
                  key={t.id}
                  className="w-full rounded-md border border-gray-200 px-3 py-2 text-left text-sm hover:border-indigo-500 hover:bg-indigo-50"
                  onClick={() =>
                    onPick({
                      amount_cents: t.price_cents,
                      description: t.name,
                      membership_type_id: t.id,
                    })
                  }
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-gray-900">{t.name}</span>
                    <span className="text-gray-700">
                      ${(t.price_cents / 100).toFixed(2)}
                      {t.billing_period && t.billing_period !== "one_time"
                        ? `/${t.billing_period.slice(0, 2)}`
                        : ""}
                    </span>
                  </div>
                </button>
              ))}
              {filtered.length === 0 && (
                <p className="px-1 py-2 text-center text-sm text-gray-400">
                  No plans match &ldquo;{search}&rdquo;
                </p>
              )}
            </div>
          </>
        )}

        <div className="mt-5 border-t border-gray-100 pt-4">
          <div className="text-xs font-medium uppercase text-gray-400">
            Or charge an ad-hoc amount
          </div>
          <div className="mt-2 flex gap-2">
            <input
              type="number"
              placeholder="$ amount"
              value={adhoc.amount}
              onChange={(e) => setAdhoc({ ...adhoc, amount: e.target.value })}
              className="w-28 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <input
              type="text"
              placeholder="Description"
              value={adhoc.description}
              onChange={(e) => setAdhoc({ ...adhoc, description: e.target.value })}
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div className="mt-3 flex justify-end gap-3">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                const cents = Math.round(parseFloat(adhoc.amount || "0") * 100);
                if (cents <= 0 || !adhoc.description.trim()) {
                  toast.error("Amount + description required");
                  return;
                }
                onPick({ amount_cents: cents, description: adhoc.description.trim() });
              }}
            >
              Charge
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
