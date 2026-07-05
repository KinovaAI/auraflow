"use client";

import Link from "next/link";
import { Lock, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Shown when someone navigates to a /dashboard URL on a device that's
 * been registered as a kiosk via the `auraflow_kiosk_lock` cookie.
 *
 * The instructor / public user landing here just sees a "go to check-in"
 * button. An owner who needs to manage the device taps the small
 * unlock link at the bottom and authenticates from there.
 */
export default function KioskLockedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-lg">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-50">
          <Lock className="h-7 w-7 text-indigo-600" />
        </div>
        <h1 className="text-xl font-semibold text-gray-900">
          This iPad is in kiosk mode
        </h1>
        <p className="mt-2 text-sm text-gray-600">
          The studio dashboard isn't available on this device. Use a
          different computer to access AuraFlow.
        </p>
        <Link href="/dashboard/check-in/kiosk" className="mt-6 block">
          <Button className="w-full">
            Open Check-In Kiosk
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </Link>
      </div>
      <Link
        href="/kiosk-unlock"
        className="mt-4 text-xs text-gray-400 hover:text-gray-600"
      >
        Owner: unlock this device
      </Link>
    </div>
  );
}
