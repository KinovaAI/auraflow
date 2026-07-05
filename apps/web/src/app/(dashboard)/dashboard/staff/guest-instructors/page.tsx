"use client";

import { useState } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Plus, Pencil, Archive, UserPlus, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import {
  guestInstructorsApi,
  type GuestInstructor,
} from "@/lib/guest-instructors-api";
import { GuestInstructorFormModal } from "@/components/staff/guest-instructor-form-modal";
import { useStudioStore } from "@/stores/studio-store";

export default function GuestInstructorsPage() {
  const queryClient = useQueryClient();
  const studioId = useStudioStore((s) => s.activeStudioId) || undefined;
  const [editingGuest, setEditingGuest] = useState<GuestInstructor | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  const { data: guests, isLoading } = useQuery({
    queryKey: ["guest-instructors", { active: !showInactive, studioId }],
    queryFn: () =>
      guestInstructorsApi
        .list({ active_only: !showInactive, studio_id: studioId })
        .then((r) => r.data),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => guestInstructorsApi.archive(id),
    onSuccess: () => {
      toast.success("Guest archived");
      queryClient.invalidateQueries({ queryKey: ["guest-instructors"] });
    },
    onError: () => toast.error("Failed to archive guest"),
  });

  const onSaved = () => {
    queryClient.invalidateQueries({ queryKey: ["guest-instructors"] });
    setEditingGuest(null);
    setShowCreate(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Guest Instructors</h1>
          <p className="mt-1 text-sm text-gray-500">
            1099 contractors who teach workshops only. They never appear in your
            staff instructor list.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-1.5 h-4 w-4" />
          Add Guest
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          Include archived
        </label>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      ) : !guests || guests.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 px-6 py-16 text-center">
          <UserPlus className="mx-auto h-10 w-10 text-gray-400" />
          <p className="mt-3 text-sm font-medium text-gray-900">
            No guest instructors yet
          </p>
          <p className="mt-1 text-sm text-gray-500">
            Add one when you book a guest to teach a workshop.
          </p>
          <Button className="mt-4" onClick={() => setShowCreate(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            Add Guest Instructor
          </Button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Name
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Email
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Phone
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Pay split (guest / studio)
                </th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-600">
                  Status
                </th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {guests.map((g) => {
                const studioPct = 100 - g.revenue_share_percent_to_guest;
                return (
                  <tr key={g.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        {g.photo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={g.photo_url}
                            alt=""
                            className="h-8 w-8 rounded-full object-cover"
                          />
                        ) : (
                          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-xs font-medium text-indigo-700">
                            {g.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                          </div>
                        )}
                        <div>
                          <p className="text-sm font-medium text-gray-900">{g.name}</p>
                          {g.bio && (
                            <p className="text-xs text-gray-500 line-clamp-1 max-w-md">
                              {g.bio}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {g.email || "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {g.phone || "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {g.revenue_share_percent_to_guest}% / {studioPct}%
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                          g.is_active
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {g.is_active ? "Active" : "Archived"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8"
                          onClick={() => setEditingGuest(g)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        {g.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 text-gray-500 hover:text-red-600"
                            onClick={() => {
                              if (confirm(`Archive ${g.name}? Their tax history stays on past workshops.`)) {
                                archiveMutation.mutate(g.id);
                              }
                            }}
                          >
                            <Archive className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <GuestInstructorFormModal
          studioId={studioId}
          onClose={() => setShowCreate(false)}
          onSaved={onSaved}
        />
      )}
      {editingGuest && (
        <GuestInstructorFormModal
          guest={editingGuest}
          studioId={studioId}
          onClose={() => setEditingGuest(null)}
          onSaved={onSaved}
        />
      )}
    </div>
  );
}
