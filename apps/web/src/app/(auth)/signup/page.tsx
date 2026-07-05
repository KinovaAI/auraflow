"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import { useState, useEffect } from "react";
import { Eye, EyeOff, Loader2, UserPlus } from "lucide-react";

import { useAuthStore } from "@/stores/auth-store";
import { authApi } from "@/lib/auth-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUtmTracking, getStoredUtmParams } from "@/hooks/use-utm-tracking";
import { trackConversion } from "@/lib/tracking";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const signupSchema = z
  .object({
    first_name: z.string().min(1, "First name is required"),
    last_name: z.string().min(1, "Last name is required"),
    email: z.string().email("Enter a valid email address"),
    // Match apps/api/app/schemas/auth.py RegisterRequest rules so users
    // get inline feedback instead of a generic backend rejection.
    password: z
      .string()
      .min(10, "At least 10 characters")
      .regex(/[A-Za-z]/, "Must contain at least one letter")
      .regex(/\d/, "Must contain at least one number"),
    confirm_password: z.string(),
    organization_name: z.string().optional(),
    accept_tos: z.literal(true, {
      errorMap: () => ({ message: "You must agree to the Terms of Service and Privacy Policy" }),
    }),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords don't match",
    path: ["confirm_password"],
  });

type SignupForm = z.infer<typeof signupSchema>;

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function SignupContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const registerUser = useAuthStore((s) => s.register);
  const [showPassword, setShowPassword] = useState(false);

  // Capture UTM params from URL into sessionStorage
  useUtmTracking();

  // Invite token handling
  const inviteToken = searchParams.get("invite");
  const [invite, setInvite] = useState<{
    org_slug: string;
    org_name: string;
    role: string;
    email: string;
  } | null>(null);
  const [inviteLoading, setInviteLoading] = useState(!!inviteToken);

  useEffect(() => {
    if (!inviteToken) return;
    authApi
      .validateInvite(inviteToken)
      .then((res) => {
        setInvite(res.data);
        setValue("email", res.data.email);
      })
      .catch(() => {
        toast.error("This invite link is invalid or has expired.");
      })
      .finally(() => setInviteLoading(false));
  }, [inviteToken]);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<SignupForm>({
    resolver: zodResolver(signupSchema),
  });

  const orgName = watch("organization_name");

  const onSubmit = async (data: SignupForm) => {
    try {
      const utm = getStoredUtmParams();
      await registerUser({
        email: data.email,
        password: data.password,
        first_name: data.first_name,
        last_name: data.last_name,
        organization_name: invite ? undefined : (data.organization_name || undefined),
        organization_slug: invite ? undefined : (data.organization_name
          ? slugify(data.organization_name)
          : undefined),
        invite_token: inviteToken || undefined,
        utm_source: utm.utm_source,
        utm_medium: utm.utm_medium,
        utm_campaign: utm.utm_campaign,
        gclid: utm.gclid,
        fbclid: utm.fbclid,
      });
      trackConversion("signup");
      toast.success("Account created!");
      router.push("/verify-email");
    } catch (err: unknown) {
      type ApiErr = {
        response?: {
          data?: { detail?: string | Array<{ msg?: string }> };
        };
      };
      const detail = (err as ApiErr)?.response?.data?.detail;
      let message: string;
      if (Array.isArray(detail)) {
        message =
          detail
            .map((d) => d?.msg)
            .filter(Boolean)
            .join("; ") || "Registration failed. Please try again.";
      } else if (typeof detail === "string") {
        message = detail;
      } else {
        message = "Registration failed. Please try again.";
      }
      toast.error(message);
    }
  };

  if (inviteLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>
          {invite
            ? `You've been invited to join ${invite.org_name}`
            : "Start managing your studio with AuraFlow"}
        </CardDescription>
      </CardHeader>

      {invite && (
        <div className="mx-6 mb-4 flex items-center gap-2 rounded-lg bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
          <UserPlus className="h-4 w-4 flex-shrink-0" />
          Joining as <span className="font-medium">{invite.role}</span> at{" "}
          <span className="font-medium">{invite.org_name}</span>
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="first_name">First name</Label>
              <Input
                id="first_name"
                placeholder="Jane"
                autoComplete="given-name"
                {...register("first_name")}
              />
              {errors.first_name && (
                <p className="text-sm text-red-500">
                  {errors.first_name.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="last_name">Last name</Label>
              <Input
                id="last_name"
                placeholder="Doe"
                autoComplete="family-name"
                {...register("last_name")}
              />
              {errors.last_name && (
                <p className="text-sm text-red-500">
                  {errors.last_name.message}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              readOnly={!!invite}
              className={invite ? "bg-gray-50" : ""}
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
                placeholder="8+ characters"
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
            <Label htmlFor="confirm_password">Confirm password</Label>
            <Input
              id="confirm_password"
              type="password"
              placeholder="Repeat your password"
              autoComplete="new-password"
              {...register("confirm_password")}
            />
            {errors.confirm_password && (
              <p className="text-sm text-red-500">
                {errors.confirm_password.message}
              </p>
            )}
          </div>

          {!invite && (
            <>
              <hr className="my-2" />
              <div className="space-y-2">
                <Label htmlFor="organization_name">
                  Studio name{" "}
                  <span className="font-normal text-gray-400">(optional)</span>
                </Label>
                <Input
                  id="organization_name"
                  placeholder="Your Studio"
                  {...register("organization_name")}
                />
                {orgName && (
                  <p className="text-xs text-gray-400">
                    Your studio URL will be{" "}
                    <span className="font-mono">
                      {slugify(orgName)}.auraflow.fit
                    </span>
                  </p>
                )}
              </div>
            </>
          )}

          <div className="flex items-start gap-2">
            <input
              type="checkbox"
              id="accept_tos"
              className="mt-1 h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              {...register("accept_tos")}
            />
            <Label htmlFor="accept_tos" className="text-sm font-normal text-gray-600">
              I agree to the{" "}
              <Link
                href="/terms"
                target="_blank"
                className="font-medium text-indigo-600 hover:text-indigo-500 underline"
              >
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link
                href="/privacy"
                target="_blank"
                className="font-medium text-indigo-600 hover:text-indigo-500 underline"
              >
                Privacy Policy
              </Link>
            </Label>
          </div>
          {errors.accept_tos && (
            <p className="text-sm text-red-500">{errors.accept_tos.message}</p>
          )}
        </CardContent>
        <CardFooter className="flex-col gap-4">
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating account...
              </>
            ) : (
              "Create account"
            )}
          </Button>
          <p className="text-center text-sm text-gray-500">
            Already have an account?{" "}
            <Link
              href="/login"
              className="font-medium text-indigo-600 hover:text-indigo-500"
            >
              Sign in
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}

export default function SignupPage() {
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
      <SignupContent />
    </Suspense>
  );
}
