"use client";

import { useEffect, useState } from "react";
import {
  Shield,
  ShieldCheck,
  ShieldOff,
  Bell,
  Mail,
  Smartphone,
  Download,
  Trash2,
  Loader2,
  AlertTriangle,
  Copy,
  Check,
} from "lucide-react";
import toast from "react-hot-toast";

import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function PortalSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [emailOptIn, setEmailOptIn] = useState(true);
  const [smsOptIn, setSmsOptIn] = useState(true);

  // 2FA setup state
  const [mfaSetupUri, setMfaSetupUri] = useState("");
  const [mfaBackupCodes, setMfaBackupCodes] = useState<string[]>([]);
  const [mfaVerifyCode, setMfaVerifyCode] = useState("");
  const [mfaSettingUp, setMfaSettingUp] = useState(false);
  const [mfaVerifying, setMfaVerifying] = useState(false);

  // Disable 2FA state
  const [disablePassword, setDisablePassword] = useState("");
  const [mfaDisabling, setMfaDisabling] = useState(false);
  const [showDisable, setShowDisable] = useState(false);

  // Account actions
  const [exporting, setExporting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [copiedCodes, setCopiedCodes] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  async function loadProfile() {
    try {
      const res = await apiClient.get("/portal/profile");
      const profile = res.data?.data ?? res.data;
      setEmailOptIn(profile.email_opt_in ?? true);
      setSmsOptIn(profile.sms_opt_in ?? true);
      setMfaEnabled(profile.mfa_enabled ?? false);
    } catch {
      // Profile may not have mfa_enabled field
    } finally {
      setLoading(false);
    }
  }

  // ── 2FA Setup ───────────────────────────────────────────────────────────
  async function handleSetup2FA() {
    setMfaSettingUp(true);
    try {
      const res = await apiClient.post("/auth/mfa/setup");
      const data = res.data?.data ?? res.data;
      setMfaSetupUri(data.provisioning_uri || data.uri || "");
      setMfaBackupCodes(data.backup_codes || []);
    } catch {
      toast.error("Failed to start 2FA setup");
    } finally {
      setMfaSettingUp(false);
    }
  }

  async function handleVerify2FA() {
    if (!mfaVerifyCode || mfaVerifyCode.length < 6) {
      toast.error("Enter a 6-digit code from your authenticator app");
      return;
    }
    setMfaVerifying(true);
    try {
      await apiClient.post("/auth/mfa/verify-setup", { code: mfaVerifyCode });
      toast.success("Two-factor authentication enabled!");
      setMfaEnabled(true);
      setMfaSetupUri("");
      setMfaBackupCodes([]);
      setMfaVerifyCode("");
    } catch {
      toast.error("Invalid code. Please try again.");
    } finally {
      setMfaVerifying(false);
    }
  }

  async function handleDisable2FA() {
    if (!disablePassword) {
      toast.error("Enter your password to disable 2FA");
      return;
    }
    setMfaDisabling(true);
    try {
      await apiClient.post("/auth/mfa/disable", { password: disablePassword });
      toast.success("Two-factor authentication disabled");
      setMfaEnabled(false);
      setShowDisable(false);
      setDisablePassword("");
    } catch {
      toast.error("Invalid password");
    } finally {
      setMfaDisabling(false);
    }
  }

  // ── Notification Preferences ────────────────────────────────────────────
  async function updatePreference(field: string, value: boolean) {
    try {
      await apiClient.put("/portal/profile", { [field]: value });
      toast.success("Preferences updated");
    } catch {
      toast.error("Failed to update preferences");
    }
  }

  // ── Account Actions ─────────────────────────────────────────────────────
  async function handleExportData() {
    setExporting(true);
    try {
      const res = await apiClient.get("/gdpr/data-export");
      const blob = new Blob([JSON.stringify(res.data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "my-data-export.json";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Data exported successfully");
    } catch {
      toast.error("Failed to export data");
    } finally {
      setExporting(false);
    }
  }

  async function handleDeleteAccount() {
    setDeleting(true);
    try {
      await apiClient.post("/gdpr/deletion-request");
      toast.success(
        "Account deletion requested. You have 30 days to cancel."
      );
      setShowDeleteConfirm(false);
    } catch {
      toast.error("Failed to request account deletion");
    } finally {
      setDeleting(false);
    }
  }

  function copyBackupCodes() {
    navigator.clipboard.writeText(mfaBackupCodes.join("\n"));
    setCopiedCodes(true);
    setTimeout(() => setCopiedCodes(false), 2000);
    toast.success("Backup codes copied to clipboard");
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">
        Account Settings
      </h1>

      <div className="space-y-6">
        {/* ── Two-Factor Authentication ────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Two-Factor Authentication
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              {mfaEnabled ? (
                <>
                  <ShieldCheck className="h-5 w-5 text-green-600" />
                  <span className="font-medium text-green-700">
                    2FA is enabled
                  </span>
                </>
              ) : (
                <>
                  <ShieldOff className="h-5 w-5 text-gray-400" />
                  <span className="text-gray-600">2FA is not enabled</span>
                </>
              )}
            </div>

            {!mfaEnabled && !mfaSetupUri && (
              <Button onClick={handleSetup2FA} disabled={mfaSettingUp}>
                {mfaSettingUp ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Shield className="mr-2 h-4 w-4" />
                )}
                Enable 2FA
              </Button>
            )}

            {mfaSetupUri && (
              <div className="space-y-4 rounded-lg border border-indigo-200 bg-indigo-50 p-4">
                <div>
                  <p className="mb-2 text-sm font-medium text-gray-700">
                    1. Scan this code with your authenticator app (Google
                    Authenticator, Authy, etc.):
                  </p>
                  <code className="block break-all rounded bg-white p-3 text-xs text-gray-700">
                    {mfaSetupUri}
                  </code>
                </div>

                {mfaBackupCodes.length > 0 && (
                  <div>
                    <p className="mb-2 text-sm font-medium text-gray-700">
                      2. Save these backup codes somewhere safe:
                    </p>
                    <div className="rounded bg-white p-3">
                      <div className="grid grid-cols-2 gap-1">
                        {mfaBackupCodes.map((code) => (
                          <code key={code} className="text-sm text-gray-700">
                            {code}
                          </code>
                        ))}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="mt-2"
                        onClick={copyBackupCodes}
                      >
                        {copiedCodes ? (
                          <Check className="mr-1.5 h-3.5 w-3.5" />
                        ) : (
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        {copiedCodes ? "Copied" : "Copy codes"}
                      </Button>
                    </div>
                  </div>
                )}

                <div>
                  <Label className="mb-1.5 text-sm font-medium text-gray-700">
                    3. Enter the 6-digit code from your app:
                  </Label>
                  <div className="flex gap-2">
                    <Input
                      value={mfaVerifyCode}
                      onChange={(e) => setMfaVerifyCode(e.target.value)}
                      placeholder="000000"
                      maxLength={6}
                      className="w-32"
                    />
                    <Button
                      onClick={handleVerify2FA}
                      disabled={mfaVerifying}
                    >
                      {mfaVerifying ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Verify
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {mfaEnabled && !showDisable && (
              <Button
                variant="outline"
                onClick={() => setShowDisable(true)}
                className="text-red-600 hover:bg-red-50 hover:text-red-700"
              >
                Disable 2FA
              </Button>
            )}

            {showDisable && (
              <div className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="text-sm text-red-700">
                  Enter your password to confirm disabling 2FA:
                </p>
                <div className="flex gap-2">
                  <Input
                    type="password"
                    value={disablePassword}
                    onChange={(e) => setDisablePassword(e.target.value)}
                    placeholder="Your password"
                    className="max-w-xs"
                  />
                  <Button
                    variant="default" className="bg-red-600 hover:bg-red-700 text-white"
                    onClick={handleDisable2FA}
                    disabled={mfaDisabling}
                  >
                    {mfaDisabling && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}
                    Confirm
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setShowDisable(false);
                      setDisablePassword("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Notification Preferences ─────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              Notification Preferences
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex cursor-pointer items-center justify-between rounded-lg border p-4 transition-colors hover:bg-gray-50">
              <div className="flex items-center gap-3">
                <Mail className="h-5 w-5 text-gray-500" />
                <div>
                  <p className="font-medium text-gray-900">
                    Email notifications
                  </p>
                  <p className="text-sm text-gray-500">
                    Booking confirmations, reminders, and promotions
                  </p>
                </div>
              </div>
              <input
                type="checkbox"
                checked={emailOptIn}
                onChange={(e) => {
                  setEmailOptIn(e.target.checked);
                  updatePreference("email_opt_in", e.target.checked);
                }}
                className="h-5 w-5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
            </label>

            <label className="flex cursor-pointer items-center justify-between rounded-lg border p-4 transition-colors hover:bg-gray-50">
              <div className="flex items-center gap-3">
                <Smartphone className="h-5 w-5 text-gray-500" />
                <div>
                  <p className="font-medium text-gray-900">
                    SMS notifications
                  </p>
                  <p className="text-sm text-gray-500">
                    Text reminders for upcoming classes
                  </p>
                </div>
              </div>
              <input
                type="checkbox"
                checked={smsOptIn}
                onChange={(e) => {
                  setSmsOptIn(e.target.checked);
                  updatePreference("sms_opt_in", e.target.checked);
                }}
                className="h-5 w-5 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
            </label>
          </CardContent>
        </Card>

        {/* ── Account Actions ──────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle>Account Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <p className="font-medium text-gray-900">
                  Download my data
                </p>
                <p className="text-sm text-gray-500">
                  Export a copy of all your personal data
                </p>
              </div>
              <Button
                variant="outline"
                onClick={handleExportData}
                disabled={exporting}
              >
                {exporting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                Export
              </Button>
            </div>

            <div className="flex items-center justify-between rounded-lg border border-red-200 p-4">
              <div>
                <p className="font-medium text-red-700">Delete my account</p>
                <p className="text-sm text-gray-500">
                  Permanently delete your account and all data. You have 30
                  days to cancel.
                </p>
              </div>
              {!showDeleteConfirm ? (
                <Button
                  variant="outline"
                  className="text-red-600 hover:bg-red-50 hover:text-red-700"
                  onClick={() => setShowDeleteConfirm(true)}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete
                </Button>
              ) : (
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-red-600" />
                  <Button
                    variant="default" className="bg-red-600 hover:bg-red-700 text-white"
                    size="sm"
                    onClick={handleDeleteAccount}
                    disabled={deleting}
                  >
                    {deleting && (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    )}
                    Confirm Delete
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowDeleteConfirm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
