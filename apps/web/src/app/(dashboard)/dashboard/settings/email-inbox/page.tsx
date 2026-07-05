"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Mail,
  Loader2,
  CheckCircle2,
  XCircle,
  Settings,
  Wifi,
  WifiOff,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import toast from "react-hot-toast";

// ── Types ────────────────────────────────────────────────────────────────────

interface EmailConnectionStatus {
  connected: boolean;
  email_address: string | null;
  display_name: string | null;
  last_checked: string | null;
  status: "connected" | "error" | "disconnected";
  error_message: string | null;
}

interface ProviderPreset {
  name: string;
  imap_host: string;
  imap_port: number;
  smtp_host: string;
  smtp_port: number;
}

const PRESETS: ProviderPreset[] = [
  {
    name: "Gmail",
    imap_host: "imap.gmail.com",
    imap_port: 993,
    smtp_host: "smtp.gmail.com",
    smtp_port: 465,
  },
  {
    name: "Outlook",
    imap_host: "outlook.office365.com",
    imap_port: 993,
    smtp_host: "outlook.office365.com",
    smtp_port: 587,
  },
  {
    name: "Purelymail",
    imap_host: "imap.purelymail.com",
    imap_port: 993,
    smtp_host: "smtp.purelymail.com",
    smtp_port: 587,
  },
  {
    name: "Custom",
    imap_host: "",
    imap_port: 993,
    smtp_host: "",
    smtp_port: 465,
  },
];

// ── Page ─────────────────────────────────────────────────────────────────────

