"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import {
  Loader2,
  Building2,
  MapPin,
  DoorOpen,
  Users,
  CreditCard,
  Check,
  ArrowRight,
  ArrowLeft,
} from "lucide-react";

import { useAuthStore } from "@/stores/auth-store";
import { organizationsApi } from "@/lib/organizations-api";
import { authApi } from "@/lib/auth-api";
import { studiosApi, roomsApi } from "@/lib/scheduling-api";
import { paymentsApi } from "@/lib/payments-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

const TIMEZONES = [
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "America/Phoenix",
  "Pacific/Honolulu",
  "America/Anchorage",
];

const STEPS = [
  { icon: Building2, label: "Basics" },
  { icon: MapPin, label: "Details" },
  { icon: DoorOpen, label: "Room" },
  { icon: Users, label: "Team" },
  { icon: CreditCard, label: "Payments" },
];

// ── Step 1: Studio Basics ──────────────────────────────────────────────────

const basicsSchema = z.object({
  name: z.string().min(2, "Studio name is required"),
  slug: z
    .string()
    .min(3, "At least 3 characters")
    .regex(
      /^[a-z0-9][a-z0-9-]*[a-z0-9]$/,
      "Lowercase letters, numbers, and hyphens only"
    ),
  timezone: z.string().min(1, "Select a timezone"),
});

