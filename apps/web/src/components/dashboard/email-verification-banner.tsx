"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, X, CheckCircle2 } from "lucide-react";
import toast from "react-hot-toast";
import { authApi } from "@/lib/auth-api";
import { useAuthStore } from "@/stores/auth-store";

export function EmailVerificationBanner() {
  const [dismissed, setDismissed] = useState(
    () => typeof window !== "undefined" && localStorage.getItem("dismiss_verify_banner") === "1"
  );
  const [resending, setResending] = useState(false);
  const [sent, setSent] = useState(false);
  const loadUser = useAuthStore((s) => s.loadUser);

  // Refresh user state when the tab regains focus (in case they verified in another tab)
  useEffect(() => {
    const handleFocus = () => {
      loadUser();
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [loadUser]);

  if (dismissed) return null;

  const handleResend = async () => {
    setResending(true);
    try {
      await authApi.resendVerification();
      setSent(true);
      toast.success("Verification email sent! Check your inbox.");
    } catch {
      toast.error("Failed to resend. Try again later.");
    } finally {
      setResending(false);
    }
  };

  const handleDismiss = () => {
    localStorage.setItem("dismiss_verify_banner", "1");
    setDismissed(true);
  };

  return (
    <div className="flex items-center gap-3 bg-yellow-50 px-4 py-2.5 text-sm text-yellow-800 border-b border-yellow-200">
      {sent ? (
        <>
          <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-green-600" />
          <span>
            Verification email sent! Check your inbox and click the link to verify.
          </span>
        </>
      ) : (
        <>
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>
            Please verify your email address.{" "}
            <button
              onClick={handleResend}
              disabled={resending}
              className="font-medium underline hover:text-yellow-900"
            >
              {resending ? "Sending..." : "Resend verification email"}
            </button>
          </span>
        </>
      )}
      <button
        onClick={handleDismiss}
        className="ml-auto text-yellow-600 hover:text-yellow-800"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
