"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Save, AlertCircle, Eye, EyeOff, Lock } from "lucide-react";
import toast from "react-hot-toast";

import { portalApi } from "@/lib/portal-api";
import type { PortalProfile } from "@/lib/portal-api";
import { authApi } from "@/lib/auth-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const profileSchema = z.object({
  phone: z.string().optional(),
  emergency_contact_name: z.string().optional(),
  emergency_contact_phone: z.string().optional(),
  email_opt_in: z.boolean(),
  sms_opt_in: z.boolean(),
});

type ProfileForm = z.infer<typeof profileSchema>;

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Current password is required"),
    new_password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type PasswordForm = z.infer<typeof passwordSchema>;

function formatMemberSince(isoStr: string) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

export default function PortalProfilePage() {
  const [profile, setProfile] = useState<PortalProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting, isDirty },
  } = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
  });

  const {
    register: registerPw,
    handleSubmit: handleSubmitPw,
    reset: resetPw,
    formState: { errors: pwErrors, isSubmitting: isPwSubmitting },
  } = useForm<PasswordForm>({
    resolver: zodResolver(passwordSchema),
  });

  const onPasswordSubmit = async (data: PasswordForm) => {
    try {
      await authApi.changePassword(data.new_password, data.current_password);
      toast.success("Password updated successfully");
      resetPw();
      setShowCurrentPw(false);
      setShowNewPw(false);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to update password";
      toast.error(message);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await portalApi.getProfile();
        setProfile(data);
        reset({
          phone: data.phone || "",
          emergency_contact_name: data.emergency_contact_name || "",
          emergency_contact_phone: data.emergency_contact_phone || "",
          email_opt_in: data.email_opt_in,
          sms_opt_in: data.sms_opt_in,
        });
      } catch (err: unknown) {
        const message =
          (err as { response?: { data?: { detail?: string } } })?.response?.data
            ?.detail || "Failed to load profile";
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSubmit = async (data: ProfileForm) => {
    try {
      const { data: updated } = await portalApi.updateProfile(data);
      setProfile(updated);
      reset({
        phone: updated.phone || "",
        emergency_contact_name: updated.emergency_contact_name || "",
        emergency_contact_phone: updated.emergency_contact_phone || "",
        email_opt_in: updated.email_opt_in,
        sms_opt_in: updated.sms_opt_in,
      });
      toast.success("Profile updated");
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to update profile";
      toast.error(message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div>
        <h1 className="mb-6 text-2xl font-bold text-gray-900">My Profile</h1>
        <Card>
          <CardContent className="py-12 text-center">
            <AlertCircle className="mx-auto mb-3 h-10 w-10 text-red-400" />
            <p className="font-medium text-gray-700">
              {error || "Profile not found"}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              Please contact the studio for assistance.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">My Profile</h1>

      {/* Read-only info */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Account Info</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-sm text-gray-400">Name</p>
              <p className="font-medium text-gray-900">
                {profile.first_name} {profile.last_name}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Email</p>
              <p className="font-medium text-gray-900">{profile.email}</p>
            </div>
            {profile.member_number && (
              <div>
                <p className="text-sm text-gray-400">Member #</p>
                <p className="font-medium text-gray-900">{profile.member_number}</p>
              </div>
            )}
            {profile.created_at && (
              <div>
                <p className="text-sm text-gray-400">Member since</p>
                <p className="font-medium text-gray-900">
                  {formatMemberSince(profile.created_at)}
                </p>
              </div>
            )}
            <div>
              <p className="text-sm text-gray-400">Total visits</p>
              <p className="text-xl font-bold text-indigo-600">{profile.total_visits}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Change Password */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Lock className="h-4 w-4" />
            Change Password
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmitPw(onPasswordSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current_password">Current Password</Label>
              <div className="relative">
                <Input
                  id="current_password"
                  type={showCurrentPw ? "text" : "password"}
                  placeholder="Enter current password"
                  autoComplete="current-password"
                  {...registerPw("current_password")}
                />
                <button
                  type="button"
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                  onClick={() => setShowCurrentPw(!showCurrentPw)}
                  tabIndex={-1}
                >
                  {showCurrentPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {pwErrors.current_password && (
                <p className="text-sm text-red-500">{pwErrors.current_password.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="new_password_profile">New Password</Label>
              <div className="relative">
                <Input
                  id="new_password_profile"
                  type={showNewPw ? "text" : "password"}
                  placeholder="Enter new password (min 8 characters)"
                  autoComplete="new-password"
                  {...registerPw("new_password")}
                />
                <button
                  type="button"
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                  onClick={() => setShowNewPw(!showNewPw)}
                  tabIndex={-1}
                >
                  {showNewPw ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              {pwErrors.new_password && (
                <p className="text-sm text-red-500">{pwErrors.new_password.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm_password_profile">Confirm New Password</Label>
              <Input
                id="confirm_password_profile"
                type={showNewPw ? "text" : "password"}
                placeholder="Confirm your new password"
                autoComplete="new-password"
                {...registerPw("confirm_password")}
              />
              {pwErrors.confirm_password && (
                <p className="text-sm text-red-500">{pwErrors.confirm_password.message}</p>
              )}
            </div>
            <div className="pt-2">
              <Button type="submit" disabled={isPwSubmitting}>
                {isPwSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Updating...
                  </>
                ) : (
                  <>
                    <Lock className="mr-2 h-4 w-4" />
                    Update Password
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Editable fields */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Contact & Preferences</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="phone">Phone</Label>
              <Input
                id="phone"
                type="tel"
                placeholder="(555) 123-4567"
                {...register("phone")}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="emergency_contact_name">Emergency contact name</Label>
                <Input
                  id="emergency_contact_name"
                  placeholder="Jane Doe"
                  {...register("emergency_contact_name")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="emergency_contact_phone">Emergency contact phone</Label>
                <Input
                  id="emergency_contact_phone"
                  type="tel"
                  placeholder="(555) 987-6543"
                  {...register("emergency_contact_phone")}
                />
              </div>
            </div>

            <div className="space-y-3 pt-2">
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  {...register("email_opt_in")}
                />
                <span className="text-sm text-gray-700">
                  Receive email updates and class reminders
                </span>
              </label>
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  {...register("sms_opt_in")}
                />
                <span className="text-sm text-gray-700">
                  Receive SMS notifications
                </span>
              </label>
            </div>

            <div className="pt-2">
              <Button type="submit" disabled={isSubmitting || !isDirty}>
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="mr-2 h-4 w-4" />
                    Save changes
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
