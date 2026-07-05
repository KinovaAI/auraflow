"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  Loader2,
  Plug,
  Unplug,
  Settings2,
  CalendarCheck,
  Mail,
  MessageSquare,
  DollarSign,
  Link2,
  Trash2,
  Heart,
  Activity,
  CheckCircle2,
  XCircle,
  ArrowUpDown,
  RefreshCw,
  Key,
  Copy,
  Download,
  FileSpreadsheet,
  ExternalLink,
  Zap,
  GraduationCap,
  Dumbbell,
  Newspaper,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  integrationsApi,
  type ClassPassConfig,
  type ClassPassConfigUpdate,
  type ClassPassReservation,
  type EmrConnectRequest,
  type EmrStatus,
  type EmrSyncLogEntry,
} from "@/lib/integrations-api";
import { apiClient } from "@/lib/api-client";
import { communicationsApi, type CommunicationsStatus } from "@/lib/communications-api";
import { studiosApi } from "@/lib/scheduling-api";
import {
  payrollExportApi,
  type PayrollExportStatus,
  type ExternalEmployee,
  type EmployeeMapping,
} from "@/lib/payroll-export-api";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";

// ── Status Badge ────────────────────────────────────────────────────────────

const reservationStatusColors: Record<string, string> = {
  confirmed: "bg-green-50 text-green-700",
  pending: "bg-yellow-50 text-yellow-700",
  cancelled: "bg-red-50 text-red-600",
  completed: "bg-blue-50 text-blue-700",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        reservationStatusColors[status] || "bg-gray-100 text-gray-500"
      }`}
    >
      {status}
    </span>
  );
}

// ── Disconnect Confirmation Dialog ──────────────────────────────────────────

function DisconnectDialog({
  onClose,
  onConfirm,
  isPending,
}: {
  onClose: () => void;
  onConfirm: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-gray-900">
          Disconnect ClassPass
        </h2>
        <p className="mt-2 text-sm text-gray-600">
          Are you sure you want to disconnect ClassPass? This will stop all
          ClassPass reservations from being accepted. Existing reservations will
          not be affected.
        </p>
        <div className="flex justify-end gap-3 pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            className="text-red-600 hover:bg-red-50 border-red-200"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending && (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            )}
            Disconnect
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Connect Form ────────────────────────────────────────────────────────────

function ConnectForm({
  studioId,
  onConnected,
}: {
  studioId: string;
  onConnected: () => void;
}) {
  const [venueId, setVenueId] = useState("");

  const connectMutation = useMutation({
    mutationFn: () =>
      integrationsApi
        .connectClassPass(studioId, venueId)
        .then((r) => r.data.data),
    onSuccess: () => {
      onConnected();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    connectMutation.mutate();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Plug className="h-5 w-5 text-indigo-600" />
          Connect ClassPass
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="venue-id">ClassPass Venue ID</Label>
            <Input
              id="venue-id"
              type="text"
              required
              value={venueId}
              onChange={(e) => setVenueId(e.target.value)}
              placeholder="e.g. cp_venue_12345"
              className="mt-1"
            />
          </div>
          {connectMutation.isError && (
            <p className="text-sm text-red-600">
              Failed to connect ClassPass. Please check your IDs and try again.
            </p>
          )}
          <Button type="submit" disabled={connectMutation.isPending}>
            {connectMutation.isPending && (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            )}
            Connect
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Config Editor ───────────────────────────────────────────────────────────

function ConfigEditor({
  config,
  onUpdated,
}: {
  config: ClassPassConfig;
  onUpdated: () => void;
}) {
  const [creditRate, setCreditRate] = useState(config.credit_rate);
  const [maxSpots, setMaxSpots] = useState(config.max_spots_per_class);
  const [autoConfirm, setAutoConfirm] = useState(config.auto_confirm);

  const updateMutation = useMutation({
    mutationFn: (data: ClassPassConfigUpdate) =>
      integrationsApi
        .updateClassPassConfig(config.studio_id, data)
        .then((r) => r.data.data),
    onSuccess: () => {
      onUpdated();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateMutation.mutate({
      credit_rate: creditRate,
      max_spots_per_class: maxSpots,
      auto_confirm: autoConfirm,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Settings2 className="h-5 w-5 text-indigo-600" />
          ClassPass Configuration
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="credit-rate">Credit Rate</Label>
              <Input
                id="credit-rate"
                type="number"
                min={1}
                required
                value={creditRate}
                onChange={(e) => setCreditRate(Number(e.target.value))}
                className="mt-1"
              />
              <p className="mt-1 text-xs text-gray-500">
                Credits charged per reservation
              </p>
            </div>
            <div>
              <Label htmlFor="max-spots">Max Spots per Class</Label>
              <Input
                id="max-spots"
                type="number"
                min={1}
                required
                value={maxSpots}
                onChange={(e) => setMaxSpots(Number(e.target.value))}
                className="mt-1"
              />
              <p className="mt-1 text-xs text-gray-500">
                Maximum ClassPass spots available per class
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              role="switch"
              aria-checked={autoConfirm}
              onClick={() => setAutoConfirm(!autoConfirm)}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 ${
                autoConfirm ? "bg-indigo-600" : "bg-gray-200"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition-transform ${
                  autoConfirm ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
            <Label htmlFor="auto-confirm" className="cursor-pointer">
              Auto-confirm reservations
            </Label>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex-1">
              <p className="text-sm text-gray-500">
                Venue ID:{" "}
                <span className="font-mono text-gray-700">
                  {config.venue_id}
                </span>
              </p>
              <p className="text-xs text-gray-400">
                Connected{" "}
                {format(new Date(config.created_at), "MMM d, yyyy")}
                {config.updated_at &&
                  ` | Last updated ${format(
                    new Date(config.updated_at),
                    "MMM d, yyyy"
                  )}`}
              </p>
            </div>
          </div>

          {updateMutation.isError && (
            <p className="text-sm text-red-600">
              Failed to update configuration. Please try again.
            </p>
          )}
          {updateMutation.isSuccess && (
            <p className="text-sm text-green-600">
              Configuration updated successfully.
            </p>
          )}

          <Button type="submit" disabled={updateMutation.isPending}>
            {updateMutation.isPending && (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            )}
            Save Configuration
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Reservations Table ──────────────────────────────────────────────────────

function ReservationsTable({
  reservations,
  isLoading,
}: {
  reservations?: ClassPassReservation[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!reservations?.length) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
        <CalendarCheck className="mx-auto h-10 w-10 text-gray-300" />
        <p className="mt-2 text-sm text-gray-500">
          No ClassPass reservations yet
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Customer
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Email
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Status
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
              Credits
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Reservation ID
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Booked At
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {reservations.map((reservation) => (
            <tr key={reservation.id} className="hover:bg-gray-50">
              <td className="whitespace-nowrap px-4 py-3 text-sm font-medium text-gray-900">
                {reservation.customer_name}
              </td>
              <td className="px-4 py-3 text-sm text-gray-600">
                {reservation.customer_email}
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <StatusBadge status={reservation.status} />
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-right text-sm text-gray-500">
                {reservation.credits}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-sm font-mono text-gray-500">
                {reservation.classpass_reservation_id}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500">
                {format(new Date(reservation.created_at), "MMM d, h:mm a")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

// ── SendGrid Config Card ──────────────────────────────────────────────────

function SendGridCard({
  status,
  onUpdated,
}: {
  status: CommunicationsStatus;
  onUpdated: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [fromName, setFromName] = useState("");
  const [testing, setTesting] = useState(false);

  const connectMutation = useMutation({
    mutationFn: () =>
      communicationsApi.connectSendGrid({
        api_key: apiKey,
        from_email: fromEmail || undefined,
        from_name: fromName || undefined,
      }),
    onSuccess: () => {
      toast.success("SendGrid connected");
      setShowForm(false);
      setApiKey("");
      onUpdated();
    },
    onError: () => toast.error("Failed to connect SendGrid"),
  });

  const disconnectMutation = useMutation({
    mutationFn: () => communicationsApi.disconnectSendGrid(),
    onSuccess: () => {
      toast.success("SendGrid disconnected");
      onUpdated();
    },
  });

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await communicationsApi.testSendGrid({
        api_key: apiKey,
        from_email: fromEmail || undefined,
        from_name: fromName || undefined,
      });
      if (res.data.success) {
        toast.success(res.data.message);
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error("Test failed");
    }
    setTesting(false);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <div className="rounded-full bg-blue-100 p-2">
              <Mail className="h-5 w-5 text-blue-600" />
            </div>
            SendGrid
          </CardTitle>
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              status.sendgrid_connected
                ? "bg-green-50 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {status.sendgrid_connected ? "Connected" : "Not Connected"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-gray-600">
          Send transactional emails, booking confirmations, and marketing
          campaigns via SendGrid.
        </p>

        {status.sendgrid_connected && (
          <div className="flex items-center justify-between rounded-md bg-gray-50 p-3 text-sm">
            <div>
              <p className="text-gray-700">
                From: {status.sendgrid_from_name} &lt;{status.sendgrid_from_email}&gt;
              </p>
              {status.sendgrid_connected_at && (
                <p className="text-xs text-gray-400">
                  Connected {new Date(status.sendgrid_connected_at).toLocaleDateString()}
                </p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-red-600"
              onClick={() => {
                if (confirm("Disconnect SendGrid?")) disconnectMutation.mutate();
              }}
            >
              Disconnect
            </Button>
          </div>
        )}

        {!status.sendgrid_connected && !showForm && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            <Plug className="mr-1 h-4 w-4" />
            Connect SendGrid
          </Button>
        )}

        {showForm && (
          <div className="space-y-3 rounded-md border border-gray-200 p-4">
            <div>
              <Label>API Key</Label>
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="SG.xxxxxx..."
                className="mt-1"
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <Label>From Email (optional)</Label>
                <Input
                  value={fromEmail}
                  onChange={(e) => setFromEmail(e.target.value)}
                  placeholder="hello@yourstudio.com"
                  className="mt-1"
                />
              </div>
              <div>
                <Label>From Name (optional)</Label>
                <Input
                  value={fromName}
                  onChange={(e) => setFromName(e.target.value)}
                  placeholder="Your Studio Name"
                  className="mt-1"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTest}
                disabled={!apiKey || testing}
              >
                {testing && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Test Connection
              </Button>
              <Button
                size="sm"
                onClick={() => connectMutation.mutate()}
                disabled={!apiKey || connectMutation.isPending}
              >
                {connectMutation.isPending && (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                )}
                Connect
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Twilio Config Card ────────────────────────────────────────────────────

function TwilioCard({
  status,
  onUpdated,
}: {
  status: CommunicationsStatus;
  onUpdated: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [accountSid, setAccountSid] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [testing, setTesting] = useState(false);

  const connectMutation = useMutation({
    mutationFn: () =>
      communicationsApi.connectTwilio({
        account_sid: accountSid,
        auth_token: authToken,
        phone_number: phoneNumber,
      }),
    onSuccess: () => {
      toast.success("Twilio connected");
      setShowForm(false);
      setAccountSid("");
      setAuthToken("");
      setPhoneNumber("");
      onUpdated();
    },
    onError: () => toast.error("Failed to connect Twilio"),
  });

  const disconnectMutation = useMutation({
    mutationFn: () => communicationsApi.disconnectTwilio(),
    onSuccess: () => {
      toast.success("Twilio disconnected");
      onUpdated();
    },
  });

  const handleTest = async () => {
    setTesting(true);
    try {
      const res = await communicationsApi.testTwilio({
        account_sid: accountSid,
        auth_token: authToken,
        phone_number: phoneNumber,
      });
      if (res.data.success) {
        toast.success(res.data.message);
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error("Test failed");
    }
    setTesting(false);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <div className="rounded-full bg-purple-100 p-2">
              <MessageSquare className="h-5 w-5 text-purple-600" />
            </div>
            Twilio
          </CardTitle>
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              status.twilio_connected
                ? "bg-green-50 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {status.twilio_connected ? "Connected" : "Not Connected"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-gray-600">
          Send SMS booking confirmations, class reminders, and marketing
          messages via Twilio.
        </p>

        {status.twilio_connected && (
          <div className="flex items-center justify-between rounded-md bg-gray-50 p-3 text-sm">
            <div>
              <p className="text-gray-700">
                Phone: {status.twilio_phone_number}
              </p>
              {status.twilio_connected_at && (
                <p className="text-xs text-gray-400">
                  Connected {new Date(status.twilio_connected_at).toLocaleDateString()}
                </p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-red-600"
              onClick={() => {
                if (confirm("Disconnect Twilio?")) disconnectMutation.mutate();
              }}
            >
              Disconnect
            </Button>
          </div>
        )}

        {!status.twilio_connected && !showForm && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            <Plug className="mr-1 h-4 w-4" />
            Connect Twilio
          </Button>
        )}

        {showForm && (
          <div className="space-y-3 rounded-md border border-gray-200 p-4">
            <div>
              <Label>Account SID</Label>
              <Input
                value={accountSid}
                onChange={(e) => setAccountSid(e.target.value)}
                placeholder="ACxxxxxxxx..."
                className="mt-1"
              />
            </div>
            <div>
              <Label>Auth Token</Label>
              <Input
                type="password"
                value={authToken}
                onChange={(e) => setAuthToken(e.target.value)}
                placeholder="Your auth token"
                className="mt-1"
              />
            </div>
            <div>
              <Label>Phone Number</Label>
              <Input
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                placeholder="+15551234567"
                className="mt-1"
              />
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleTest}
                disabled={!accountSid || !authToken || !phoneNumber || testing}
              >
                {testing && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Test Connection
              </Button>
              <Button
                size="sm"
                onClick={() => connectMutation.mutate()}
                disabled={!accountSid || !authToken || !phoneNumber || connectMutation.isPending}
              >
                {connectMutation.isPending && (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                )}
                Connect
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function IntegrationsPage() {
  const queryClient = useQueryClient();
  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);
  const [studioId, setStudioId] = useState<string | null>(null);

  // Fetch studios to get the first one
  const { data: studios } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  useEffect(() => {
    if (studios && studios.length > 0 && !studioId) {
      setStudioId(studios[0].id);
    }
  }, [studios, studioId]);

  // ── Queries ─────────────────────────────────────────────────────────────

  // We try to fetch the config; a 404 means not connected
  const {
    data: config,
    isLoading: configLoading,
    error: configError,
  } = useQuery({
    queryKey: ["classpass-config", studioId],
    queryFn: () =>
      integrationsApi
        .getClassPassConfig(studioId!)
        .then((r) => r.data.data),
    enabled: !!studioId,
    retry: (failureCount, error: unknown) => {
      // Don't retry on 404 (not connected)
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404) return false;
      return failureCount < 2;
    },
  });

  const isConnected = !!config && !configError;

  const { data: reservations, isLoading: reservationsLoading } = useQuery({
    queryKey: ["classpass-reservations"],
    queryFn: () =>
      integrationsApi
        .listClassPassReservations({ limit: 50 })
        .then((r) => r.data.data),
    enabled: isConnected,
  });

  // ── Mutations ───────────────────────────────────────────────────────────

  const disconnectMutation = useMutation({
    mutationFn: () =>
      integrationsApi
        .disconnectClassPass(config!.studio_id)
        .then((r) => r.data.data),
    onSuccess: () => {
      setShowDisconnectDialog(false);
      queryClient.invalidateQueries({ queryKey: ["classpass-config"] });
      queryClient.invalidateQueries({ queryKey: ["classpass-reservations"] });
    },
  });

  const handleInvalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["classpass-config"] });
    queryClient.invalidateQueries({ queryKey: ["classpass-reservations"] });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Integrations</h1>
        <p className="text-sm text-gray-500">
          Connect third-party platforms to your studio
        </p>
      </div>

      {/* ClassPass Integration Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <div className="rounded-full bg-indigo-100 p-2">
                <Plug className="h-5 w-5 text-indigo-600" />
              </div>
              ClassPass
            </CardTitle>
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                isConnected
                  ? "bg-green-50 text-green-700"
                  : "bg-gray-100 text-gray-500"
              }`}
            >
              {configLoading
                ? "Checking..."
                : isConnected
                  ? "Connected"
                  : "Not Connected"}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600">
            Accept ClassPass reservations for your classes. ClassPass members
            can discover and book your studio through the ClassPass app and
            website.
          </p>
          {isConnected && (
            <div className="mt-4">
              <Button
                variant="outline"
                size="sm"
                className="text-red-600 hover:bg-red-50 hover:text-red-700"
                onClick={() => setShowDisconnectDialog(true)}
              >
                <Unplug className="mr-1 h-4 w-4" />
                Disconnect
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Loading State */}
      {(configLoading || !studioId) && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        </div>
      )}

      {/* Connect Form (not connected) */}
      {!configLoading && !isConnected && studioId && (
        <ConnectForm studioId={studioId} onConnected={handleInvalidate} />
      )}

      {/* Config Editor (connected) */}
      {!configLoading && isConnected && config && (
        <ConfigEditor config={config} onUpdated={handleInvalidate} />
      )}

      {/* Reservations */}
      {isConnected && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Recent Reservations
            </h2>
            {reservations && reservations.length > 0 && (
              <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
                {reservations.length}
              </span>
            )}
          </div>
          <ReservationsTable
            reservations={reservations}
            isLoading={reservationsLoading}
          />
        </div>
      )}

      {/* ── Communications (SendGrid + Twilio) ──────────────────────── */}
      <CommunicationsSection />

      {/* ── Payroll Integrations ──────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">
          Payroll Integrations
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <GustoPayrollCard />
          <QuickBooksPayrollCard />
        </div>
      </div>

      {/* ── EMR Integration ──────────────────────────────────────────── */}
      <EmrIntegrationCard />

      {/* ── Mailchimp ──────────────────────────────────────────────────── */}
      <MailchimpCard />

      {/* ── API Integrations ───────────────────────────────────────────── */}
      <ApiIntegrationsSection />

      {/* ── Data Export ────────────────────────────────────────────────── */}
      <DataExportSection />

      {/* Disconnect Confirmation Dialog */}
      {showDisconnectDialog && (
        <DisconnectDialog
          onClose={() => setShowDisconnectDialog(false)}
          onConfirm={() => disconnectMutation.mutate()}
          isPending={disconnectMutation.isPending}
        />
      )}
    </div>
  );
}

