"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Loader2, ArrowLeft, Building2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { hiringApi, type EmployerProfile } from "@/lib/hiring-api";
import { usePermission } from "@/hooks/use-permission";

const FIELDS: { key: keyof EmployerProfile; label: string; full?: boolean; type?: string }[] = [
  { key: "legal_name", label: "Legal business name", full: true },
  { key: "dba_name", label: "DBA / studio name", full: true },
  { key: "ein", label: "EIN (federal tax ID)" },
  { key: "edd_account_number", label: "EDD employer account #" },
  { key: "address_line1", label: "Address", full: true },
  { key: "address_line2", label: "Address line 2", full: true },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "postal_code", label: "ZIP" },
  { key: "phone", label: "Business phone" },
  { key: "wc_carrier_name", label: "Workers' comp carrier" },
  { key: "wc_policy_number", label: "WC policy number" },
  { key: "wc_carrier_phone", label: "WC carrier phone" },
  { key: "wc_policy_effective", label: "WC policy effective date", type: "date" },
  { key: "pay_schedule", label: "Pay schedule (weekly/biweekly/semimonthly/monthly)" },
  { key: "regular_payday", label: "Regular payday" },
  { key: "overtime_basis", label: "Overtime basis" },
];

export default function EmployerProfilePage() {
  const canManage = usePermission("hiring.manage_employer");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EmployerProfile>({});

  const { data: profile, isLoading } = useQuery({
    queryKey: ["employer-profile"],
    queryFn: () => hiringApi.getEmployerProfile(),
    enabled: canManage,
  });

  useEffect(() => {
    if (profile) setForm(profile);
  }, [profile]);

  useEffect(() => {
    if (!canManage) router.push("/dashboard/hiring");
  }, [canManage, router]);

  const mutation = useMutation({
    mutationFn: () => hiringApi.updateEmployerProfile(form),
    onSuccess: () => {
      toast.success("Employer profile saved");
      queryClient.invalidateQueries({ queryKey: ["employer-profile"] });
    },
    onError: () => toast.error("Failed to save"),
  });

  const set = (k: keyof EmployerProfile, v: string) => setForm((p) => ({ ...p, [k]: v }));

  if (!canManage || isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => router.push("/dashboard/hiring")} className="rounded-md p-1 text-gray-500 hover:bg-gray-100">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-gray-900">
            <Building2 className="h-6 w-6 text-indigo-600" /> Employer Profile
          </h1>
          <p className="text-sm text-gray-500">
            Your business info — used to auto-fill new-hire forms (wage-theft notice, DE-34, etc.).
          </p>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Business & Tax</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {FIELDS.map((f) => (
              <div key={f.key} className={f.full ? "sm:col-span-2" : ""}>
                <Label htmlFor={f.key}>{f.label}</Label>
                <Input
                  id={f.key}
                  type={f.type || "text"}
                  value={(form[f.key] as string) || ""}
                  onChange={(e) => set(f.key, e.target.value)}
                />
              </div>
            ))}
            <div className="sm:col-span-2">
              <Label htmlFor="sick_leave_policy">Paid sick leave policy</Label>
              <textarea
                id="sick_leave_policy"
                rows={3}
                value={form.sick_leave_policy || ""}
                onChange={(e) => set("sick_leave_policy", e.target.value)}
                className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save Employer Profile
        </Button>
      </div>
    </div>
  );
}
