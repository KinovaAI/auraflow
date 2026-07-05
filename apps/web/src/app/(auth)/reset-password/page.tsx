"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import { useState, Suspense } from "react";
import { Eye, EyeOff, Loader2, CheckCircle, ArrowLeft } from "lucide-react";

import { authApi } from "@/lib/auth-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Keep these rules aligned with apps/api/app/schemas/auth.py
// `ResetPasswordRequest.password_strength` — mismatched rules caused
// Elaine Bredfeldt's "reset link expired" reports (frontend let 8-char
// passwords through; backend returned 422; catch-all toast wrongly
// blamed the token).
const resetSchema = z
  .object({
    password: z
      .string()
      .min(10, "Password must be at least 10 characters")
      .regex(/[A-Za-z]/, "Password must contain at least one letter")
      .regex(/\d/, "Password must contain at least one number"),
    confirmPassword: z.string(),
  })
  .refine((d) => d.password === d.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type ResetForm = z.infer<typeof resetSchema>;

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");
  const [showPassword, setShowPassword] = useState(false);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetForm>({
    resolver: zodResolver(resetSchema),
  });

  if (!token) {
    return (
      <Card>
        <CardHeader className="items-center text-center">
          <CardTitle>Invalid reset link</CardTitle>
          <CardDescription>
            This password reset link is invalid or has expired.
          </CardDescription>
        </CardHeader>
        <CardFooter className="justify-center">
          <Link href="/forgot-password">
            <Button variant="outline">Request a new link</Button>
          </Link>
        </CardFooter>
      </Card>
    );
  }

  if (success) {
    return (
      <Card>
        <CardHeader className="items-center text-center">
          <CheckCircle className="mb-2 h-12 w-12 text-green-500" />
          <CardTitle>Password reset</CardTitle>
          <CardDescription>
            Your password has been updated. You can now sign in.
          </CardDescription>
        </CardHeader>
        <CardFooter className="justify-center">
          <Link href="/login">
            <Button>Sign in</Button>
          </Link>
        </CardFooter>
      </Card>
    );
  }

  const onSubmit = async (data: ResetForm) => {
    try {
      await authApi.resetPassword(token, data.password);
      setSuccess(true);
    } catch (err: unknown) {
      // Pull the backend's actual reason out instead of always blaming
      // the token. Pydantic 422s surface as { detail: [{msg, loc}, ...] };
      // explicit token errors surface as { detail: "..." }.
      type ApiErr = {
        response?: {
          status?: number;
          data?: { detail?: string | Array<{ msg?: string }> };
        };
      };
      const e = err as ApiErr;
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      let message: string;
      if (status === 400 && typeof detail === "string") {
        // Genuine expired/invalid token
        message = detail;
      } else if (Array.isArray(detail)) {
        // Pydantic validation errors — show the first specific issue
        message =
          detail
            .map((d) => d?.msg)
            .filter(Boolean)
            .join("; ") ||
          "Please check that your password meets the requirements.";
      } else if (typeof detail === "string") {
        message = detail;
      } else {
        message = "Something went wrong. Please try again.";
      }
      toast.error(message);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set new password</CardTitle>
        <CardDescription>Enter your new password below</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password">New password</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="At least 10 characters, with a letter and a number"
                autoComplete="new-password"
                {...register("password")}
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
            {errors.password && (
              <p className="text-sm text-red-500">{errors.password.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm password</Label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="Re-enter your password"
              autoComplete="new-password"
              {...register("confirmPassword")}
            />
            {errors.confirmPassword && (
              <p className="text-sm text-red-500">
                {errors.confirmPassword.message}
              </p>
            )}
          </div>
        </CardContent>
        <CardFooter className="flex-col gap-4">
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Resetting...
              </>
            ) : (
              "Reset password"
            )}
          </Button>
          <Link
            href="/login"
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            <ArrowLeft className="mr-1 inline h-3 w-3" />
            Back to sign in
          </Link>
        </CardFooter>
      </form>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
          </CardContent>
        </Card>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