// ── Gusto Payroll Card ──────────────────────────────────────────────────────

function GustoPayrollCard() {
  const queryClient = useQueryClient();
  const [showMapping, setShowMapping] = useState(false);

  const { data: status, isLoading } = useQuery({
    queryKey: ["payroll-export-status"],
    queryFn: () => payrollExportApi.getStatus().then((r) => r.data.data),
  });

  const gustoStatus = status?.gusto;
  const isConnected = gustoStatus?.connected === true;

  const handleConnect = async () => {
    try {
      const resp = await payrollExportApi.gustoAuthorize();
      window.location.href = resp.data.data.authorize_url;
    } catch {
      toast.error("Failed to start Gusto connection");
    }
  };

  const disconnectMut = useMutation({
    mutationFn: () => payrollExportApi.gustoDisconnect(),
    onSuccess: () => {
      toast.success("Gusto disconnected");
      queryClient.invalidateQueries({ queryKey: ["payroll-export-status"] });
    },
    onError: () => toast.error("Failed to disconnect Gusto"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-emerald-600" />
            Gusto Payroll
          </span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              isConnected
                ? "bg-green-50 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {isConnected ? "Connected" : "Not Connected"}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
          </div>
        ) : isConnected ? (
          <>
            <div className="text-sm text-gray-500">
              Company ID: <span className="font-mono text-gray-700">{gustoStatus?.company_id}</span>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowMapping(!showMapping)}
              >
                <Link2 className="mr-1 h-3.5 w-3.5" />
                Employee Mapping
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-red-600 hover:bg-red-50"
                onClick={() => disconnectMut.mutate()}
                disabled={disconnectMut.isPending}
              >
                <Unplug className="mr-1 h-3.5 w-3.5" />
                Disconnect
              </Button>
            </div>
            {showMapping && <EmployeeMappingTable provider="gusto" />}
          </>
        ) : (
          <>
            <p className="text-sm text-gray-500">
              Connect your Gusto account to push payroll data directly.
            </p>
            <Button size="sm" onClick={handleConnect}>
              <Plug className="mr-1 h-3.5 w-3.5" />
              Connect Gusto
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── QuickBooks Payroll Card ─────────────────────────────────────────────────

function QuickBooksPayrollCard() {
  const queryClient = useQueryClient();
  const [showMapping, setShowMapping] = useState(false);

  const { data: status, isLoading } = useQuery({
    queryKey: ["payroll-export-status"],
    queryFn: () => payrollExportApi.getStatus().then((r) => r.data.data),
  });

  const qbStatus = status?.quickbooks;
  const isConnected = qbStatus?.connected === true;

  const handleConnect = async () => {
    try {
      const resp = await payrollExportApi.qbAuthorize();
      window.location.href = resp.data.data.authorize_url;
    } catch {
      toast.error("Failed to start QuickBooks connection");
    }
  };

  const disconnectMut = useMutation({
    mutationFn: () => payrollExportApi.qbDisconnect(),
    onSuccess: () => {
      toast.success("QuickBooks disconnected");
      queryClient.invalidateQueries({ queryKey: ["payroll-export-status"] });
    },
    onError: () => toast.error("Failed to disconnect QuickBooks"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-green-600" />
            QuickBooks Payroll
          </span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              isConnected
                ? "bg-green-50 text-green-700"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {isConnected ? "Connected" : "Not Connected"}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
          </div>
        ) : isConnected ? (
          <>
            <div className="text-sm text-gray-500">
              Realm ID: <span className="font-mono text-gray-700">{qbStatus?.realm_id}</span>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowMapping(!showMapping)}
              >
                <Link2 className="mr-1 h-3.5 w-3.5" />
                Employee Mapping
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-red-600 hover:bg-red-50"
                onClick={() => disconnectMut.mutate()}
                disabled={disconnectMut.isPending}
              >
                <Unplug className="mr-1 h-3.5 w-3.5" />
                Disconnect
              </Button>
            </div>
            {showMapping && <EmployeeMappingTable provider="quickbooks" />}
          </>
        ) : (
          <>
            <p className="text-sm text-gray-500">
              Connect your QuickBooks account to push time activities directly.
            </p>
            <Button size="sm" onClick={handleConnect}>
              <Plug className="mr-1 h-3.5 w-3.5" />
              Connect QuickBooks
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Employee Mapping Table ──────────────────────────────────────────────────

function EmployeeMappingTable({ provider }: { provider: string }) {
  const queryClient = useQueryClient();
  const [selectedInstructor, setSelectedInstructor] = useState("");
  const [selectedEmployee, setSelectedEmployee] = useState("");

  const { data: instructors } = useQuery({
    queryKey: ["instructors"],
    queryFn: () => instructorsApi.list().then((r) => r.data),
  });

  const { data: mappings, isLoading: mappingsLoading } = useQuery({
    queryKey: ["payroll-mappings", provider],
    queryFn: () =>
      payrollExportApi.listMappings(provider).then((r) => r.data.data),
  });

  const { data: employees, isLoading: employeesLoading } = useQuery({
    queryKey: ["payroll-employees", provider],
    queryFn: () => {
      if (provider === "gusto") {
        return payrollExportApi.gustoEmployees().then((r) => r.data.data);
      }
      return payrollExportApi.qbEmployees().then((r) => r.data.data);
    },
  });

  const createMut = useMutation({
    mutationFn: () => {
      const emp = employees?.find((e) => e.id === selectedEmployee);
      return payrollExportApi.createMapping(provider, {
        instructor_id: selectedInstructor,
        external_employee_id: selectedEmployee,
        external_employee_name: emp
          ? `${emp.first_name} ${emp.last_name}`
          : undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["payroll-mappings", provider],
      });
      setSelectedInstructor("");
      setSelectedEmployee("");
      toast.success("Mapping saved");
    },
    onError: () => toast.error("Failed to save mapping"),
  });

  const deleteMut = useMutation({
    mutationFn: (instructorId: string) =>
      payrollExportApi.deleteMapping(provider, instructorId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["payroll-mappings", provider],
      });
      toast.success("Mapping removed");
    },
  });

  const mappedInstructorIds = new Set(mappings?.map((m) => m.instructor_id));
  const unmappedInstructors = (instructors || []).filter(
    (i) => !mappedInstructorIds.has(i.id)
  );

  if (mappingsLoading || employeesLoading) {
    return (
      <div className="flex justify-center py-4">
        <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-md border border-gray-200 p-3">
      <h4 className="text-sm font-medium text-gray-700">Employee Mapping</h4>

      {/* Existing Mappings */}
      {mappings && mappings.length > 0 && (
        <div className="space-y-2">
          {mappings.map((m) => (
            <div
              key={m.id}
              className="flex items-center justify-between rounded bg-gray-50 px-3 py-2 text-sm"
            >
              <div>
                <span className="font-medium text-gray-900">
                  {m.instructor_name}
                </span>
                <span className="mx-2 text-gray-400">→</span>
                <span className="text-gray-600">
                  {m.external_employee_name || m.external_employee_id}
                </span>
              </div>
              <button
                onClick={() => deleteMut.mutate(m.instructor_id)}
                className="rounded p-1 text-red-400 hover:bg-red-50 hover:text-red-600"
                title="Remove mapping"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add New Mapping */}
      {unmappedInstructors.length > 0 && employees && employees.length > 0 && (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-gray-500">
              Instructor
            </label>
            <select
              value={selectedInstructor}
              onChange={(e) => setSelectedInstructor(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
            >
              <option value="">Select...</option>
              {unmappedInstructors.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-gray-500">
              {provider === "gusto" ? "Gusto" : "QB"} Employee
            </label>
            <select
              value={selectedEmployee}
              onChange={(e) => setSelectedEmployee(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm"
            >
              <option value="">Select...</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.first_name} {e.last_name}
                </option>
              ))}
            </select>
          </div>
          <Button
            size="sm"
            disabled={
              !selectedInstructor ||
              !selectedEmployee ||
              createMut.isPending
            }
            onClick={() => createMut.mutate()}
          >
            {createMut.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              "Map"
            )}
          </Button>
        </div>
      )}

      {employees && employees.length === 0 && (
        <p className="text-xs text-gray-400">
          No employees found in {provider === "gusto" ? "Gusto" : "QuickBooks"}.
        </p>
      )}
    </div>
  );
}

// ── EMR Integration Card ──────────────────────────────────────────────────

function EmrIntegrationCard() {
  const queryClient = useQueryClient();
  const [showConnect, setShowConnect] = useState(false);
  const [showSyncLog, setShowSyncLog] = useState(false);
  const [protocol, setProtocol] = useState<"fhir_r4" | "hl7v2">("fhir_r4");
  const [fhirUrl, setFhirUrl] = useState("");
  const [fhirClientId, setFhirClientId] = useState("");
  const [fhirClientSecret, setFhirClientSecret] = useState("");
  const [hl7Host, setHl7Host] = useState("");
  const [hl7Port, setHl7Port] = useState("2575");

  const { data: statusData, isLoading } = useQuery({
    queryKey: ["emr-status"],
    queryFn: () => integrationsApi.emrStatus().then((r) => r.data.data),
  });

  const { data: syncLog } = useQuery({
    queryKey: ["emr-sync-log"],
    queryFn: () =>
      integrationsApi.emrSyncLog({ limit: 20 }).then((r) => r.data.data),
    enabled: showSyncLog && !!statusData?.connected,
  });

  const connectMut = useMutation({
    mutationFn: (data: EmrConnectRequest) => integrationsApi.emrConnect(data),
    onSuccess: () => {
      toast.success("EMR connected successfully");
      queryClient.invalidateQueries({ queryKey: ["emr-status"] });
      setShowConnect(false);
    },
    onError: (e: any) => {
      toast.error(
        e?.response?.data?.detail || "Failed to connect. Check credentials."
      );
    },
  });

  const disconnectMut = useMutation({
    mutationFn: () => integrationsApi.emrDisconnect(),
    onSuccess: () => {
      toast.success("EMR disconnected");
      queryClient.invalidateQueries({ queryKey: ["emr-status"] });
    },
  });

  const testMut = useMutation({
    mutationFn: () => integrationsApi.emrTest(),
    onSuccess: (res) => {
      const d = res.data.data;
      if (d.success) toast.success("Connection OK");
      else toast.error(`Connection failed: ${d.message}`);
    },
  });

  const handleConnect = () => {
    if (protocol === "fhir_r4") {
      if (!fhirUrl || !fhirClientId || !fhirClientSecret) {
        toast.error("Please fill in all FHIR fields");
        return;
      }
      connectMut.mutate({
        protocol: "fhir_r4",
        base_url: fhirUrl,
        client_id: fhirClientId,
        client_secret: fhirClientSecret,
      });
    } else {
      if (!hl7Host || !hl7Port) {
        toast.error("Please fill in host and port");
        return;
      }
      connectMut.mutate({
        protocol: "hl7v2",
        host: hl7Host,
        port: parseInt(hl7Port),
      });
    }
  };

  const isConnected = statusData?.connected ?? false;

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-gray-900">
        EMR Integration
      </h2>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <div className="rounded-full bg-emerald-100 p-2">
                <Heart className="h-5 w-5 text-emerald-600" />
              </div>
              Electronic Medical Records
            </CardTitle>
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                isConnected
                  ? "bg-green-50 text-green-700"
                  : "bg-gray-100 text-gray-500"
              }`}
            >
              {isLoading
                ? "Checking..."
                : isConnected
                  ? `Connected (${statusData?.protocol === "fhir_r4" ? "FHIR R4" : "HL7v2"})`
                  : "Not Connected"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600">
            Sync members and class attendance with your EMR system. Supports{" "}
            <strong>FHIR R4</strong> (e.g., OpenEMR, Epic, Cerner) and{" "}
            <strong>HL7v2</strong> for legacy systems. New members automatically
            create patients in the EMR, and class check-ins appear as encounters.
          </p>

          {/* Connected state */}
          {isConnected && statusData && (
            <div className="space-y-3">
              <div className="rounded-lg bg-emerald-50 p-4">
                <div className="grid gap-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Protocol</span>
                    <span className="font-medium">
                      {statusData.protocol === "fhir_r4" ? "FHIR R4" : "HL7v2"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Endpoint</span>
                    <span className="font-mono text-xs">{statusData.endpoint}</span>
                  </div>
                  {statusData.connected_at && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Connected</span>
                      <span>{format(new Date(statusData.connected_at), "MMM d, yyyy")}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-600">Auto-sync</span>
                    <span className={statusData.sync_enabled ? "text-green-600" : "text-gray-400"}>
                      {statusData.sync_enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => testMut.mutate()}
                  disabled={testMut.isPending}
                >
                  {testMut.isPending ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Activity className="mr-1 h-3.5 w-3.5" />
                  )}
                  Test Connection
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowSyncLog(!showSyncLog)}
                >
                  <ArrowUpDown className="mr-1 h-3.5 w-3.5" />
                  {showSyncLog ? "Hide" : "Sync Log"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:bg-red-50 hover:text-red-700"
                  onClick={() => disconnectMut.mutate()}
                  disabled={disconnectMut.isPending}
                >
                  <Unplug className="mr-1 h-3.5 w-3.5" />
                  Disconnect
                </Button>
              </div>

              {/* Sync Log */}
              {showSyncLog && (
                <div className="rounded-lg border border-gray-200">
                  <div className="border-b bg-gray-50 px-4 py-2">
                    <h3 className="text-sm font-medium text-gray-700">
                      Recent Sync Activity
                    </h3>
                  </div>
                  {!syncLog || syncLog.length === 0 ? (
                    <p className="px-4 py-6 text-center text-sm text-gray-400">
                      No sync activity yet
                    </p>
                  ) : (
                    <div className="divide-y divide-gray-100">
                      {syncLog.map((entry: EmrSyncLogEntry) => (
                        <div
                          key={entry.id}
                          className="flex items-center justify-between px-4 py-2 text-xs"
                        >
                          <div className="flex items-center gap-2">
                            {entry.status === "success" ? (
                              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                            ) : (
                              <XCircle className="h-3.5 w-3.5 text-red-500" />
                            )}
                            <span className="font-medium">
                              {entry.direction === "outbound" ? "→" : "←"}{" "}
                              {entry.resource_type}
                            </span>
                            <span className="text-gray-400">
                              {entry.operation}
                            </span>
                          </div>
                          <div className="flex items-center gap-3">
                            {entry.error_message && (
                              <span className="max-w-[200px] truncate text-red-500">
                                {entry.error_message}
                              </span>
                            )}
                            <span className="text-gray-400">
                              {format(
                                new Date(entry.created_at),
                                "MMM d, h:mm a"
                              )}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Not connected — show connect button or form */}
          {!isConnected && !isLoading && (
            <>
              {!showConnect ? (
                <Button onClick={() => setShowConnect(true)}>
                  <Plug className="mr-2 h-4 w-4" />
                  Connect EMR System
                </Button>
              ) : (
                <div className="space-y-4 rounded-lg border border-gray-200 p-4">
                  <div>
                    <Label>Protocol</Label>
                    <select
                      className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                      value={protocol}
                      onChange={(e) =>
                        setProtocol(e.target.value as "fhir_r4" | "hl7v2")
                      }
                    >
                      <option value="fhir_r4">
                        FHIR R4 (OpenEMR, Epic, Cerner, etc.)
                      </option>
                      <option value="hl7v2">HL7v2 (Legacy MLLP)</option>
                    </select>
                  </div>

                  {protocol === "fhir_r4" ? (
                    <>
                      <div>
                        <Label htmlFor="fhir-url">FHIR Base URL</Label>
                        <Input
                          id="fhir-url"
                          placeholder="https://your-emr.com/fhir/r4"
                          value={fhirUrl}
                          onChange={(e) => setFhirUrl(e.target.value)}
                        />
                      </div>
                      <div>
                        <Label htmlFor="fhir-client-id">Client ID</Label>
                        <Input
                          id="fhir-client-id"
                          placeholder="OAuth2 Client ID"
                          value={fhirClientId}
                          onChange={(e) => setFhirClientId(e.target.value)}
                        />
                      </div>
                      <div>
                        <Label htmlFor="fhir-client-secret">
                          Client Secret
                        </Label>
                        <Input
                          id="fhir-client-secret"
                          type="password"
                          placeholder="OAuth2 Client Secret"
                          value={fhirClientSecret}
                          onChange={(e) => setFhirClientSecret(e.target.value)}
                        />
                      </div>
                    </>
                  ) : (
                    <>
                      <div>
                        <Label htmlFor="hl7-host">HL7 MLLP Host</Label>
                        <Input
                          id="hl7-host"
                          placeholder="emr.yourhospital.com"
                          value={hl7Host}
                          onChange={(e) => setHl7Host(e.target.value)}
                        />
                      </div>
                      <div>
                        <Label htmlFor="hl7-port">HL7 MLLP Port</Label>
                        <Input
                          id="hl7-port"
                          placeholder="2575"
                          value={hl7Port}
                          onChange={(e) => setHl7Port(e.target.value)}
                        />
                      </div>
                    </>
                  )}

                  <div className="flex gap-2">
                    <Button
                      onClick={handleConnect}
                      disabled={connectMut.isPending}
                    >
                      {connectMut.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Plug className="mr-2 h-4 w-4" />
                      )}
                      Connect
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setShowConnect(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Mailchimp Card ────────────────────────────────────────────────────────

function MailchimpCard() {
  const queryClient = useQueryClient();
  const [showConnect, setShowConnect] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [listId, setListId] = useState("");

  const { data: status, isLoading } = useQuery({
    queryKey: ["mailchimp-status"],
    queryFn: () => integrationsApi.emrStatus().then(() => null).catch(() => null),
  });

  // Use fetch directly since mailchimp endpoints use JWT auth
  const [mcStatus, setMcStatus] = useState<{ connected: boolean; list_name?: string; member_count?: number } | null>(null);

  useEffect(() => {
    apiClient.get("/external/mailchimp/status")
      .then((r) => setMcStatus((r as any).data?.data || (r as any).data))
      .catch(() => {});
  }, []);

  const handleConnect = async () => {
    if (!apiKey || !listId) { toast.error("API key and List ID are required"); return; }
    try {
      await apiClient.post("/external/mailchimp/connect", { api_key: apiKey, list_id: listId });
      toast.success("Mailchimp connected!");
      setShowConnect(false);
      setMcStatus({ connected: true });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to connect");
    }
  };

  const handleSyncAll = async () => {
    try {
      await apiClient.post("/external/mailchimp/sync-all");
      toast.success("Sync started — members will be added to your list");
    } catch { toast.error("Sync failed"); }
  };

  const handleDisconnect = async () => {
    try {
      await apiClient.post("/external/mailchimp/disconnect");
      toast.success("Mailchimp disconnected");
      setMcStatus(null);
    } catch { toast.error("Disconnect failed"); }
  };

  const isConnected = mcStatus?.connected ?? false;

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-gray-900">Email Marketing</h2>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <div className="rounded-full bg-yellow-100 p-2">
                <Newspaper className="h-5 w-5 text-yellow-600" />
              </div>
              Mailchimp
            </CardTitle>
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${isConnected ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}>
              {isConnected ? "Connected" : "Not Connected"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600">
            Automatically add new members to your Mailchimp mailing list. Every member created in AuraFlow — whether through the dashboard, API, or integrations — syncs to your newsletter list.
          </p>

          {isConnected ? (
            <div className="space-y-3">
              {mcStatus?.list_name && (
                <div className="rounded-lg bg-yellow-50 p-3 text-sm">
                  <span className="text-gray-600">List: </span>
                  <strong>{mcStatus.list_name}</strong>
                  {mcStatus.member_count != null && (
                    <span className="ml-2 text-gray-500">({mcStatus.member_count} subscribers)</span>
                  )}
                </div>
              )}
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleSyncAll}>
                  <RefreshCw className="mr-1 h-3.5 w-3.5" />
                  Sync All Members
                </Button>
                <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50" onClick={handleDisconnect}>
                  <Unplug className="mr-1 h-3.5 w-3.5" />
                  Disconnect
                </Button>
              </div>
            </div>
          ) : !showConnect ? (
            <Button onClick={() => setShowConnect(true)}>
              <Plug className="mr-2 h-4 w-4" />
              Connect Mailchimp
            </Button>
          ) : (
            <div className="space-y-3 rounded-lg border border-gray-200 p-4">
              <div>
                <Label htmlFor="mc-key">Mailchimp API Key</Label>
                <Input id="mc-key" type="password" placeholder="xxxxxxxx-us21" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
                <p className="mt-1 text-xs text-gray-400">Found in Mailchimp → Account → Extras → API keys</p>
              </div>
              <div>
                <Label htmlFor="mc-list">Audience/List ID</Label>
                <Input id="mc-list" placeholder="a1b2c3d4e5" value={listId} onChange={(e) => setListId(e.target.value)} />
                <p className="mt-1 text-xs text-gray-400">Found in Mailchimp → Audience → Settings → Audience ID</p>
              </div>
              <div className="flex gap-2">
                <Button onClick={handleConnect}><Plug className="mr-2 h-4 w-4" />Connect</Button>
                <Button variant="outline" onClick={() => setShowConnect(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── API Integrations Section ──────────────────────────────────────────────

const AVAILABLE_SCOPES = [
  { id: "*:*", label: "Full Access", desc: "Read and write all data" },
  { id: "scheduling:read", label: "Schedule (Read)", desc: "View classes and sessions" },
  { id: "bookings:read", label: "Bookings (Read)", desc: "View bookings" },
  { id: "bookings:write", label: "Bookings (Write)", desc: "Create and cancel bookings" },
  { id: "members:read", label: "Members (Read)", desc: "View member profiles" },
  { id: "members:write", label: "Members (Write)", desc: "Create and update members" },
  { id: "memberships:read", label: "Memberships (Read)", desc: "View membership plans" },
  { id: "memberships:write", label: "Memberships (Write)", desc: "Assign memberships" },
  { id: "instructors:read", label: "Instructors (Read)", desc: "View instructor profiles" },
  { id: "payments:read", label: "Payments (Read)", desc: "View transactions" },
  { id: "payments:write", label: "Payments (Write)", desc: "Process payments" },
  { id: "courses:read", label: "Courses (Read)", desc: "View workshops and trainings" },
  { id: "courses:write", label: "Courses (Write)", desc: "Manage courses" },
  { id: "private_sessions:read", label: "Private Sessions (Read)", desc: "View private bookings" },
  { id: "private_sessions:write", label: "Private Sessions (Write)", desc: "Book private sessions" },
];

function ApiIntegrationsSection() {
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<string[]>(["*:*"]);
  const [newKey, setNewKey] = useState("");
  const [keys, setKeys] = useState<Array<{ id: string; name: string; key_prefix: string; scopes: string[]; last_used_at: string | null; created_at: string }>>([]);

  const loadKeys = async () => {
    try {
      const resp = await apiClient.get("/external/api-keys");
      setKeys(resp.data.data || []);
    } catch {}
  };

  useEffect(() => { loadKeys(); }, []);

  const createKey = async () => {
    if (!keyName) { toast.error("Enter a name for the API key"); return; }
    try {
      const resp = await apiClient.post("/external/api-keys", { name: keyName, scopes: selectedScopes });
      setNewKey(resp.data.data.raw_key);
      setKeyName("");
      loadKeys();
      toast.success("API key created — copy it now, it won't be shown again!");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to create key");
    }
  };

  const revokeKey = async (keyId: string) => {
    if (!confirm("Revoke this API key? Integrations using it will stop working.")) return;
    try {
      await apiClient.delete(`/external/api-keys/${keyId}`);
      toast.success("Key revoked");
      loadKeys();
    } catch { toast.error("Failed to revoke key"); }
  };

  const integrations = [
    { name: "BioAlignPro Edge", icon: Dumbbell, color: "bg-blue-100 text-blue-600", desc: "Clinical assessment and FMS screening. Creates members and private sessions in AuraFlow for billing." },
    { name: "MyYogi.ai", icon: Zap, color: "bg-purple-100 text-purple-600", desc: "Personalized at-home yoga training. AI-guided pose perfection, breathing and meditation techniques, and assistance on the yogic path." },
    { name: "MyYogi Academy", icon: GraduationCap, color: "bg-orange-100 text-orange-600", desc: "Digital teacher training platform. Manage homework, quizzes, video classes, and course content online." },
  ];

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-gray-900">API Integrations</h2>
      <p className="mb-4 text-sm text-gray-500">
        Connect external applications using API keys. Control access with granular scopes.{" "}
        <a href="/docs/api-reference.html" target="_blank" className="text-indigo-600 hover:underline">
          View API documentation <ExternalLink className="inline h-3 w-3" />
        </a>
      </p>

      {/* Integration cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        {integrations.map((int) => (
          <Card key={int.name}>
            <CardContent className="pt-6">
              <div className="mb-3 flex items-center gap-2">
                <div className={`rounded-full p-2 ${int.color}`}>
                  <int.icon className="h-4 w-4" />
                </div>
                <span className="font-semibold text-gray-900">{int.name}</span>
              </div>
              <p className="text-xs text-gray-500">{int.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Key className="h-4 w-4 text-gray-500" />
              API Keys
            </CardTitle>
            <Button size="sm" onClick={() => setShowKeyForm(!showKeyForm)}>
              {showKeyForm ? "Cancel" : "+ Create Key"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* New key form */}
          {showKeyForm && (
            <div className="space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
              <Input placeholder="Key name (e.g., ClassPass, BioAlignPro)" value={keyName} onChange={(e) => setKeyName(e.target.value)} />
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700">Scopes</label>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {AVAILABLE_SCOPES.map((scope) => {
                    const isFullAccess = scope.id === "*:*";
                    const isChecked = selectedScopes.includes(scope.id);
                    const isDisabledByFull = !isFullAccess && selectedScopes.includes("*:*");
                    return (
                      <label key={scope.id} className={`flex items-start gap-2 rounded border px-3 py-2 text-sm cursor-pointer ${isChecked ? "border-indigo-300 bg-indigo-50" : "border-gray-200 bg-white"} ${isDisabledByFull ? "opacity-50" : ""}`}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          disabled={isDisabledByFull}
                          onChange={(e) => {
                            if (isFullAccess) {
                              setSelectedScopes(e.target.checked ? ["*:*"] : []);
                            } else {
                              const without = selectedScopes.filter((s) => s !== "*:*" && s !== scope.id);
                              setSelectedScopes(e.target.checked ? [...without, scope.id] : without);
                            }
                          }}
                          className="mt-0.5 h-4 w-4 rounded border-gray-300 text-indigo-600"
                        />
                        <div>
                          <div className="font-medium text-gray-900">{scope.label}</div>
                          <div className="text-xs text-gray-500">{scope.desc}</div>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="flex justify-end">
                <Button onClick={createKey} disabled={!keyName || selectedScopes.length === 0}>Create API Key</Button>
              </div>
            </div>
          )}

          {/* Show new key once */}
          {newKey && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
              <p className="mb-2 text-sm font-medium text-green-800">New API Key — copy it now, it won&apos;t be shown again!</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded bg-white px-3 py-2 font-mono text-xs text-gray-800">{newKey}</code>
                <Button size="sm" variant="outline" onClick={() => { navigator.clipboard.writeText(newKey); toast.success("Copied!"); }}>
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
              <Button size="sm" variant="outline" className="mt-2" onClick={() => setNewKey("")}>Dismiss</Button>
            </div>
          )}

          {/* Existing keys */}
          {keys.length === 0 ? (
            <p className="text-sm text-gray-400">No API keys yet. Create one to connect BioAlignPro, MyYogi, or other applications.</p>
          ) : (
            <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
              {keys.map((k) => (
                <div key={k.id} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{k.name}</p>
                    <p className="text-xs text-gray-400">
                      <code>{k.key_prefix}...</code>
                      {k.last_used_at && ` · Last used ${format(new Date(k.last_used_at), "MMM d, h:mm a")}`}
                      {` · Created ${format(new Date(k.created_at), "MMM d, yyyy")}`}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {k.scopes.map((s) => (
                        <span key={s} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{s}</span>
                      ))}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" className="text-red-600 hover:bg-red-50" onClick={() => revokeKey(k.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Data Export Section ────────────────────────────────────────────────────

function DataExportSection() {
  const exports = [
    { label: "Members", path: "/external/members/export.csv", icon: "👥" },
    { label: "Bookings", path: "/external/bookings/export.csv", icon: "📅" },
    { label: "Sessions", path: "/external/sessions/export.csv", icon: "🗓️" },
    { label: "Memberships", path: "/external/memberships/export.csv", icon: "💳" },
    { label: "Instructors", path: "/external/instructors/export.csv", icon: "🧘" },
    { label: "Private Sessions", path: "/external/private-sessions/export.csv", icon: "🤝" },
    { label: "Courses", path: "/external/courses/export.csv", icon: "🎓" },
    { label: "Transactions", path: "/external/transactions/export.csv", icon: "💰" },
    { label: "Products", path: "/external/products/export.csv", icon: "🛍️" },
  ];

  const handleExport = async (path: string, label: string) => {
    try {
      const resp = await apiClient.get(path, { responseType: "blob" });
      const blob = new Blob([resp.data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${label.toLowerCase().replace(/\s+/g, "-")}-export.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`${label} exported`);
    } catch {
      toast.error("Export failed");
    }
  };

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-gray-900">Data Export</h2>
      <Card>
        <CardContent className="pt-6">
          <p className="mb-4 text-sm text-gray-600">
            Export your studio data as CSV files. Your data is always yours — download it anytime.
          </p>
          <div className="grid gap-2 sm:grid-cols-3">
            {exports.map((exp) => (
              <button
                key={exp.label}
                onClick={() => handleExport(exp.path, exp.label)}
                className="flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-3 text-left text-sm transition-colors hover:border-indigo-300 hover:bg-indigo-50"
              >
                <span>{exp.icon}</span>
                <span className="font-medium text-gray-700">{exp.label}</span>
                <Download className="ml-auto h-3.5 w-3.5 text-gray-400" />
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Communications Section (SendGrid + Twilio) ───────────────────────────

function CommunicationsSection() {
  const queryClient = useQueryClient();
  const [sgApiKey, setSgApiKey] = useState("");
  const [sgFromEmail, setSgFromEmail] = useState("");
  const [sgFromName, setSgFromName] = useState("");
  const [twAccountSid, setTwAccountSid] = useState("");
  const [twAuthToken, setTwAuthToken] = useState("");
  const [twPhone, setTwPhone] = useState("");

  const { data: status } = useQuery({
    queryKey: ["communications-status"],
    queryFn: () => communicationsApi.getStatus().then((r) => r.data),
  });

  const connectSgMut = useMutation({
    mutationFn: () => communicationsApi.connectSendGrid({ api_key: sgApiKey, from_email: sgFromEmail || undefined, from_name: sgFromName || undefined }),
    onSuccess: () => { toast.success("SendGrid connected"); setSgApiKey(""); queryClient.invalidateQueries({ queryKey: ["communications-status"] }); },
    onError: () => toast.error("Failed to connect SendGrid"),
  });
  const testSgMut = useMutation({
    mutationFn: () => communicationsApi.testSendGrid({ api_key: sgApiKey, from_email: sgFromEmail || undefined, from_name: sgFromName || undefined }),
    onSuccess: (r: any) => r.data.success ? toast.success("SendGrid test passed") : toast.error(r.data.message),
    onError: () => toast.error("SendGrid test failed"),
  });
  const disconnectSgMut = useMutation({
    mutationFn: () => communicationsApi.disconnectSendGrid(),
    onSuccess: () => { toast.success("SendGrid disconnected"); queryClient.invalidateQueries({ queryKey: ["communications-status"] }); },
  });
  const connectTwMut = useMutation({
    mutationFn: () => communicationsApi.connectTwilio({ account_sid: twAccountSid, auth_token: twAuthToken, phone_number: twPhone }),
    onSuccess: () => { toast.success("Twilio connected"); setTwAccountSid(""); setTwAuthToken(""); setTwPhone(""); queryClient.invalidateQueries({ queryKey: ["communications-status"] }); },
    onError: () => toast.error("Failed to connect Twilio"),
  });
  const testTwMut = useMutation({
    mutationFn: () => communicationsApi.testTwilio({ account_sid: twAccountSid, auth_token: twAuthToken, phone_number: twPhone }),
    onSuccess: (r: any) => r.data.success ? toast.success("Twilio test passed") : toast.error(r.data.message),
    onError: () => toast.error("Twilio test failed"),
  });
  const disconnectTwMut = useMutation({
    mutationFn: () => communicationsApi.disconnectTwilio(),
    onSuccess: () => { toast.success("Twilio disconnected"); queryClient.invalidateQueries({ queryKey: ["communications-status"] }); },
  });

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold text-gray-900">Communications</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="rounded-full bg-blue-100 p-2"><Mail className="h-4 w-4 text-blue-600" /></div>
                <CardTitle className="text-base">SendGrid</CardTitle>
              </div>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${status?.sendgrid_connected ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                {status?.sendgrid_connected ? "Connected" : "Not Connected"}
              </span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-gray-500">Email delivery for campaigns, notifications, and AI engagement.</p>
            {status?.sendgrid_connected ? (
              <div className="space-y-2">
                <p className="text-sm text-gray-600">From: <strong>{status.sendgrid_from_email}</strong>{status.sendgrid_from_name && ` (${status.sendgrid_from_name})`}</p>
                <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50" onClick={() => confirm("Disconnect SendGrid?") && disconnectSgMut.mutate()}>Disconnect</Button>
              </div>
            ) : (
              <div className="space-y-3">
                <div><Label htmlFor="sg-key2">API Key</Label><Input id="sg-key2" type="password" value={sgApiKey} onChange={(e) => setSgApiKey(e.target.value)} placeholder="SG.xxxxxxx..." /></div>
                <div className="grid grid-cols-2 gap-2">
                  <div><Label htmlFor="sg-email2">From Email</Label><Input id="sg-email2" type="email" value={sgFromEmail} onChange={(e) => setSgFromEmail(e.target.value)} placeholder="hello@studio.com" /></div>
                  <div><Label htmlFor="sg-name2">From Name</Label><Input id="sg-name2" value={sgFromName} onChange={(e) => setSgFromName(e.target.value)} placeholder="Your Studio" /></div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => testSgMut.mutate()} disabled={!sgApiKey || testSgMut.isPending}>{testSgMut.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Test</Button>
                  <Button size="sm" onClick={() => connectSgMut.mutate()} disabled={!sgApiKey || connectSgMut.isPending}>{connectSgMut.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Connect</Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="rounded-full bg-red-100 p-2"><MessageSquare className="h-4 w-4 text-red-600" /></div>
                <CardTitle className="text-base">Twilio</CardTitle>
              </div>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${status?.twilio_connected ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                {status?.twilio_connected ? "Connected" : "Not Connected"}
              </span>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-gray-500">SMS messaging for reminders, campaigns, and AI office manager.</p>
            {status?.twilio_connected ? (
              <div className="space-y-2">
                <p className="text-sm text-gray-600">Phone: <strong>{status.twilio_phone_number}</strong></p>
                <Button variant="outline" size="sm" className="text-red-600 hover:bg-red-50" onClick={() => confirm("Disconnect Twilio?") && disconnectTwMut.mutate()}>Disconnect</Button>
              </div>
            ) : (
              <div className="space-y-3">
                <div><Label htmlFor="tw-sid2">Account SID</Label><Input id="tw-sid2" value={twAccountSid} onChange={(e) => setTwAccountSid(e.target.value)} placeholder="ACxxxxxxx..." /></div>
                <div><Label htmlFor="tw-tok2">Auth Token</Label><Input id="tw-tok2" type="password" value={twAuthToken} onChange={(e) => setTwAuthToken(e.target.value)} /></div>
                <div><Label htmlFor="tw-ph2">Phone Number</Label><Input id="tw-ph2" value={twPhone} onChange={(e) => setTwPhone(e.target.value)} placeholder="+15551234567" /></div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => testTwMut.mutate()} disabled={!twAccountSid || !twAuthToken || !twPhone || testTwMut.isPending}>{testTwMut.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Test</Button>
                  <Button size="sm" onClick={() => connectTwMut.mutate()} disabled={!twAccountSid || !twAuthToken || !twPhone || connectTwMut.isPending}>{connectTwMut.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}Connect</Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