type BasicsForm = z.infer<typeof basicsSchema>;

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export default function OnboardingPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [currentStep, setCurrentStep] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [orgSlug, setOrgSlug] = useState<string | null>(null);
  const [studioId, setStudioId] = useState<string | null>(null);

  // Step 1 form
  const basicsForm = useForm<BasicsForm>({
    resolver: zodResolver(basicsSchema),
    defaultValues: { timezone: "America/Los_Angeles" },
  });

  // Step 2 data
  const [details, setDetails] = useState({
    address_line1: "",
    city: "",
    state: "",
    postal_code: "",
    phone: "",
    email: "",
  });

  // Step 3 data
  const [room, setRoom] = useState({ name: "", capacity: "" });

  // Step 4 data
  const [invites, setInvites] = useState([{ email: "", role: "instructor" }]);

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const name = e.target.value;
    basicsForm.setValue("name", name);
    const slug = slugify(name);
    if (slug.length >= 3) {
      basicsForm.setValue("slug", slug);
    }
  };

  const handleFinish = useCallback(() => {
    router.push("/onboarding/plan");
  }, [router]);

  // Step 1: Create org
  const handleBasicsSubmit = async (data: BasicsForm) => {
    setIsProcessing(true);
    try {
      await organizationsApi.create({
        name: data.name,
        slug: data.slug,
        timezone: data.timezone,
      });

      const { data: tokens } = await organizationsApi.switchOrg(data.slug);
      localStorage.setItem("access_token", tokens.access_token);
      localStorage.setItem("refresh_token", tokens.refresh_token);

      const { data: updatedUser } = await authApi.getMe();
      useAuthStore.setState({
        user: updatedUser,
        isAuthenticated: true,
        isLoading: false,
      });

      setOrgSlug(data.slug);

      // Get the studio ID for subsequent steps
      const { data: studios } = await studiosApi.list();
      if (studios.length > 0) {
        setStudioId(studios[0].id);
      }

      toast.success("Studio created!");
      setCurrentStep(1);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to create studio. Please try again.";
      toast.error(message);
    } finally {
      setIsProcessing(false);
    }
  };

  // Step 2: Update studio details
  const handleDetailsSave = async () => {
    if (!studioId) return;
    const hasAnyField = Object.values(details).some((v) => v.trim());
    if (!hasAnyField) {
      setCurrentStep(2);
      return;
    }
    setIsProcessing(true);
    try {
      const updateData: Record<string, string> = {};
      for (const [key, val] of Object.entries(details)) {
        if (val.trim()) updateData[key] = val.trim();
      }
      await studiosApi.update(studioId, updateData);
      toast.success("Studio details saved");
      setCurrentStep(2);
    } catch {
      toast.error("Failed to save details");
    } finally {
      setIsProcessing(false);
    }
  };

  // Step 3: Create room
  const handleRoomSave = async () => {
    if (!studioId || !room.name.trim()) {
      setCurrentStep(3);
      return;
    }
    setIsProcessing(true);
    try {
      await roomsApi.create(studioId, {
        name: room.name.trim(),
        capacity: room.capacity ? parseInt(room.capacity) : undefined,
      });
      toast.success("Room created");
      setCurrentStep(3);
    } catch {
      toast.error("Failed to create room");
    } finally {
      setIsProcessing(false);
    }
  };

  // Step 4: Invite team
  const handleInvitesSave = async () => {
    if (!orgSlug) return;
    const validInvites = invites.filter((i) => i.email.trim());
    if (validInvites.length === 0) {
      setCurrentStep(4);
      return;
    }
    setIsProcessing(true);
    try {
      for (const inv of validInvites) {
        await organizationsApi.inviteMember(orgSlug, {
          email: inv.email.trim(),
          role: inv.role,
        });
      }
      toast.success(`Invited ${validInvites.length} team member(s)`);
      setCurrentStep(4);
    } catch {
      toast.error("Failed to send invites");
    } finally {
      setIsProcessing(false);
    }
  };

  // Step 5: Connect Stripe
  const handleStripeConnect = async () => {
    setIsProcessing(true);
    try {
      const returnUrl = `${window.location.origin}/onboarding/plan`;
      const refreshUrl = `${window.location.origin}/onboarding`;
      const { data } = await paymentsApi.startOnboarding(returnUrl, refreshUrl);
      window.location.href = data.url;
    } catch {
      toast.error("Failed to start Stripe setup. You can do this later in Settings.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900">
            Set up your studio
          </h1>
          <p className="mt-2 text-sm text-gray-500">
            Hey {user?.first_name || "there"}, let&apos;s get you up and running.
          </p>
        </div>

        {/* Progress bar */}
        <div className="mb-8 flex items-center justify-between">
          {STEPS.map((step, i) => (
            <div key={step.label} className="flex flex-1 flex-col items-center">
              <div className="flex w-full items-center">
                {i > 0 && (
                  <div
                    className={`h-0.5 flex-1 ${
                      i <= currentStep ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  />
                )}
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium ${
                    i < currentStep
                      ? "bg-indigo-600 text-white"
                      : i === currentStep
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {i < currentStep ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <step.icon className="h-4 w-4" />
                  )}
                </div>
                {i < STEPS.length - 1 && (
                  <div
                    className={`h-0.5 flex-1 ${
                      i < currentStep ? "bg-indigo-600" : "bg-gray-200"
                    }`}
                  />
                )}
              </div>
              <span className="mt-1 text-[10px] text-gray-500">
                {step.label}
              </span>
            </div>
          ))}
        </div>

        <Card>
          <CardContent className="pt-6">
            {/* Step 1: Studio Basics */}
            {currentStep === 0 && (
              <form onSubmit={basicsForm.handleSubmit(handleBasicsSubmit)}>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Studio name</Label>
                    <Input
                      id="name"
                      placeholder="Your Studio"
                      {...basicsForm.register("name")}
                      onChange={handleNameChange}
                    />
                    {basicsForm.formState.errors.name && (
                      <p className="text-sm text-red-500">
                        {basicsForm.formState.errors.name.message}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="slug">Studio URL</Label>
                    <div className="flex items-center gap-0">
                      <Input
                        id="slug"
                        placeholder="your-studio"
                        className="rounded-r-none"
                        {...basicsForm.register("slug")}
                      />
                      <span className="flex h-10 items-center rounded-r-md border border-l-0 border-gray-200 bg-gray-50 px-3 text-sm text-gray-500">
                        .auraflow.fit
                      </span>
                    </div>
                    {basicsForm.formState.errors.slug && (
                      <p className="text-sm text-red-500">
                        {basicsForm.formState.errors.slug.message}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="timezone">Timezone</Label>
                    <select
                      id="timezone"
                      className="flex h-10 w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      {...basicsForm.register("timezone")}
                    >
                      {TIMEZONES.map((tz) => (
                        <option key={tz} value={tz}>
                          {tz.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </div>

                  <Button
                    type="submit"
                    className="w-full"
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating studio...
                      </>
                    ) : (
                      <>
                        Continue
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </form>
            )}

            {/* Step 2: Studio Details */}
            {currentStep === 1 && (
              <div className="space-y-4">
                <p className="text-sm text-gray-500">
                  Add your studio&apos;s address and contact info. You can skip this
                  and add it later in Settings.
                </p>

                <div className="space-y-2">
                  <Label>Address</Label>
                  <Input
                    placeholder="123 Main St"
                    value={details.address_line1}
                    onChange={(e) =>
                      setDetails({ ...details, address_line1: e.target.value })
                    }
                  />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-2">
                    <Label>City</Label>
                    <Input
                      placeholder="Your City"
                      value={details.city}
                      onChange={(e) =>
                        setDetails({ ...details, city: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>State</Label>
                    <Input
                      placeholder="CA"
                      value={details.state}
                      onChange={(e) =>
                        setDetails({ ...details, state: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>ZIP</Label>
                    <Input
                      placeholder="93711"
                      value={details.postal_code}
                      onChange={(e) =>
                        setDetails({ ...details, postal_code: e.target.value })
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>Phone</Label>
                    <Input
                      placeholder="(559) 555-0100"
                      value={details.phone}
                      onChange={(e) =>
                        setDetails({ ...details, phone: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Email</Label>
                    <Input
                      placeholder="hello@studio.com"
                      value={details.email}
                      onChange={(e) =>
                        setDetails({ ...details, email: e.target.value })
                      }
                    />
                  </div>
                </div>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setCurrentStep(2)}
                  >
                    Skip
                  </Button>
                  <Button
                    className="flex-1"
                    onClick={handleDetailsSave}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        Save & Continue
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 3: First Room */}
            {currentStep === 2 && (
              <div className="space-y-4">
                <p className="text-sm text-gray-500">
                  Create your first room. Rooms help you avoid scheduling
                  conflicts and track capacity.
                </p>

                <div className="space-y-2">
                  <Label>Room name</Label>
                  <Input
                    placeholder="Main Studio"
                    value={room.name}
                    onChange={(e) =>
                      setRoom({ ...room, name: e.target.value })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label>Capacity (optional)</Label>
                  <Input
                    type="number"
                    placeholder="25"
                    value={room.capacity}
                    onChange={(e) =>
                      setRoom({ ...room, capacity: e.target.value })
                    }
                  />
                </div>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    onClick={() => setCurrentStep(1)}
                  >
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setCurrentStep(3)}
                  >
                    Skip
                  </Button>
                  <Button
                    className="flex-1"
                    onClick={handleRoomSave}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        Save & Continue
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 4: Invite Team */}
            {currentStep === 3 && (
              <div className="space-y-4">
                <p className="text-sm text-gray-500">
                  Invite your instructors and staff. They&apos;ll receive an email
                  to set up their account.
                </p>

                {invites.map((inv, i) => (
                  <div key={i} className="flex gap-3">
                    <div className="flex-1 space-y-1">
                      <Input
                        placeholder="email@example.com"
                        value={inv.email}
                        onChange={(e) => {
                          const updated = [...invites];
                          updated[i] = { ...inv, email: e.target.value };
                          setInvites(updated);
                        }}
                      />
                    </div>
                    <select
                      className="h-10 rounded-md border border-gray-200 bg-white px-3 text-sm"
                      value={inv.role}
                      onChange={(e) => {
                        const updated = [...invites];
                        updated[i] = { ...inv, role: e.target.value };
                        setInvites(updated);
                      }}
                    >
                      <option value="instructor">Instructor</option>
                      <option value="admin">Admin</option>
                      <option value="front_desk">Front Desk</option>
                    </select>
                  </div>
                ))}

                <button
                  type="button"
                  className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
                  onClick={() =>
                    setInvites([...invites, { email: "", role: "instructor" }])
                  }
                >
                  + Add another
                </button>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    onClick={() => setCurrentStep(2)}
                  >
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={() => setCurrentStep(4)}
                  >
                    Skip
                  </Button>
                  <Button
                    className="flex-1"
                    onClick={handleInvitesSave}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <>
                        Send Invites
                        <ArrowRight className="ml-2 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 5: Connect Payments */}
            {currentStep === 4 && (
              <div className="space-y-4">
                <p className="text-sm text-gray-500">
                  Connect your Stripe account to accept payments from members.
                  This takes about 5 minutes.
                </p>

                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center">
                  <CreditCard className="mx-auto h-10 w-10 text-gray-400" />
                  <p className="mt-2 text-sm font-medium text-gray-700">
                    Accept credit cards, debit cards, and more
                  </p>
                  <p className="mt-1 text-xs text-gray-500">
                    Powered by Stripe Connect
                  </p>
                </div>

                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    onClick={() => setCurrentStep(3)}
                  >
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back
                  </Button>
                  <Button
                    variant="outline"
                    className="flex-1"
                    onClick={handleFinish}
                  >
                    Skip for now
                  </Button>
                  <Button
                    className="flex-1"
                    onClick={handleStripeConnect}
                    disabled={isProcessing}
                  >
                    {isProcessing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      "Connect Stripe"
                    )}
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
