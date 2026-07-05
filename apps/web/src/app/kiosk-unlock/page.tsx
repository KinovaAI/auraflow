"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Lock, Unlock, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authApi } from "@/lib/auth-api";

/**
 * Owner-authenticated unlock page for the device-level kiosk lock.
 *
 * Lives OUTSIDE the /dashboard route group so it's reachable from a
 * locked iPad (the middleware wouldn't let /dashboard/* through).
 *
 * Flow:
 *   1. Owner enters email + password.
 *   2. We hit the normal /auth/login endpoint — same path the regular
 *      login form uses, so no new backend surface.
 *   3. On success we inspect the returned user/role; only owner or
 *      admin can clear the lock.
 *   4. Clear the auraflow_kiosk_lock cookie, then redirect to
 *      /dashboard (now reachable because the cookie is gone).
 */
export default function KioskUnlockPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // Login. The httponly auth cookie gets set as a side-effect on
      // success; we use the response itself to read role.
      await authApi.login({ email, password });
      // Fetch /users/me to confirm role.
      const me = await authApi.getMe();
      const orgRole = me.data?.active_org_role;
      const isOwnerOrAdmin =
        orgRole === "owner" ||
        orgRole === "admin" ||
        me.data?.organizations?.some((o) => o.role === "owner" || o.role === "admin");
      if (!isOwnerOrAdmin) {
        setError(
          "Only an owner or admin can unlock this device.",
        );
        setSubmitting(false);
        return;
      }
      // Clear the kiosk-lock cookie. Same path/domain attrs the setter
      // used so the browser deletes it.
      document.cookie =
        "auraflow_kiosk_lock=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax";
      router.push("/dashboard");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Login failed. Check the email and password.",
      );
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-lg">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-50">
            <Unlock className="h-7 w-7 text-amber-600" />
          </div>
          <h1 className="text-xl font-semibold text-gray-900">
            Unlock this device
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            Sign in with an owner or admin account to remove the kiosk
            lock from this browser.
          </p>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            <Lock className="mr-1 h-4 w-4" />
            Unlock this device
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-gray-400">
          <Link href="/kiosk-locked" className="hover:text-gray-600">
            ← Back to kiosk
          </Link>
        </p>
      </div>
    </div>
  );
}
