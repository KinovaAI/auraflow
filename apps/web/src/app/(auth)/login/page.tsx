"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import { useState } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";

import { useAuthStore } from "@/stores/auth-store";
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

const loginSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const completeMfaLogin = useAuthStore((s) => s.completeMfaLogin);
  const [showPassword, setShowPassword] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaSubmitting, setMfaSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  const navigateAfterLogin = () => {
    if (localStorage.getItem("force_password_reset") === "1") {
      router.push("/change-password");
      return;
    }
    const user = useAuthStore.getState().user;
    const role = user?.organizations?.[0]?.role;
    if (role === "member") {
      router.push("/portal");
    } else if (role) {
      router.push("/dashboard");
    } else {
      router.push("/onboarding");
    }
  };

  const onSubmit = async (data: LoginForm) => {
    try {
      await login(data.email, data.password);
      navigateAfterLogin();
    } catch (err: unknown) {
      if (err instanceof Error && err.message === "MFA_REQUIRED") {
        setMfaToken((err as unknown as { mfaToken: string }).mfaToken);
        return;
      }
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Login failed. Check your credentials.";
      toast.error(message);
    }
  };

  const onMfaSubmit = async () => {
    if (!mfaToken || mfaCode.length < 6) return;
    setMfaSubmitting(true);
    try {
      await completeMfaLogin(mfaToken, mfaCode);
      navigateAfterLogin();
    } catch {
      toast.error("Invalid code. Please try again.");
      setMfaCode("");
    } finally {
      setMfaSubmitting(false);
    }
  };

  if (mfaToken) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Two-factor authentication</CardTitle>
          <CardDescription>
            Enter the 6-digit code from your authenticator app
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="mfa-code">Verification code</Label>
            <Input
              id="mfa-code"
              type="text"
              inputMode="numeric"
              placeholder="000000"
              maxLength={8}
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onMfaSubmit()}
              autoFocus
            />
            <p className="text-xs text-gray-500">
              You can also use a backup code
            </p>
          </div>
        </CardContent>
        <CardFooter className="flex-col gap-4">
          <Button
            className="w-full"
            onClick={onMfaSubmit}
            disabled={mfaSubmitting || mfaCode.length < 6}
          >
            {mfaSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Verifying...
              </>
            ) : (
              "Verify"
            )}
          </Button>
          <button
            type="button"
            onClick={() => { setMfaToken(null); setMfaCode(""); }}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Use a different account
          </button>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Enter your email and password to access your studio
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              {...register("email")}
            />
            {errors.email && (
              <p className="text-sm text-red-500">{errors.email.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                autoComplete="current-password"
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
          <div className="flex justify-end">
            <Link
              href="/forgot-password"
              className="text-sm text-indigo-600 hover:text-indigo-500"
            >
              Forgot password?
            </Link>
          </div>
        </CardContent>
        <CardFooter className="flex-col gap-4">
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              "Sign in"
            )}
          </Button>
          <p className="text-center text-sm text-gray-500">
            Don&apos;t have an account?{" "}
            <Link
              href="/signup"
              className="font-medium text-indigo-600 hover:text-indigo-500"
            >
              Create one
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