export default function EmailInboxSettingsPage() {
  const queryClient = useQueryClient();

  const [emailAddress, setEmailAddress] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState(993);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState(465);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [imapTls, setImapTls] = useState(true);
  const [smtpTls, setSmtpTls] = useState(true);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);

  const {
    data: status,
    isLoading,
    isError,
    error: statusError,
  } = useQuery({
    queryKey: ["studio-email-status"],
    queryFn: async () => {
      try {
        const r = await apiClient.get("/studio-email/status");
        const raw = (r as any)?.data ?? r;
        const d = raw?.data ?? raw;
        const isConn = !!(d?.connected || d?.is_active || d?.email_address);
        return {
          connected: isConn,
          email_address: d?.email_address || null,
          display_name: d?.display_name || null,
          last_checked: d?.last_checked_at || null,
          status: isConn ? "connected" : "disconnected",
          error_message: null,
        } as EmailConnectionStatus;
      } catch {
        return {
          connected: false,
          email_address: null,
          display_name: null,
          last_checked: null,
          status: "disconnected",
          error_message: "Could not check status",
        } as EmailConnectionStatus;
      }
    },
    retry: 2,
    staleTime: 30000,
  });

  const connectMutation = useMutation({
    mutationFn: () =>
      apiClient.post("/studio-email/connect", {
        email_address: emailAddress,
        display_name: displayName || "Studio",
        imap_host: imapHost,
        imap_port: imapPort,
        smtp_host: smtpHost,
        smtp_port: smtpPort,
        username: (username || emailAddress).trim(),
        password: password.trim(),
        imap_use_tls: imapTls,
        smtp_use_tls: smtpTls,
      }),
    onSuccess: () => {
      toast.success("Email account connected successfully");
      queryClient.invalidateQueries({ queryKey: ["studio-email-status"] });
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || "Failed to connect email account"),
  });

  const disconnectMutation = useMutation({
    mutationFn: () => apiClient.post("/studio-email/disconnect"),
    onSuccess: () => {
      toast.success("Email account disconnected");
      queryClient.invalidateQueries({ queryKey: ["studio-email-status"] });
    },
    onError: () => toast.error("Failed to disconnect"),
  });

  function applyPreset(preset: ProviderPreset) {
    setSelectedPreset(preset.name);
    setImapHost(preset.imap_host);
    setImapPort(preset.imap_port);
    setSmtpHost(preset.smtp_host);
    setSmtpPort(preset.smtp_port);
    if (preset.name !== "Custom") {
      setImapTls(true);
      setSmtpTls(true);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────

  if (isError) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Email Inbox</h2>
          <p className="text-sm text-gray-500">
            Connect your studio email for AI-powered inbox management
          </p>
        </div>
        <Card>
          <CardContent className="py-8">
            <div className="flex flex-col items-center gap-3 text-center">
              <XCircle className="h-10 w-10 text-red-400" />
              <p className="text-sm font-medium text-red-700">
                Error loading email status
              </p>
              <p className="text-xs text-gray-500">
                {(statusError as any)?.message || "Could not reach the server. Please try again."}
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  queryClient.invalidateQueries({
                    queryKey: ["studio-email-status"],
                  })
                }
              >
                Retry
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Connected state ──────────────────────────────────────────────────────

  if (status?.connected) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Email Inbox</h2>
          <p className="text-sm text-gray-500">
            Connect your studio email for AI-powered inbox management
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wifi className="h-5 w-5 text-green-600" />
              Connected
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium text-gray-500">Email Address</p>
                <p className="text-sm text-gray-900">{status.email_address}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Display Name</p>
                <p className="text-sm text-gray-900">{status.display_name || "—"}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Last Checked</p>
                <p className="text-sm text-gray-900">
                  {status.last_checked
                    ? new Date(status.last_checked).toLocaleString()
                    : "Never"}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-500">Status</p>
                <span className="inline-flex items-center gap-1 text-sm">
                  {status.status === "connected" ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                      <span className="text-green-700">Connected</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 text-red-600" />
                      <span className="text-red-700">Error</span>
                    </>
                  )}
                </span>
              </div>
            </div>

            {status.error_message && (
              <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {status.error_message}
              </div>
            )}

            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    const r = await apiClient.post("/studio-email/test");
                    const d = (r as any).data?.data || (r as any).data;
                    if (d?.imap && d?.smtp) toast.success("Connection test passed: IMAP ✓ SMTP ✓");
                    else if (d?.imap) toast.success("IMAP ✓ | SMTP failed: " + (d?.smtp_error || "unknown"));
                    else toast.error("Connection test failed: " + (d?.imap_error || "unknown"));
                  } catch { toast.error("Test failed"); }
                }}
              >
                <Settings className="mr-2 h-4 w-4" />
                Test Connection
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  disconnectMutation.mutate();
                }}
                className="text-amber-600 hover:bg-amber-50"
                disabled={disconnectMutation.isPending}
              >
                Reconnect with New Password
              </Button>
              <Button
                variant="outline"
                className="text-red-600 hover:bg-red-50"
                onClick={() => {
                  if (window.confirm("Disconnect email account? Inbox messages will be kept.")) {
                    disconnectMutation.mutate();
                  }
                }}
                disabled={disconnectMutation.isPending}
              >
                {disconnectMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <WifiOff className="mr-2 h-4 w-4" />
                )}
                Disconnect
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Not connected — setup form ───────────────────────────────────────────

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Email Inbox</h2>
        <p className="text-sm text-gray-500">
          Connect your studio email for AI-powered inbox management
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mail className="h-5 w-5 text-indigo-600" />
            Connect Email Account
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Provider Presets */}
          <div>
            <Label className="mb-2 block">Provider Preset</Label>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  onClick={() => applyPreset(preset)}
                  className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                    selectedPreset === preset.name
                      ? "border-indigo-600 bg-indigo-50 text-indigo-700"
                      : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </div>

          {/* Email & Display Name */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="email">Email Address</Label>
              <Input
                id="email"
                type="email"
                placeholder="studio@example.com"
                value={emailAddress}
                onChange={(e) => setEmailAddress(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="displayName">Display Name</Label>
              <Input
                id="displayName"
                placeholder="Your Studio"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          </div>

          {/* IMAP Settings */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-gray-700">IMAP Settings (Incoming)</h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <Label htmlFor="imapHost">IMAP Host</Label>
                <Input
                  id="imapHost"
                  placeholder="imap.example.com"
                  value={imapHost}
                  onChange={(e) => setImapHost(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="imapPort">IMAP Port</Label>
                <Input
                  id="imapPort"
                  type="number"
                  value={imapPort}
                  onChange={(e) => setImapPort(Number(e.target.value))}
                />
              </div>
            </div>
            <label className="mt-2 flex items-center gap-2">
              <input
                type="checkbox"
                checked={imapTls}
                onChange={(e) => setImapTls(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
              <span className="text-sm text-gray-600">Use TLS</span>
            </label>
          </div>

          {/* SMTP Settings */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-gray-700">SMTP Settings (Outgoing)</h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <Label htmlFor="smtpHost">SMTP Host</Label>
                <Input
                  id="smtpHost"
                  placeholder="smtp.example.com"
                  value={smtpHost}
                  onChange={(e) => setSmtpHost(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="smtpPort">SMTP Port</Label>
                <Input
                  id="smtpPort"
                  type="number"
                  value={smtpPort}
                  onChange={(e) => setSmtpPort(Number(e.target.value))}
                />
              </div>
            </div>
            <label className="mt-2 flex items-center gap-2">
              <input
                type="checkbox"
                checked={smtpTls}
                onChange={(e) => setSmtpTls(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
              <span className="text-sm text-gray-600">Use TLS</span>
            </label>
          </div>

          {/* Credentials */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-gray-700">Credentials</h3>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  placeholder="studio@example.com"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="App password or account password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>
          </div>

          <Button
            onClick={() => connectMutation.mutate()}
            disabled={
              connectMutation.isPending ||
              !emailAddress ||
              !imapHost ||
              !smtpHost ||
              !username ||
              !password
            }
            className="bg-indigo-600 hover:bg-indigo-700"
          >
            {connectMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Settings className="mr-2 h-4 w-4" />
            )}
            Test &amp; Connect
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
