"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { Sidebar } from "@/components/dashboard/sidebar";
import { MobileSidebar } from "@/components/dashboard/mobile-sidebar";
import { TopBar } from "@/components/dashboard/top-bar";
import { EmailVerificationBanner } from "@/components/dashboard/email-verification-banner";
import { TrialExpirationBanner } from "@/components/dashboard/trial-expiration-banner";
import { VoiceCommandButton } from "@/components/dashboard/voice-command-button";
import { AIChatbot } from "@/components/dashboard/ai-chatbot";
import { useDashboardShortcuts } from "@/hooks/use-dashboard-shortcuts";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  useDashboardShortcuts();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isLoading && isAuthenticated && user && user.organizations.length === 0) {
      router.push("/onboarding");
    }
  }, [isLoading, isAuthenticated, user, router]);

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

  if (user && user.organizations.length === 0) {
    return null;
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <MobileSidebar open={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar onMenuClick={() => setMobileMenuOpen(true)} />
        <TrialExpirationBanner />
        {user && !user.email_verified && <EmailVerificationBanner />}
        <main className="flex-1 overflow-y-auto bg-gray-50 p-4 md:p-6">
          {children}
        </main>
      </div>
      <VoiceCommandButton />
      <AIChatbot />
    </div>
  );
}
