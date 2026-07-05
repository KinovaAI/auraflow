"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useStudioStore } from "@/stores/studio-store";
import { useAuth } from "@/hooks/use-auth";

// Dynamically import the real kiosk to avoid duplicating code
import dynamic from "next/dynamic";

const KioskContent = dynamic(
  () => import("@/components/kiosk/kiosk-content"),
  { ssr: false }
);

export default function StudioKioskPage() {
  const params = useParams();
  const slug = params.slug as string;
  const { isAuthenticated, isLoading } = useAuth();
  const studios = useStudioStore((s) => s.studios);
  const switchStudio = useStudioStore((s) => s.switchStudio);
  const activeStudioId = useStudioStore((s) => s.activeStudioId);

  // Set the studio from the user's studio list for this org
  useEffect(() => {
    if (!studios.length || activeStudioId) return;
    // The URL slug is the org slug — select the first (or primary) studio
    const primary = studios.find((s) => s.is_primary) || studios[0];
    if (primary) {
      switchStudio(primary.studio_id);
    }
  }, [studios, activeStudioId, switchStudio]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <p className="text-lg text-gray-500">Please log in to access the kiosk.</p>
      </div>
    );
  }

  if (!activeStudioId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return <KioskContent />;
}
