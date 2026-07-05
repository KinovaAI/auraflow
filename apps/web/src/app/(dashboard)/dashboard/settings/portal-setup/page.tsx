"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Circle,
  Loader2,
  Copy,
  ExternalLink,
  Trash2,
  Plus,
  AlertCircle,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { portalSetupApi } from "@/lib/portal-setup-api";

export default function PortalSetupPage() {
  const qc = useQueryClient();
  const { data: statusResp, isLoading } = useQuery({
    queryKey: ["portal-setup-status"],
    queryFn: () => portalSetupApi.status().then((r) => r.data),
    refetchInterval: 30_000,
  });
  const { data: deployResp } = useQuery({
    queryKey: ["portal-setup-deploy"],
    queryFn: () => portalSetupApi.deployConfig().then((r) => r.data),
    enabled: !!statusResp?.ready_to_deploy,
  });

  const [newOrigin, setNewOrigin] = useState("");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  // Brand editor state — hydrated from status.current_brand on first load.
  const [brand, setBrand] = useState({
    name: "",
    logo_url: "",
    primary_color: "#4F46E5",
    on_primary_color: "#ffffff",
    surface_color: "#fafafa",
    on_surface_color: "#1a1a1a",
  });
  const [brandDirty, setBrandDirty] = useState(false);

  // Hydrate brand state when status resolves.
  useEffect(() => {
    if (statusResp?.current_brand && !brandDirty) {
      setBrand({
        name: statusResp.current_brand.name ?? "",
        logo_url: statusResp.current_brand.logo_url ?? "",
        primary_color: statusResp.current_brand.primary_color ?? "#4F46E5",
        on_primary_color: statusResp.current_brand.on_primary_color ?? "#ffffff",
        surface_color: statusResp.current_brand.surface_color ?? "#fafafa",
        on_surface_color: statusResp.current_brand.on_surface_color ?? "#1a1a1a",
      });
    }
    // Intentionally omit brandDirty + brand from deps — we only want to
    // hydrate once per status refetch, not fight user edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusResp?.current_brand]);

  const setBrandField = (field: keyof typeof brand, value: string) => {
    setBrand((prev) => ({ ...prev, [field]: value }));
    setBrandDirty(true);
  };

  const saveBrand = useMutation({
    mutationFn: () =>
      portalSetupApi
        .updateBrand({
          name: brand.name || undefined,
          logo_url: brand.logo_url || undefined,
          primary_color: brand.primary_color,
          on_primary_color: brand.on_primary_color,
          surface_color: brand.surface_color,
          on_surface_color: brand.on_surface_color,
        })
        .then((r) => r.data),
    onSuccess: () => {
      toast.success("Brand updated — portal will reflect within 60s");
      setBrandDirty(false);
      qc.invalidateQueries({ queryKey: ["portal-setup-status"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed"),
  });

  const mintKey = useMutation({
    mutationFn: () => portalSetupApi.mintApiKey().then((r) => r.data),
    onSuccess: (d) => {
      setRevealedKey(d.raw_key);
      toast.success("API key minted — copy it now");
      qc.invalidateQueries({ queryKey: ["portal-setup-status"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed"),
  });

  const addOrigin = useMutation({
    mutationFn: (origin: string) =>
      portalSetupApi.addOrigin(origin).then((r) => r.data),
    onSuccess: () => {
      setNewOrigin("");
      toast.success("Origin added");
      qc.invalidateQueries({ queryKey: ["portal-setup-status"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? "Failed"),
  });

  const removeOrigin = useMutation({
    mutationFn: (origin: string) =>
      portalSetupApi.removeOrigin(origin).then((r) => r.data),
    onSuccess: () => {
      toast.success("Origin removed");
      qc.invalidateQueries({ queryKey: ["portal-setup-status"] });
    },
  });

  if (isLoading || !statusResp) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    );
  }

  const s = statusResp;
  const Step = ({
    done,
    title,
    children,
  }: { done: boolean; title: string; children?: React.ReactNode }) => (
    <div className="flex items-start gap-3">
      {done ? (
        <CheckCircle2 className="h-6 w-6 flex-shrink-0 text-green-600" />
      ) : (
        <Circle className="h-6 w-6 flex-shrink-0 text-gray-300" />
      )}
      <div className="flex-1 min-w-0">
        <div className={`font-medium ${done ? "text-gray-700" : "text-gray-900"}`}>{title}</div>
        {children && <div className="mt-2">{children}</div>}
      </div>
    </div>
  );

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied`);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">White-label Portal Setup</h1>
        <p className="mt-1 text-sm text-gray-500">
          Customers run their own member portal on their own domain, talking to AuraFlow.
          This wizard walks you through everything they need.
        </p>
        {!s.ready_to_deploy && (
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-blue-50 px-4 py-3 text-sm text-blue-900">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>Next: <strong>{s.next_step_label}</strong></span>
          </div>
        )}
        {s.ready_to_deploy && (
          <div className="mt-4 flex items-center gap-2 rounded-lg bg-green-50 px-4 py-3 text-sm text-green-900">
            <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
            <span>Ready to deploy — copy the env vars below into your host.</span>
          </div>
        )}
      </div>

      {/* Step 1: Brand editor */}
      <Card>
        <CardHeader><CardTitle className="text-base">1. Brand</CardTitle></CardHeader>
        <CardContent>
          <Step done={s.checklist.brand.done} title="Studio logo and colors">
            <p className="text-sm text-gray-500 mb-4">
              These are the brand tokens your portal uses. Changes propagate to the live
              portal within 60 seconds — no rebuild or redeploy.
            </p>

            <div className="space-y-4">
              <div>
                <Label className="text-xs">Studio name</Label>
                <Input
                  value={brand.name}
                  onChange={(e) => setBrandField("name", e.target.value)}
                  placeholder="Your Studio"
                  className="mt-1"
                />
              </div>

              <div>
                <Label className="text-xs">Logo URL (https only)</Label>
                <Input
                  value={brand.logo_url}
                  onChange={(e) => setBrandField("logo_url", e.target.value)}
                  placeholder="https://your-cdn.com/logo.png"
                  className="mt-1"
                />
                {brand.logo_url && (
                  <div className="mt-2 rounded border border-gray-200 p-2 bg-gray-50 inline-block">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={brand.logo_url}
                      alt="logo preview"
                      style={{ maxHeight: 48, maxWidth: 200 }}
                    />
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <ColorField
                  label="Primary (buttons, links)"
                  value={brand.primary_color}
                  onChange={(v) => setBrandField("primary_color", v)}
                />
                <ColorField
                  label="On primary (text on buttons)"
                  value={brand.on_primary_color}
                  onChange={(v) => setBrandField("on_primary_color", v)}
                />
                <ColorField
                  label="Surface (backgrounds)"
                  value={brand.surface_color}
                  onChange={(v) => setBrandField("surface_color", v)}
                />
                <ColorField
                  label="On surface (body text)"
                  value={brand.on_surface_color}
                  onChange={(v) => setBrandField("on_surface_color", v)}
                />
              </div>

              {/* Live preview */}
              <div>
                <Label className="text-xs">Preview</Label>
                <div
                  className="mt-1 rounded-lg border border-gray-200 p-4"
                  style={{
                    backgroundColor: brand.surface_color,
                    color: brand.on_surface_color,
                  }}
                >
                  <div className="font-semibold" style={{ fontSize: 16 }}>
                    {brand.name || "Your Studio"}
                  </div>
                  <div style={{ opacity: 0.7, fontSize: 13, marginTop: 4 }}>
                    Book a class · Manage membership · Profile
                  </div>
                  <button
                    type="button"
                    className="mt-3 rounded-md px-3 py-1.5 text-sm font-medium"
                    style={{
                      backgroundColor: brand.primary_color,
                      color: brand.on_primary_color,
                    }}
                  >
                    Book a Class
                  </button>
                </div>
              </div>

              <div className="flex justify-end">
                <Button
                  size="sm"
                  onClick={() => saveBrand.mutate()}
                  disabled={!brandDirty || saveBrand.isPending}
                >
                  {saveBrand.isPending ? (
                    <><Loader2 className="h-3 w-3 mr-2 animate-spin" /> Saving…</>
                  ) : (
                    <>Save brand</>
                  )}
                </Button>
              </div>
            </div>
          </Step>
        </CardContent>
      </Card>

      {/* Step 2: API key */}
      <Card>
        <CardHeader><CardTitle className="text-base">2. Portal API key</CardTitle></CardHeader>
        <CardContent>
          <Step
            done={s.checklist.api_key.done}
            title={
              s.checklist.api_key.done
                ? `${s.checklist.api_key.active_count} active key${s.checklist.api_key.active_count > 1 ? "s" : ""}`
                : "No portal API key yet"
            }
          >
            <p className="text-sm text-gray-500">
              The portal authenticates to AuraFlow with this key. Server-side only —
              never exposed to browsers.
            </p>
            {revealedKey ? (
              <div className="mt-3 rounded-lg border border-yellow-300 bg-yellow-50 p-3">
                <p className="text-xs font-medium text-yellow-900 mb-2">
                  Copy this key now — it will not be shown again.
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all text-xs bg-white px-2 py-1 rounded border border-yellow-200">
                    {revealedKey}
                  </code>
                  <Button size="sm" variant="outline" onClick={() => copy(revealedKey, "API key")}>
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                size="sm"
                className="mt-2"
                onClick={() => mintKey.mutate()}
                disabled={mintKey.isPending}
              >
                {mintKey.isPending ? (
                  <><Loader2 className="h-3 w-3 mr-2 animate-spin" /> Minting…</>
                ) : (
                  <>{s.checklist.api_key.done ? "Mint another key" : "Mint API key"}</>
                )}
              </Button>
            )}
          </Step>
        </CardContent>
      </Card>

      {/* Step 3: Origins */}
      <Card>
        <CardHeader><CardTitle className="text-base">3. Portal domain</CardTitle></CardHeader>
        <CardContent>
          <Step
            done={s.checklist.origins.done}
            title={
              s.checklist.origins.done
                ? `${s.checklist.origins.origins.length} domain${s.checklist.origins.origins.length > 1 ? "s" : ""} authorized`
                : "No portal domain authorized yet"
            }
          >
            <p className="text-sm text-gray-500">
              The full origin (scheme + host) where the portal will run, e.g.
              <code className="px-1 bg-gray-100 rounded">https://portal.your-studio.com</code>.
              Required for CORS — the browser will refuse API calls otherwise.
            </p>
            <ul className="mt-3 space-y-1">
              {s.checklist.origins.origins.map((o) => (
                <li key={o} className="flex items-center gap-2">
                  <code className="flex-1 text-xs bg-gray-50 px-2 py-1 rounded">{o}</code>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => removeOrigin.mutate(o)}
                    disabled={removeOrigin.isPending}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex gap-2">
              <Input
                placeholder="https://portal.your-studio.com"
                value={newOrigin}
                onChange={(e) => setNewOrigin(e.target.value)}
                className="flex-1 text-sm"
              />
              <Button
                size="sm"
                onClick={() => addOrigin.mutate(newOrigin)}
                disabled={!newOrigin || addOrigin.isPending}
              >
                {addOrigin.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <><Plus className="h-3 w-3 mr-1" /> Add</>
                )}
              </Button>
            </div>
          </Step>
        </CardContent>
      </Card>

      {/* Step 4: Stripe Connect */}
      <Card>
        <CardHeader><CardTitle className="text-base">4. Stripe Connect (optional)</CardTitle></CardHeader>
        <CardContent>
          <Step
            done={s.checklist.stripe_connect.done}
            title={
              s.checklist.stripe_connect.done
                ? "Connected and accepting charges"
                : s.checklist.stripe_connect.account_id
                  ? "Account connected, charges not yet enabled"
                  : "Not connected"
            }
          >
            <p className="text-sm text-gray-500">
              Required for portal-initiated payments. Skip if your portal won't process payments.
            </p>
            <a
              href="/dashboard/settings/billing"
              className="mt-2 inline-flex items-center gap-1 text-sm text-indigo-600 hover:underline"
            >
              Manage Stripe Connect
              <ExternalLink className="h-3 w-3" />
            </a>
          </Step>
        </CardContent>
      </Card>

      {/* Step 5: Deploy */}
      <Card>
        <CardHeader><CardTitle className="text-base">5. Deploy</CardTitle></CardHeader>
        <CardContent>
          {!s.ready_to_deploy && (
            <p className="text-sm text-gray-500">
              Complete the steps above to unlock deploy instructions.
            </p>
          )}
          {s.ready_to_deploy && deployResp && (
            <div className="space-y-4">
              <div>
                <Label className="text-xs">Env vars</Label>
                <pre className="mt-1 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs overflow-x-auto">{deployResp.env_block}</pre>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2"
                  onClick={() => copy(deployResp.env_block, "Env block")}
                >
                  <Copy className="h-3 w-3 mr-1" /> Copy
                </Button>
              </div>

              <div>
                <Label className="text-xs">Deploy to Vercel (one-click)</Label>
                <div>
                  <a
                    href={deployResp.vercel_deploy_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-flex items-center gap-2 rounded-lg bg-black text-white px-4 py-2 text-sm hover:bg-gray-800"
                  >
                    Deploy with Vercel
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <p className="mt-2 text-xs text-gray-500">
                  Opens Vercel's new-project flow with the AuraFlow portal repo and env-var
                  prompts pre-filled. You'll paste the API key from Step 2 when prompted.
                </p>
              </div>

              <div>
                <Label className="text-xs">Or self-host with Docker Compose</Label>
                <pre className="mt-1 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs overflow-x-auto">{deployResp.docker_compose_snippet}</pre>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2"
                  onClick={() => copy(deployResp.docker_compose_snippet, "Docker snippet")}
                >
                  <Copy className="h-3 w-3 mr-1" /> Copy
                </Button>
              </div>

              <p className="text-xs text-gray-500">
                Source: <a href={deployResp.github_repo} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">{deployResp.github_repo}</a>
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <div className="mt-1 flex items-center gap-2">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-12 rounded border border-gray-300 cursor-pointer"
        />
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          pattern="^#[0-9a-fA-F]{6}$"
          className="flex-1 text-xs font-mono"
        />
      </div>
    </div>
  );
}
