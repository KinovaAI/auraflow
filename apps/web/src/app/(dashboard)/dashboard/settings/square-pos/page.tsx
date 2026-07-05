"use client";

/**
 * AuraFlow Settings → Square POS Devices
 *
 * Studio owners pair Square hardware (Square Terminal, Square Register)
 * with their studio. Square Reader plugs into an iPhone/iPad and that
 * paired phone/tablet then also acts as an addressable device.
 *
 * Note: the consumer Square POS app on a phone WITHOUT a Square Reader
 * attached does NOT support being a paired Terminal API device — use
 * the "Charge via phone" deep-link flow from POS instead.
 * Once paired, devices are listed here with status indicators; one is
 * marked as the default for the POS sale screen.
 *
 * Pair flow:
 *   1. Click "Pair new device" → server generates a code via Square
 *   2. Modal shows the code + instructions per device type
 *   3. Staff enters the code on the device
 *   4. Frontend polls the device-code endpoint until status=PAIRED
 *   5. Local row appears in the devices list
 */
import { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  CheckCircle,
  Smartphone,
  CreditCard as CardIcon,
  Trash2,
  RefreshCw,
  Plus,
  Pencil,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { paymentsApi, type POSDevice, type POSDeviceCode } from "@/lib/payments-api";

function PairDeviceModal({
  onClose,
  onPaired,
}: {
  onClose: () => void;
  onPaired: () => void;
}) {
  const [phase, setPhase] = useState<"name" | "code" | "polling" | "paired" | "error">("name");
  const [deviceName, setDeviceName] = useState("");
  const [code, setCode] = useState<POSDeviceCode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createCode = useCallback(async () => {
    if (!deviceName.trim()) {
      setError("Give this device a name first (e.g. \"Front Desk Reader\").");
      return;
    }
    setError(null);
    try {
      const resp = await paymentsApi.pairPOSDevice(deviceName.trim());
      setCode(resp.data.data);
      setPhase("polling");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { error?: string } | string } } })
        ?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : detail?.error || "Could not start pairing";
      setError(msg);
      setPhase("error");
    }
  }, [deviceName]);

  // Poll until paired (every 3s, max 5 min)
  useEffect(() => {
    if (phase !== "polling" || !code) return;
    let cancelled = false;
    const start = Date.now();
    const tick = async () => {
      if (cancelled) return;
      if (Date.now() - start > 5 * 60 * 1000) {
        if (!cancelled) {
          setError("Pairing code expired. Try again.");
          setPhase("error");
        }
        return;
      }
      try {
        const resp = await paymentsApi.pollDeviceCode(code.device_code_id);
        if (resp.data.data.status === "PAIRED" && resp.data.data.device_id) {
          setPhase("paired");
          setTimeout(() => onPaired(), 1500);
          return;
        }
      } catch {
        /* keep polling */
      }
      setTimeout(tick, 3000);
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [phase, code, onPaired]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pair-device-title"
    >
      <div className="max-h-[95vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <h3 id="pair-device-title" className="text-lg font-semibold text-gray-900">
          Pair a Square device
        </h3>

        {phase === "name" && (
          <>
            <p className="mt-2 text-sm text-gray-600">
              Give this device a name your staff will recognize. You&apos;ll enter
              the pairing code on the device itself in the next step.
            </p>
            <div className="mt-4">
              <input
                type="text"
                value={deviceName}
                onChange={(e) => setDeviceName(e.target.value)}
                placeholder="e.g. Front Desk Reader, Marco's Phone"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                autoFocus
              />
            </div>
            {error && (
              <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button onClick={createCode}>Next</Button>
            </div>
          </>
        )}

        {(phase === "polling" || phase === "paired") && code && (
          <>
            <p className="mt-2 text-sm text-gray-600">
              On a Square Terminal or Square Register: Settings → Sign in with code → enter:
            </p>
            <div className="my-5 rounded-lg border-2 border-indigo-500 bg-indigo-50 px-6 py-4 text-center">
              <div className="font-mono text-3xl font-bold tracking-widest text-indigo-700">
                {code.code}
              </div>
              {code.pair_by && (
                <div className="mt-1 text-xs text-gray-500">
                  Expires {new Date(code.pair_by).toLocaleTimeString()}
                </div>
              )}
            </div>

            {phase === "polling" && (
              <div className="flex items-center justify-center gap-2 text-sm text-gray-600" role="status">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Waiting for device to pair…
              </div>
            )}

            {phase === "paired" && (
              <div className="flex items-center justify-center gap-2 text-sm text-green-700" role="status">
                <CheckCircle className="h-5 w-5" aria-hidden="true" />
                Paired successfully!
              </div>
            )}

            <div className="mt-6 flex justify-end">
              <Button variant="outline" onClick={onClose}>
                {phase === "paired" ? "Done" : "Cancel"}
              </Button>
            </div>
          </>
        )}

        {phase === "error" && (
          <>
            <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error || "Something went wrong."}
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={onClose}>Close</Button>
              <Button onClick={() => { setPhase("name"); setError(null); }}>Try again</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function RenameDeviceModal({
  device,
  onClose,
  onSaved,
}: {
  device: POSDevice;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(device.name);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await paymentsApi.renamePOSDevice(device.id, { name });
      onSaved();
    } catch {
      toast.error("Rename failed");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-900">Rename device</h3>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-4 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          autoFocus
        />
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function SquarePOSDevicesPage() {
  const [devices, setDevices] = useState<POSDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [pairOpen, setPairOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<POSDevice | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await paymentsApi.listPOSDevices();
      setDevices(resp.data.data);
    } catch {
      toast.error("Failed to load devices");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Refresh device status every 30s so a paired device flipping
    // online/offline mid-shift surfaces without a manual refresh.
    const id = setInterval(() => { load(); }, 30_000);
    return () => clearInterval(id);
  }, [load]);

  const setDefault = async (devicePk: string) => {
    try {
      await paymentsApi.renamePOSDevice(devicePk, { set_as_default: true });
      toast.success("Default device updated");
      load();
    } catch {
      toast.error("Could not set default");
    }
  };

  const unpair = async (devicePk: string, name: string) => {
    if (!confirm(`Unpair "${name}"? This stops AuraFlow from routing charges to it. The device will still work standalone in Square POS.`)) return;
    try {
      await paymentsApi.unpairPOSDevice(devicePk);
      toast.success("Device unpaired");
      load();
    } catch {
      toast.error("Could not unpair");
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Square POS Devices</h1>
          <p className="mt-1 text-sm text-gray-500">
            Square Terminal hardware paired with this studio (plus any phone/tablet with a Square Reader attached).
            Once paired, the POS screen routes charges to the default device.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Refresh
          </Button>
          <Button onClick={() => setPairOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Pair new device
          </Button>
        </div>
      </div>

      {loading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
          </CardContent>
        </Card>
      ) : devices.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Smartphone className="mx-auto mb-3 h-10 w-10 text-gray-300" />
            <p className="text-gray-600">No Square devices paired yet.</p>
            <p className="mt-1 text-sm text-gray-500">
              Pair a Square Terminal or Square Register to take in-person card payments. If you don&apos;t have Square hardware, you can still take card sales from POS using the &quot;Charge via phone&quot; option — that opens Square POS on the same phone you&apos;re using.
            </p>
            <Button className="mt-5" onClick={() => setPairOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Pair your first device
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Paired devices ({devices.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-gray-100">
              {devices.map((d) => (
                <div key={d.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                  <div className="flex items-start gap-3">
                    <div className="rounded-md bg-gray-100 p-2">
                      <CardIcon className="h-5 w-5 text-gray-600" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{d.name}</span>
                        {d.is_default && (
                          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                            Default
                          </span>
                        )}
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                            d.status === "online" || d.status === "paired"
                              ? "bg-green-50 text-green-700"
                              : d.status === "offline"
                                ? "bg-gray-100 text-gray-600"
                                : "bg-amber-50 text-amber-700"
                          }`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-full ${
                            d.status === "online" || d.status === "paired"
                              ? "bg-green-500" : "bg-gray-400"
                          }`} />
                          {d.status}
                        </span>
                      </div>
                      <div className="mt-0.5 text-xs text-gray-400">
                        ID: <code>{d.device_id}</code>
                        {d.paired_at && ` · Paired ${new Date(d.paired_at).toLocaleDateString()}`}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    {!d.is_default && (
                      <Button size="sm" variant="outline" onClick={() => setDefault(d.id)}>
                        Set as default
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => setRenameTarget(d)}>
                      <Pencil className="mr-1.5 h-3.5 w-3.5" />
                      Rename
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => unpair(d.id, d.name)}>
                      <Trash2 className="mr-1.5 h-3.5 w-3.5 text-red-500" />
                      Unpair
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {pairOpen && (
        <PairDeviceModal
          onClose={() => setPairOpen(false)}
          onPaired={() => {
            setPairOpen(false);
            load();
          }}
        />
      )}
      {renameTarget && (
        <RenameDeviceModal
          device={renameTarget}
          onClose={() => setRenameTarget(null)}
          onSaved={() => {
            setRenameTarget(null);
            load();
          }}
        />
      )}
    </div>
  );
}
