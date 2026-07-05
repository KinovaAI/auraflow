"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import { useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { useAuthStore } from "@/stores/auth-store";
import { authApi } from "@/lib/auth-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Keep these rules ≥ what apps/api/app/api/v1/endpoints/auth.py
// `ChangePasswordRequest.password_strength` enforces (currently min 8).
// We're stricter here for consistency with reset-password and to avoid
// the same misleading "expired"/"failed" error class.
const schema = z
  .object({
    new_password: z
      .string()
      .min(10, "Password must be at least 10 characters")
      .regex(/[A-Za-z]/, "Password must contain at least one letter")
      .regex(/\d/, "Password must contain at least one number"),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type FormData = z.infer<typeof schema>;

export default function ChangePasswordPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    try {
      await authApi.changePassword(data.new_password);
      localStorage.removeItem("force_password_reset");
      toast.success("Password updated successfully");

      const role = user?.organizations?.[0]?.role;
      if (role === "member") {
        // Send members to payment methods page to set up billing
        router.push("/portal/payment-methods?setup=1");
      } else if (role) {
        router.push("/dashboard");
      } else {
        router.push("/onboarding");
      }
    } catch (err: unknown) {
      type ApiErr = {
        response?: {
          status?: number;
          data?: { detail?: string | Array<{ msg?: string }> };
        };
      };
      const e = err as ApiErr;
      const detail = e?.response?.data?.detail;
      let message: string;
      if (Array.isArray(detail)) {
        // Pydantic validation errors — surface the specific rule the user broke
        message =
          detail
            .map((d) => d?.msg)
            .filter(Boolean)
            .join("; ") ||
          "Please check that your password meets the requirements.";
      } else if (typeof detail === "string") {
        message = detail;
      } else {
        message = "Failed to update password. Please try again.";
      }
      toast.error(message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set New Password</CardTitle>
        <CardDescription>
          Your account requires a password update before continuing.
          Please choose a new password.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new_password">New Password</Label>
            <div className="relative">
              <Input
                id="new_password"
                type={showPassword ? "text" : "password"}
                placeholder="At least 10 characters, with a letter and a number"
                autoComplete="new-password"
                {...register("new_password")}
              />
              <button
                type="button"
                className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {errors.new_password && (
              <p className="text-sm text-red-500">
                {errors.new_password.message}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm_password">Confirm Password</Label>
            <Input
              id="confirm_password"
              type={showPassword ? "text" : "password"}
              placeholder="Confirm your new password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
            {errors.confirm_password && (
              <p className="text-sm text-red-500">
                {errors.confirm_password.message}
              </p>
            )}
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Updating...
              </>
            ) : (
              "Update Password"
            )}
          </Button>
        </CardContent>
      </form>
    </Card>
  );
}
