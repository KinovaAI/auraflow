"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { useAuthStore } from "@/stores/auth-store";
import { PortalHeader } from "@/components/portal/portal-header";
import { EmailVerificationBanner } from "@/components/dashboard/email-verification-banner";
import { AIChatbot } from "@/components/dashboard/ai-chatbot";
import { portalApi } from "@/lib/portal-api";

export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isLoading } = useAuth();
  const user = useAuthStore((s) => s.user);
  const [checkedPayment, setCheckedPayment] = useState(false);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  // Force members who need payment setup to the payment-methods page
  useEffect(() => {
    if (!isAuthenticated || checkedPayment) return;
    if (pathname?.includes("/payment-methods") || pathname?.includes("/waiver")) {
      setCheckedPayment(true);
      return;
    }
    portalApi.getProfile().then((resp) => {
      setCheckedPayment(true);
      const profile = (resp as any)?.data ?? resp;
      const slug = pathname?.split("/")[1] || "";
      if (profile?.waiver_required) {
        router.push(`/${slug}/portal/waiver`);
      } else if (profile?.payment_setup_required) {
        router.push(`/${slug}/portal/payment-methods?setup=1`);
      }
    }).catch(() => setCheckedPayment(true));
  }, [isAuthenticated, checkedPayment, pathname, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <PortalHeader />
      {user && !user.email_verified && <EmailVerificationBanner />}
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
        {children}
      </main>
      <AIChatbot />
    </div>
  );
}
