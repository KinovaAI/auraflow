"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Lock, Unlock, Tablet, AlertTriangle, ArrowLeft, Trash2 } from "lucide-react";
import toast from "react-hot-toast";
import { apiClient } from "@/lib/api-client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

// Server-side kiosk device record. The device_token itself never
// leaves the API → cookie — we only see metadata here.
type KioskDevice = {
  id: string;
  label: string;
  is_active: boolean;
  registered_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
};

export default function KioskDevicePage() {
  const router = useRouter();
  const [devices, setDevices] = useState<KioskDevice[]>([]);
  const [label, setLabel] = useState("Front desk iPad");
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);

  const fetchDevices = async () => {
    try {
      const { data } = await apiClient.get<{ data: KioskDevice[] }>(
        "/kiosk-devices",
      );
      setDevices(data.data);
    } catch {
      toast.error("Failed to load kiosk devices");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const register = async () => {
    if (
      !window.confirm(
        "Lock THIS device as a studio kiosk?\n\n" +
          "After locking, this device's browser can only open the check-in kiosk — " +
          "no one will be able to access the dashboard, POS, billing, or settings " +
          "from this device, even if they clear cookies. Only do this on a public " +
          "iPad you intend to leave in kiosk mode.",
      )
    ) {
      return;
    }
    setRegistering(true);
    try {
      await apiClient.post("/kiosk-devices/register", { label });
      toast.success(
        "This device is now kiosk-locked. Reloading...",
      );
      // Reload — the dashboard route will now bounce to /kiosk-locked.
      setTimeout(() => router.refresh(), 800);
      setTimeout(() => router.push("/dashboard/check-in/kiosk"), 1200);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Failed to register device");
      setRegistering(false);
    }
  };

  const revoke = async (id: string, deviceLabel: string) => {
    if (
      !window.confirm(
        `Revoke "${deviceLabel}"?\n\n` +
          `This device will no longer be locked into kiosk mode. ` +
          `Anyone with sign-in credentials will be able to use AuraFlow from it again.`,
      )
    ) {
      return;
    }
    try {
      await apiClient.delete(`/kiosk-devices/${id}`);
      toast.success("Kiosk device revoked");
      fetchDevices();
    } catch {
      toast.error("Failed to revoke device");
    }
  };

  const activeCount = devices.filter((d) => d.is_active).length;

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <button
        onClick={() => router.push("/dashboard/settings")}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Settings
      </button>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Kiosk Devices</h1>
        <p className="mt-1 text-sm text-gray-500">
          Lock an iPad or shared computer to the check-in kiosk only. The
          lock is enforced server-side and survives clearing Safari
          cookies — staff cannot sign in to AuraFlow from a registered
          kiosk device.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Tablet className="h-5 w-5 text-indigo-600" />
            Register this device
          </CardTitle>
          <CardDescription>
            Open this page in Safari on the iPad you want to lock, then
            register. The browser will be permanently restricted to
            <code className="mx-1 rounded bg-gray-100 px-1 text-xs">/dashboard/check-in/kiosk</code>
            until you revoke it from this page on your laptop.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="label">Device label</Label>
            <Input
              id="label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Front desk iPad"
              maxLength={120}
            />
            <p className="mt-1 text-xs text-gray-500">
              Helps you identify the device later. Example: &quot;Lobby iPad&quot;,
              &quot;Saturday market kiosk&quot;.
            </p>
          </div>
          <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              <strong>Only do this on the iPad you intend to lock.</strong>
              {" "}If you lock your own laptop by accident, sign in from
              another device and revoke it from the list below.
            </span>
          </div>
          <Button
            onClick={register}
            disabled={registering || !label.trim()}
            className="bg-indigo-600 hover:bg-indigo-700"
          >
            <Lock className="mr-2 h-4 w-4" />
            {registering ? "Locking..." : "Lock this device as kiosk"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Registered devices</CardTitle>
          <CardDescription>
            {activeCount} active · {devices.length} total
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-gray-500">Loading...</p>
          ) : devices.length === 0 ? (
            <p className="text-sm text-gray-500">
              No kiosk devices registered yet.
            </p>
          ) : (
            <div className="divide-y">
              {devices.map((d) => (
                <div
                  key={d.id}
                  className="flex items-center justify-between py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">
                        {d.label}
                      </span>
                      {d.is_active ? (
                        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                          Active
                        </span>
                      ) : (
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                          Revoked
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      Registered {new Date(d.registered_at).toLocaleString()}
                      {d.last_seen_at && (
                        <> · Last seen {new Date(d.last_seen_at).toLocaleString()}</>
                      )}
                      {d.revoked_at && (
                        <> · Revoked {new Date(d.revoked_at).toLocaleString()}</>
                      )}
                    </div>
                  </div>
                  {d.is_active && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => revoke(d.id, d.label)}
                    >
                      <Trash2 className="mr-1 h-4 w-4" />
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Belt-and-suspenders: iPadOS Guided Access
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-gray-600">
          <p>
            The server-side lock survives clearing Safari cookies and
            switching browsers, but a determined user could still leave
            Safari and use a different browser app. To completely pin the
            iPad to Safari on the kiosk URL, enable{" "}
            <strong>Guided Access</strong> in Settings → Accessibility
            with a PIN only you know. Triple-click the side button to
            start Guided Access when Safari is open on the kiosk page.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
