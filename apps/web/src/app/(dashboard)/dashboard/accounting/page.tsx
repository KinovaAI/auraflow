"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  RefreshCw,
  Download,
  FileText,
  Plus,
  Trash2,
  Building2,
  CheckCircle2,
  AlertTriangle,
  Landmark,
  Banknote,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  accountingApi,
  type AccountingTransaction,
  type AccountingMember,
} from "@/lib/accounting-api";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt(cents: number | null | undefined): string {
  const c = cents ?? 0;
  const neg = c < 0;
  return `${neg ? "-" : ""}$${(Math.abs(c) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

const TYPE_STYLES: Record<string, string> = {
  income: "bg-emerald-100 text-emerald-800",
  expense: "bg-rose-100 text-rose-800",
  distribution: "bg-amber-100 text-amber-800",
  transfer: "bg-slate-100 text-slate-600",
};

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "transactions", label: "Transactions" },
  { key: "reconciliation", label: "Reconciliation" },
  { key: "members", label: "K-1 Members" },
  { key: "settings", label: "Settings" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AccountingPage() {
  const currentYear = new Date().getFullYear();
  const [tab, setTab] = useState<TabKey>("overview");
  const [year, setYear] = useState<number>(currentYear);
  const qc = useQueryClient();

  const years = useMemo(
    () => Array.from({ length: 6 }, (_, i) => currentYear - i),
    [currentYear],
  );

  const syncMut = useMutation({
    mutationFn: () => accountingApi.sync().then((r) => r.data),
    onSuccess: (d) => {
      toast.success(
        `Synced — ${(d.income?.income_booked ?? 0) + (d.income?.pos_booked ?? 0)} AuraFlow sales, ${d.bank?.imported ?? 0} bank txns, ${d.reconciliation?.newly_matched ?? 0} reconciled`,
      );
      qc.invalidateQueries();
    },
    onError: () => toast.error("Sync failed — check the Mercury key + payment connections"),
  });

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-stone-800 flex items-center gap-2">
            <Landmark className="h-6 w-6 text-emerald-700" /> Accounting
          </h1>
          <p className="text-sm text-stone-500">
            Bank-authoritative books, reconciliation, and tax export.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          <Button onClick={() => syncMut.mutate()} disabled={syncMut.isPending}>
            {syncMut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            <span className="ml-2">Sync now</span>
          </Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-stone-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key
                ? "border-emerald-600 text-emerald-700"
                : "border-transparent text-stone-500 hover:text-stone-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab year={year} />}
      {tab === "transactions" && <TransactionsTab year={year} />}
      {tab === "reconciliation" && <ReconciliationTab />}
      {tab === "members" && <MembersTab year={year} />}
      {tab === "settings" && <SettingsTab year={year} />}
    </div>
  );
}

// ── Overview (P&L) ─────────────────────────────────────────────────────────────

function OverviewTab({ year }: { year: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["acct-summary", year],
    queryFn: () => accountingApi.summary(year).then((r) => r.data),
  });

  if (isLoading || !data) return <Loading />;

  const catRows = (obj: Record<string, number>) =>
    Object.entries(obj).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Total Income" value={fmt(data.total_income_cents)} tone="emerald" />
        <StatCard label="Total Expenses" value={fmt(data.total_expenses_cents)} tone="rose" />
        <StatCard
          label="Net Profit / (Loss)"
          value={fmt(data.net_profit_cents)}
          tone={data.net_profit_cents >= 0 ? "emerald" : "rose"}
        />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Income by category</CardTitle>
          </CardHeader>
          <CardContent>
            <CatTable rows={catRows(data.income)} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Expenses by category</CardTitle>
          </CardHeader>
          <CardContent>
            <CatTable rows={catRows(data.expense)} />
          </CardContent>
        </Card>
      </div>
      {Object.keys(data.distribution).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Distributions</CardTitle>
          </CardHeader>
          <CardContent>
            <CatTable rows={catRows(data.distribution)} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function CatTable({ rows }: { rows: [string, number][] }) {
  if (rows.length === 0)
    return <p className="text-sm text-stone-400 italic">Nothing recorded</p>;
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([cat, cents]) => (
          <tr key={cat} className="border-b border-stone-100 last:border-0">
            <td className="py-1.5 capitalize">{cat.replace(/_/g, " ")}</td>
            <td className="py-1.5 text-right tabular-nums">{fmt(cents)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Transactions (ledger) ──────────────────────────────────────────────────────

function TransactionsTab({ year }: { year: number }) {
  const qc = useQueryClient();
  const [filterType, setFilterType] = useState("");
  const [filterSource, setFilterSource] = useState("");

  const { data: cats } = useQuery({
    queryKey: ["acct-categories"],
    queryFn: () => accountingApi.getCategories().then((r) => r.data),
  });
  const { data: txns, isLoading } = useQuery({
    queryKey: ["acct-txns", year, filterType, filterSource],
    queryFn: () =>
      accountingApi
        .getTransactions({
          year,
          ...(filterType ? { type: filterType } : {}),
          ...(filterSource ? { source: filterSource } : {}),
        })
        .then((r) => r.data),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<AccountingTransaction> }) =>
      accountingApi.updateTransaction(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["acct-txns"] });
      qc.invalidateQueries({ queryKey: ["acct-summary"] });
    },
    onError: () => toast.error("Update failed"),
  });
  const delMut = useMutation({
    mutationFn: (id: string) => accountingApi.deleteTransaction(id),
    onSuccess: () => {
      toast.success("Deleted");
      qc.invalidateQueries({ queryKey: ["acct-txns"] });
    },
    onError: () => toast.error("Only manual entries can be deleted"),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex gap-2">
          <Select value={filterType} onChange={setFilterType} placeholder="All types"
            options={[["income", "Income"], ["expense", "Expense"], ["distribution", "Distribution"], ["transfer", "Transfer"]]} />
          <Select value={filterSource} onChange={setFilterSource} placeholder="Books (bank + manual)"
            options={[["bank", "Bank only"], ["manual", "Manual only"], ["auraflow", "AuraFlow sales detail"]]} />
        </div>
        <AddTransaction cats={cats ?? []} />
      </div>

      <p className="text-xs text-stone-500">
        {filterSource === "auraflow"
          ? "Itemized AuraFlow sales — the detail behind your bank card deposits. Shown for reference; not counted again in the P&L."
          : "Your books, straight from the bank statement. Card sales appear as their bank deposit; the per-sale breakdown is under “AuraFlow sales detail.”"}
      </p>

      {isLoading || !txns ? (
        <Loading />
      ) : (
        <Card>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-stone-500 border-b border-stone-200">
                  <th className="p-3">Date</th>
                  <th className="p-3">Description</th>
                  <th className="p-3">Type</th>
                  <th className="p-3">Category</th>
                  <th className="p-3">Source</th>
                  <th className="p-3 text-right">Amount</th>
                  <th className="p-3">Status</th>
                  <th className="p-3"></th>
                </tr>
              </thead>
              <tbody>
                {txns.length === 0 && (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-stone-400 italic">
                      No transactions. Add the Mercury key in Settings and hit “Sync now.”
                    </td>
                  </tr>
                )}
                {txns.map((t) => (
                  <tr key={t.id} className="border-b border-stone-100">
                    <td className="p-3 whitespace-nowrap">{t.txn_date}</td>
                    <td className="p-3 max-w-xs truncate" title={t.description}>
                      {t.description}
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${TYPE_STYLES[t.type]}`}>
                        {t.type}
                      </span>
                    </td>
                    <td className="p-3">
                      <select
                        value={t.category ?? ""}
                        onChange={(e) =>
                          updateMut.mutate({ id: t.id, patch: { category: e.target.value } })
                        }
                        className="rounded border border-stone-200 bg-white px-2 py-1 text-xs"
                      >
                        <option value="">—</option>
                        {(cats ?? [])
                          .filter((c) => c.kind === t.type)
                          .map((c) => (
                            <option key={c.code} value={c.code}>
                              {c.label}
                            </option>
                          ))}
                      </select>
                    </td>
                    <td className="p-3">
                      <span className="text-xs text-stone-500 capitalize">{t.source}</span>
                    </td>
                    <td className="p-3 text-right tabular-nums">{fmt(t.amount_cents)}</td>
                    <td className="p-3">
                      {t.status === "reconciled" ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      ) : (
                        <span className="text-xs text-amber-600">pending</span>
                      )}
                    </td>
                    <td className="p-3">
                      {t.source === "manual" && (
                        <button
                          onClick={() => delMut.mutate(t.id)}
                          className="text-stone-400 hover:text-rose-600"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function AddTransaction({ cats }: { cats: { code: string; label: string; kind: string }[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    txn_date: new Date().toISOString().slice(0, 10),
    description: "",
    type: "expense",
    category: "",
    amount: "",
  });
  const mut = useMutation({
    mutationFn: () =>
      accountingApi.createTransaction({
        txn_date: form.txn_date,
        description: form.description,
        type: form.type as AccountingTransaction["type"],
        category: form.category || null,
        amount_cents: Math.round(parseFloat(form.amount || "0") * 100),
      }),
    onSuccess: () => {
      toast.success("Added");
      setOpen(false);
      setForm({ ...form, description: "", amount: "" });
      qc.invalidateQueries({ queryKey: ["acct-txns"] });
      qc.invalidateQueries({ queryKey: ["acct-summary"] });
    },
    onError: () => toast.error("Failed to add"),
  });

  if (!open)
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Plus className="h-4 w-4 mr-1" /> Manual entry
      </Button>
    );

  return (
    <Card className="w-full">
      <CardContent className="p-4 flex flex-wrap items-end gap-3">
        <Field label="Date">
          <Input type="date" value={form.txn_date} onChange={(e) => setForm({ ...form, txn_date: e.target.value })} />
        </Field>
        <Field label="Description" className="flex-1 min-w-[200px]">
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Type">
          <select
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value, category: "" })}
            className="rounded-md border border-stone-300 px-3 py-2 text-sm bg-white"
          >
            {["income", "expense", "distribution", "transfer"].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="Category">
          <select
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            className="rounded-md border border-stone-300 px-3 py-2 text-sm bg-white"
          >
            <option value="">—</option>
            {cats.filter((c) => c.kind === form.type).map((c) => (
              <option key={c.code} value={c.code}>{c.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Amount ($)">
          <Input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="w-28" />
        </Field>
        <div className="flex gap-2">
          <Button onClick={() => mut.mutate()} disabled={mut.isPending || !form.description || !form.amount}>
            Save
          </Button>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Reconciliation ─────────────────────────────────────────────────────────────

function ReconciliationTab() {
  const qc = useQueryClient();
  const { data: payouts, isLoading } = useQuery({
    queryKey: ["acct-payouts"],
    queryFn: () => accountingApi.getPayouts().then((r) => r.data),
  });
  const reconMut = useMutation({
    mutationFn: () => accountingApi.reconcile().then((r) => r.data),
    onSuccess: () => {
      toast.success("Refreshed");
      qc.invalidateQueries({ queryKey: ["acct-reconcile-view"] });
      qc.invalidateQueries({ queryKey: ["acct-payouts"] });
    },
    onError: () => toast.error("Refresh failed"),
  });
  const { data: reconResult } = useQuery({
    queryKey: ["acct-reconcile-view"],
    queryFn: () => accountingApi.reconcile().then((r) => r.data),
  });

  if (isLoading) return <Loading />;

  const r = reconResult;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-stone-600">
          Your books are built from the <strong>bank statement</strong> (the authoritative record).
          AuraFlow sales are the itemized detail behind your card deposits.
        </p>
        <Button onClick={() => reconMut.mutate()} disabled={reconMut.isPending} variant="outline">
          {reconMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="ml-2">Refresh</span>
        </Button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Bank income entries" value={String(r?.bank_income_count ?? 0)} tone="emerald" />
        <StatCard label="Bank expense entries" value={String(r?.bank_expense_count ?? 0)} tone="rose" />
        <StatCard label="Internal transfers (excluded)" value={String(r?.bank_transfer_count ?? 0)} tone="amber" />
        <StatCard label="AuraFlow sales tracked" value={String(r?.auraflow_sales_count ?? 0)} tone="emerald" />
      </div>

      {(payouts?.length ?? 0) > 0 && (
        <Card>
          <CardHeader><CardTitle>Processor payouts</CardTitle></CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-stone-500 border-b border-stone-200">
                  <th className="p-3">Date</th>
                  <th className="p-3">Provider</th>
                  <th className="p-3 text-right">Net (deposit)</th>
                </tr>
              </thead>
              <tbody>
                {payouts!.map((p) => (
                  <tr key={p.id} className="border-b border-stone-100">
                    <td className="p-3">{p.payout_date ?? "—"}</td>
                    <td className="p-3 capitalize">{p.provider}</td>
                    <td className="p-3 text-right tabular-nums">{fmt(p.net_cents)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Members (K-1) ──────────────────────────────────────────────────────────────

function MembersTab({ year }: { year: number }) {
  const qc = useQueryClient();
  const { data: members } = useQuery({
    queryKey: ["acct-members"],
    queryFn: () => accountingApi.getMembers().then((r) => r.data),
  });
  const { data: k1 } = useQuery({
    queryKey: ["acct-k1", year],
    queryFn: () => accountingApi.memberAllocation(year).then((r) => r.data),
  });

  const [form, setForm] = useState({ name: "", email: "", ownership_pct: "", capital: "" });
  const createMut = useMutation({
    mutationFn: () =>
      accountingApi.createMember({
        name: form.name,
        email: form.email || null,
        ownership_pct: parseFloat(form.ownership_pct || "0"),
        capital_cents: Math.round(parseFloat(form.capital || "0") * 100),
      }),
    onSuccess: () => {
      toast.success("Member added");
      setForm({ name: "", email: "", ownership_pct: "", capital: "" });
      qc.invalidateQueries({ queryKey: ["acct-members"] });
      qc.invalidateQueries({ queryKey: ["acct-k1"] });
    },
    onError: () => toast.error("Failed"),
  });
  const delMut = useMutation({
    mutationFn: (id: string) => accountingApi.deleteMember(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["acct-members"] });
      qc.invalidateQueries({ queryKey: ["acct-k1"] });
    },
  });

  const totalOwnership = (members ?? []).reduce((s: number, m: AccountingMember) => s + Number(m.ownership_pct), 0);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 flex flex-wrap items-end gap-3">
          <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Email"><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Ownership %"><Input type="number" step="0.001" className="w-28" value={form.ownership_pct} onChange={(e) => setForm({ ...form, ownership_pct: e.target.value })} /></Field>
          <Field label="Capital ($)"><Input type="number" step="0.01" className="w-32" value={form.capital} onChange={(e) => setForm({ ...form, capital: e.target.value })} /></Field>
          <Button onClick={() => createMut.mutate()} disabled={createMut.isPending || !form.name}>
            <Plus className="h-4 w-4 mr-1" /> Add partner
          </Button>
        </CardContent>
      </Card>

      {totalOwnership !== 100 && (members ?? []).length > 0 && (
        <p className="text-sm text-amber-600 flex items-center gap-1">
          <AlertTriangle className="h-4 w-4" /> Ownership sums to {totalOwnership}% (should be 100%).
        </p>
      )}

      <Card>
        <CardHeader><CardTitle>Partner allocation — {year}</CardTitle></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-stone-500 border-b border-stone-200">
                <th className="p-3">Partner</th>
                <th className="p-3 text-right">Ownership</th>
                <th className="p-3 text-right">Share of income</th>
                <th className="p-3 text-right">Net allocation</th>
                <th className="p-3 text-right">Distributions</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {(k1?.allocations ?? []).length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-stone-400 italic">No partners on file</td></tr>
              )}
              {(k1?.allocations ?? []).map((a) => (
                <tr key={a.id} className="border-b border-stone-100">
                  <td className="p-3">{a.name}</td>
                  <td className="p-3 text-right tabular-nums">{a.ownership_pct.toFixed(2)}%</td>
                  <td className="p-3 text-right tabular-nums">{fmt(a.share_income_cents)}</td>
                  <td className="p-3 text-right tabular-nums">{fmt(a.net_allocation_cents)}</td>
                  <td className="p-3 text-right tabular-nums">{fmt(a.distributions_cents)}</td>
                  <td className="p-3">
                    <button onClick={() => delMut.mutate(a.id)} className="text-stone-400 hover:text-rose-600">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Settings ───────────────────────────────────────────────────────────────────

function SettingsTab({ year }: { year: number }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["acct-settings"],
    queryFn: () => accountingApi.getSettings().then((r) => r.data),
  });
  const [form, setForm] = useState<Record<string, string>>({});
  const [key, setKey] = useState("");

  const saveMut = useMutation({
    mutationFn: () =>
      accountingApi.updateSettings({
        ...form,
        ...(key ? { mercury_api_key: key } : {}),
      }),
    onSuccess: () => {
      toast.success("Settings saved");
      setKey("");
      setForm({});
      qc.invalidateQueries({ queryKey: ["acct-settings"] });
    },
    onError: () => toast.error("Save failed"),
  });

  if (isLoading || !data) return <Loading />;
  const val = (f: string) => form[f] ?? (data as unknown as Record<string, string>)[f] ?? "";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Building2 className="h-4 w-4" /> LLC identity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field label="Legal name"><Input value={val("llc_name")} onChange={(e) => setForm({ ...form, llc_name: e.target.value })} /></Field>
          <Field label="EIN"><Input value={val("llc_ein")} onChange={(e) => setForm({ ...form, llc_ein: e.target.value })} /></Field>
          <Field label="State"><Input value={val("llc_state")} onChange={(e) => setForm({ ...form, llc_state: e.target.value })} /></Field>
          <Field label="Tax classification">
            <select
              value={val("llc_tax_class")}
              onChange={(e) => setForm({ ...form, llc_tax_class: e.target.value })}
              className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm bg-white"
            >
              <option value="">—</option>
              {["Sole Proprietor", "Single-Member LLC", "Partnership", "S-Corp", "C-Corp"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Landmark className="h-4 w-4" /> Mercury bank feed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-stone-500">
            Paste your Mercury API key to auto-import every bank transaction (read-only).
            {data.mercury_connected && (
              <span className="text-emerald-600"> Connected ({data.mercury_api_key}).</span>
            )}
          </p>
          <Field label="Mercury API key">
            <Input
              type="password"
              placeholder={data.mercury_connected ? "•••• (leave blank to keep)" : "secret-token-..."}
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </Field>
          {data.last_sync_at && (
            <p className="text-xs text-stone-400">Last sync: {new Date(data.last_sync_at).toLocaleString()}</p>
          )}
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader><CardTitle className="flex items-center gap-2"><FileText className="h-4 w-4" /> Tax export — {year}</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={() => accountingApi.exportTxf(year)}>
            <Download className="h-4 w-4 mr-1" /> TurboTax (.txf)
          </Button>
          <Button variant="outline" onClick={() => accountingApi.exportPdf(year)}>
            <Download className="h-4 w-4 mr-1" /> Accountant PDF
          </Button>
          <span className="text-xs text-stone-400">
            Import the .txf into TurboTax Desktop, or hand the PDF to your accountant.
          </span>
        </CardContent>
      </Card>

      <div className="lg:col-span-2">
        <OwnerDrawsCard />
      </div>

      <div className="lg:col-span-2">
        <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
          {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          Save settings
        </Button>
      </div>
    </div>
  );
}

function OwnerDrawsCard() {
  const qc = useQueryClient();
  const { data: draws } = useQuery({
    queryKey: ["acct-owner-draws"],
    queryFn: () => accountingApi.getOwnerDraws().then((r) => r.data),
  });
  const [form, setForm] = useState({ owner_pattern: "", monthly: "", from: "", to: "" });
  const createMut = useMutation({
    mutationFn: () =>
      accountingApi.createOwnerDraw({
        owner_pattern: form.owner_pattern,
        monthly_cents: Math.round(parseFloat(form.monthly || "0") * 100),
        effective_from: form.from,
        effective_to: form.to || null,
      }),
    onSuccess: () => {
      toast.success("Draw rule added");
      setForm({ owner_pattern: "", monthly: "", from: "", to: "" });
      qc.invalidateQueries({ queryKey: ["acct-owner-draws"] });
    },
    onError: () => toast.error("Failed — check the fields"),
  });
  const delMut = useMutation({
    mutationFn: (id: string) => accountingApi.deleteOwnerDraw(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["acct-owner-draws"] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Banknote className="h-4 w-4" /> Owner Draws
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-stone-500">
          Set each owner&apos;s fixed monthly draw. On every sync, that amount is booked as a
          <strong> Distribution</strong> and anything they were paid above it becomes wages.
          AuraFlow can&apos;t know your draws — you define them here.
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-stone-500 border-b border-stone-200">
              <th className="p-2">Owner</th>
              <th className="p-2 text-right">Monthly draw</th>
              <th className="p-2">From</th>
              <th className="p-2">To</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {(draws ?? []).length === 0 && (
              <tr><td colSpan={5} className="p-3 text-stone-400 italic">No draw rules yet</td></tr>
            )}
            {(draws ?? []).map((d) => (
              <tr key={d.id} className="border-b border-stone-100">
                <td className="p-2">{d.owner_pattern}</td>
                <td className="p-2 text-right tabular-nums">{fmt(d.monthly_cents)}/mo</td>
                <td className="p-2">{d.effective_from}</td>
                <td className="p-2">{d.effective_to ?? "ongoing"}</td>
                <td className="p-2">
                  <button onClick={() => delMut.mutate(d.id)} className="text-stone-400 hover:text-rose-600">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex flex-wrap items-end gap-2 border-t border-stone-100 pt-3">
          <Field label="Owner (name as it appears on the payout)">
            <Input className="w-44" value={form.owner_pattern} onChange={(e) => setForm({ ...form, owner_pattern: e.target.value })} />
          </Field>
          <Field label="Monthly draw ($)">
            <Input type="number" step="0.01" className="w-28" value={form.monthly} onChange={(e) => setForm({ ...form, monthly: e.target.value })} />
          </Field>
          <Field label="From"><Input type="date" value={form.from} onChange={(e) => setForm({ ...form, from: e.target.value })} /></Field>
          <Field label="To (optional)"><Input type="date" value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })} /></Field>
          <Button onClick={() => createMut.mutate()} disabled={createMut.isPending || !form.owner_pattern || !form.monthly || !form.from}>
            <Plus className="h-4 w-4 mr-1" /> Add
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Shared bits ────────────────────────────────────────────────────────────────

function Loading() {
  return (
    <div className="flex justify-center py-16">
      <Loader2 className="h-6 w-6 animate-spin text-stone-400" />
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: string; tone: "emerald" | "rose" | "amber" }) {
  const toneMap = {
    emerald: "text-emerald-700",
    rose: "text-rose-700",
    amber: "text-amber-700",
  };
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs uppercase tracking-wide text-stone-500">{label}</p>
        <p className={`text-2xl font-semibold mt-1 tabular-nums ${toneMap[tone]}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function Field({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-xs font-medium text-stone-500 mb-1">{label}</span>
      {children}
    </label>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  placeholder: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-stone-300 bg-white px-3 py-2 text-sm"
    >
      <option value="">{placeholder}</option>
      {options.map(([v, l]) => (
        <option key={v} value={v}>{l}</option>
      ))}
    </select>
  );
}
