"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { label: "Studio", href: "/dashboard/settings/studio" },
  { label: "Locations", href: "/dashboard/settings/locations" },
  { label: "Email Inbox", href: "/dashboard/settings/email-inbox" },
  { label: "Integrations", href: "/dashboard/settings/integrations" },
  { label: "Import", href: "/dashboard/settings/import" },
  { label: "Billing", href: "/dashboard/settings/billing" },
  { label: "Square POS", href: "/dashboard/settings/square-pos" },
  { label: "Waivers", href: "/dashboard/settings/waivers" },
  { label: "Webhooks", href: "/dashboard/settings/webhooks" },
  { label: "Portal Setup", href: "/dashboard/settings/portal-setup" },
  { label: "Kiosk Devices", href: "/dashboard/settings/kiosk-device" },
  { label: "Audit Log", href: "/dashboard/settings/audit-log" },
  { label: "Account", href: "/dashboard/settings/account" },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500">
          Manage your studio configuration
        </p>
      </div>

      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6">
          {tabs.map((tab) => {
            const active = pathname === tab.href || pathname.startsWith(tab.href + "/");
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`border-b-2 pb-3 text-sm font-medium ${
                  active
                    ? "border-indigo-600 text-indigo-600"
                    : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {children}
    </div>
  );
}
