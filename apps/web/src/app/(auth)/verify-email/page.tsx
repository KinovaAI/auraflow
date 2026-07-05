"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, XCircle, Loader2, Mail } from "lucide-react";
import toast from "react-hot-toast";

import { authApi } from "@/lib/auth-api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error" | "waiting">(
    token ? "loading" : "waiting"
  );
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (!token) return;

    authApi
      .verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  const handleResend = async () => {
    setResending(true);
    try {
      await authApi.resendVerification();
      toast.success("Verification email sent! Check your inbox.");
    } catch {
      toast.error("Failed to resend. Please try again.");
    } finally {
      setResending(false);
    }
  };

  return (
    <Card className="text-center">
      <CardHeader>
        <CardTitle>
          {status === "loading" && "Verifying your email..."}
          {status === "success" && "Email verified!"}
          {status === "error" && "Verification failed"}
          {status === "waiting" && "Check your email"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {status === "loading" && (
          <Loader2 className="mx-auto h-12 w-12 animate-spin text-indigo-600" />
        )}

        {status === "success" && (
          <div>
            <CheckCircle2 className="mx-auto h-12 w-12 text-green-500" />
            <p className="mt-4 text-sm text-gray-600">
              Your email has been verified. You can now access all features.
            </p>
          </div>
        )}

        {status === "error" && (
          <div>
            <XCircle className="mx-auto h-12 w-12 text-red-500" />
            <p className="mt-4 text-sm text-gray-600">
              This verification link is invalid or has expired.
            </p>
          </div>
        )}

        {status === "waiting" && (
          <div>
            <Mail className="mx-auto h-12 w-12 text-indigo-600" />
            <p className="mt-4 text-sm text-gray-600">
              We sent a verification link to your email address.
              <br />
              Click the link in the email to verify your account.
            </p>
          </div>
        )}
      </CardContent>
      <CardFooter className="flex-col gap-3">
        {status === "success" && (
          <Link href="/dashboard" className="w-full">
            <Button className="w-full">Go to Dashboard</Button>
          </Link>
        )}

        {(status === "error" || status === "waiting") && (
          <Button
            variant="outline"
            className="w-full"
            onClick={handleResend}
            disabled={resending}
          >
            {resending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              "Resend verification email"
            )}
          </Button>
        )}

        <Link href="/login" className="text-sm text-gray-500 hover:text-gray-700">
          Back to login
        </Link>
      </CardFooter>
    </Card>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <Card className="text-center">
          <CardContent className="py-12">
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-indigo-600" />
          </CardContent>
        </Card>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
