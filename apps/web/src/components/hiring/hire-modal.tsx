"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api-client";
import { hiringApi, type JobApplicationDetail, type HireResult } from "@/lib/hiring-api";

interface Studio {
  id: string;
  name: string;
}

interface HireModalProps {
  application: JobApplicationDetail;
  onClose: () => void;
  onHired: (result: HireResult) => void;
}

const ROLES = [
  { value: "instructor", label: "Instructor" },
  { value: "front_desk", label: "Front Desk" },
  { value: "admin", label: "Manager / Admin" },
];

export function HireModal({ application, onClose, onHired }: HireModalProps) {
  const defaultRole =
    application.position_type === "front_desk" || application.position_type === "admin"
      ? application.position_type
      : "instructor";

  const [role, setRole] = useState<string>(defaultRole);
  const [studioId, setStudioId] = useState<string>("");
  const [title, setTitle] = useState(application.position_title || "");
  const [department, setDepartment] = useState("");
  const [payRate, setPayRate] = useState("");
  const [payType, setPayType] = useState("per_class");
  const [taxClass, setTaxClass] = useState("1099");
  const [hireDate, setHireDate] = useState("");
  const [sendW4, setSendW4] = useState(true);

  const { data: studios } = useQuery({
    queryKey: ["studios-for-hire"],
    queryFn: () =>
      apiClient.get<Studio[] | { data: Studio[] }>("/studios").then((r) =>
        Array.isArray(r.data) ? r.data : r.data.data,
      ),
  });

  // Default to the first studio once loaded.
  useEffect(() => {
    if (studios && studios.length > 0 && !studioId) {
      setStudioId(studios[0].id);
    }
  }, [studios, studioId]);

  const mutation = useMutation({
    mutationFn: () =>
      hiringApi.hire(application.id, {
        role: role as "instructor" | "front_desk" | "admin",
        studio_id: studioId || undefined,
        pay_rate_cents: payRate ? Math.round(parseFloat(payRate) * 100) : undefined,
        pay_type: payType,
        tax_classification: taxClass,
        title: title.trim() || undefined,
        department: department.trim() || undefined,
        hire_date: hireDate || undefined,
        send_w4_email: sendW4,
      }),
    onSuccess: (result) => {
      toast.success(`${application.first_name} hired as ${role.replace("_", " ")}`);
      onHired(result);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to hire applicant");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Hire {application.first_name} {application.last_name}
          </h2>
          <button onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-6 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="role">Role *</Label>
              <select
                id="role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="mt-1 flex h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <div>
              <Label htmlFor="studio">Location *</Label>
              <select
                id="studio"
                value={studioId}
                onChange={(e) => setStudioId(e.target.value)}
                className="mt-1 flex h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {(studios || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="title">Title</Label>
              <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior Yoga Instructor" />
            </div>
            <div>
              <Label htmlFor="department">Department</Label>
              <Input id="department" value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Yoga" />
            </div>
          </div>

          {role === "instructor" && (
            <div className="grid grid-cols-3 gap-4">
              <div>
                <Label htmlFor="payrate">Pay rate ($)</Label>
                <Input id="payrate" type="number" step="0.01" value={payRate} onChange={(e) => setPayRate(e.target.value)} placeholder="60.00" />
              </div>
              <div>
                <Label htmlFor="paytype">Pay type</Label>
                <select
                  id="paytype"
                  value={payType}
                  onChange={(e) => setPayType(e.target.value)}
                  className="mt-1 flex h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="per_class">Per class</option>
                  <option value="hourly">Hourly</option>
                  <option value="salary">Salary</option>
                </select>
              </div>
              <div>
                <Label htmlFor="taxclass">Tax class</Label>
                <select
                  id="taxclass"
                  value={taxClass}
                  onChange={(e) => setTaxClass(e.target.value)}
                  className="mt-1 flex h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="1099">1099</option>
                  <option value="W2">W-2</option>
                </select>
              </div>
            </div>
          )}

          <div>
            <Label htmlFor="hiredate">Start date</Label>
            <Input id="hiredate" type="date" value={hireDate} onChange={(e) => setHireDate(e.target.value)} />
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={sendW4} onChange={(e) => setSendW4(e.target.checked)} className="rounded border-gray-300" />
            Email the new hire a link to complete their W-4
          </label>

          <p className="rounded-md bg-indigo-50 px-3 py-2 text-xs text-indigo-700">
            This creates the account, assigns the role + location, and (for instructors)
            an instructor profile prefilled from the application.
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => mutation.mutate()} disabled={!studioId || mutation.isPending}>
            {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Confirm Hire
          </Button>
        </div>
      </div>
    </div>
  );
}
