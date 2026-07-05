"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StaffMember } from "@/types/staff";

const ROLE_BADGES: Record<string, { label: string; className: string }> = {
  owner: {
    label: "Owner",
    className: "bg-purple-100 text-purple-800",
  },
  admin: {
    label: "Admin",
    className: "bg-blue-100 text-blue-800",
  },
  instructor: {
    label: "Instructor",
    className: "bg-green-100 text-green-800",
  },
  front_desk: {
    label: "Front Desk",
    className: "bg-yellow-100 text-yellow-800",
  },
};

interface Props {
  staff: StaffMember[];
}

export function StaffTable({ staff }: Props) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Email
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Role
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Title
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Department
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Status
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              Permissions
            </th>
            <th className="relative px-6 py-3">
              <span className="sr-only">View</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {staff.map((member) => {
            const badge = ROLE_BADGES[member.role];
            const name =
              [member.first_name, member.last_name]
                .filter(Boolean)
                .join(" ") || "—";

            return (
              <tr key={member.user_id} className="hover:bg-gray-50">
                <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                  {name}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                  {member.email}
                </td>
                <td className="whitespace-nowrap px-6 py-4">
                  {badge && (
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium",
                        badge.className
                      )}
                    >
                      {badge.label}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                  {member.title || "—"}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                  {member.department || "—"}
                </td>
                <td className="whitespace-nowrap px-6 py-4">
                  <span
                    className={cn(
                      "inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium",
                      member.is_active
                        ? "bg-green-100 text-green-800"
                        : "bg-red-100 text-red-800"
                    )}
                  >
                    {member.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                  {member.permissions.length} / 20
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-right text-sm">
                  <Link
                    href={`/dashboard/staff/${member.user_id}`}
                    className="inline-flex items-center text-indigo-600 hover:text-indigo-900"
                  >
                    Manage
                    <ChevronRight className="ml-1 h-4 w-4" />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
