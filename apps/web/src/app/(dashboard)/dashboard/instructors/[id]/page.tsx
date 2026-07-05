"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { format, startOfWeek, endOfWeek } from "date-fns";
import {
  ArrowLeft,
  Loader2,
  Mail,
  Phone,
  DollarSign,
  Clock,
  Edit2,
  Trash2,
} from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { InstructorFormModal } from "@/components/instructors/instructor-form-modal";
import { AvailabilityEditor } from "@/components/instructors/availability-editor";
import { instructorsApi, type Instructor } from "@/lib/instructors-api";

const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export default function InstructorDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showEditForm, setShowEditForm] = useState(false);
  const [showAvailability, setShowAvailability] = useState(false);

  const { data: instructor, isLoading } = useQuery({
    queryKey: ["instructor", id],
    queryFn: () => instructorsApi.get(id).then((r) => r.data),
  });

  const { data: availability } = useQuery({
    queryKey: ["instructor-availability", id],
    queryFn: () => instructorsApi.getAvailability(id).then((r) => r.data),
  });

  const now = new Date();
  const weekStart = startOfWeek(now, { weekStartsOn: 0 });
  const weekEnd = endOfWeek(now, { weekStartsOn: 0 });

  const { data: schedule } = useQuery({
    queryKey: ["instructor-schedule", id],
    queryFn: () =>
      instructorsApi
        .getSchedule(
          id,
          format(weekStart, "yyyy-MM-dd"),
          format(weekEnd, "yyyy-MM-dd")
        )
        .then((r) => r.data as Array<{ id: string; title: string; starts_at: string; ends_at: string }>),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => instructorsApi.deactivate(id),
    onSuccess: () => {
      toast.success("Instructor deactivated");
      router.push("/dashboard/instructors");
    },
    onError: () => toast.error("Failed to deactivate"),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!instructor) {
    return (
      <div className="py-20 text-center text-gray-500">
        Instructor not found
      </div>
    );
  }

  const payLabel =
    instructor.pay_type === "per_class"
      ? "per class"
      : instructor.pay_type === "hourly"
        ? "per hour"
        : instructor.pay_type || "";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/dashboard/instructors")}
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back
        </Button>
      </div>

      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div
            className="flex h-14 w-14 items-center justify-center rounded-full text-lg font-semibold text-white"
            style={{ backgroundColor: instructor.color || "#6366F1" }}
          >
            {instructor.display_name
              .split(" ")
              .map((n) => n[0])
              .join("")
              .toUpperCase()
              .slice(0, 2)}
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {instructor.display_name}
            </h1>
            {instructor.bio && (
              <p className="mt-1 text-sm text-gray-500">{instructor.bio}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowEditForm(true)}
          >
            <Edit2 className="mr-1 h-4 w-4" />
            Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-red-600 hover:bg-red-50"
            onClick={() => {
              if (confirm("Deactivate this instructor?")) {
                deactivateMutation.mutate();
              }
            }}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Deactivate
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Contact & Pay</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {instructor.email && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Mail className="h-4 w-4 text-gray-400" />
                {instructor.email}
              </div>
            )}
            {instructor.phone && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Phone className="h-4 w-4 text-gray-400" />
                {instructor.phone}
              </div>
            )}
            {instructor.pay_rate_cents != null && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <DollarSign className="h-4 w-4 text-gray-400" />$
                {(instructor.pay_rate_cents / 100).toFixed(2)} {payLabel}
              </div>
            )}
            {instructor.tax_classification && (
              <div className="text-xs text-gray-400">
                Tax: {instructor.tax_classification}
              </div>
            )}
            <div className="grid grid-cols-3 gap-2 pt-2 text-xs text-gray-500">
              <div>Workshop: {instructor.workshop_pay_percent ?? 60}%</div>
              <div>Private: {instructor.private_session_pay_percent ?? 70}%</div>
              <div>Training: {instructor.training_pay_percent ?? 50}%</div>
            </div>
            {instructor.specialties?.length ? (
              <div className="flex flex-wrap gap-1 pt-2">
                {instructor.specialties.map((s) => (
                  <span
                    key={s}
                    className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
                  >
                    {s}
                  </span>
                ))}
              </div>
            ) : null}
            {instructor.certifications?.length ? (
              <div className="flex flex-wrap gap-1">
                {instructor.certifications.map((c) => (
                  <span
                    key={c}
                    className="rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-700"
                  >
                    {c}
                  </span>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Availability Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Availability</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAvailability(true)}
            >
              Edit
            </Button>
          </CardHeader>
          <CardContent>
            {!availability?.length ? (
              <p className="text-sm text-gray-400">No availability set</p>
            ) : (
              <div className="space-y-2">
                {availability.map((slot, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-sm">
                    <Clock className="h-3.5 w-3.5 text-gray-400" />
                    <span className="font-medium text-gray-700">
                      {DAY_NAMES[slot.day_of_week]}
                    </span>
                    <span className="text-gray-500">
                      {slot.start_time} - {slot.end_time}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Schedule Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">This Week</CardTitle>
          </CardHeader>
          <CardContent>
            {!schedule?.length ? (
              <p className="text-sm text-gray-400">No classes this week</p>
            ) : (
              <div className="space-y-2">
                {schedule.slice(0, 10).map((s) => (
                  <div key={s.id} className="text-sm">
                    <p className="font-medium text-gray-700">{s.title}</p>
                    <p className="text-xs text-gray-500">
                      {format(new Date(s.starts_at), "EEE, MMM d h:mm a")}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Edit Form Modal */}
      {showEditForm && (
        <InstructorFormModal
          instructor={instructor}
          onClose={() => setShowEditForm(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["instructor", id] });
            setShowEditForm(false);
            toast.success("Instructor updated");
          }}
        />
      )}

      {/* Availability Editor Modal */}
      {showAvailability && (
        <AvailabilityEditor
          instructorId={id}
          currentSlots={availability || []}
          onClose={() => setShowAvailability(false)}
          onSaved={() => {
            queryClient.invalidateQueries({
              queryKey: ["instructor-availability", id],
            });
            setShowAvailability(false);
            toast.success("Availability updated");
          }}
        />
      )}
    </div>
  );
}
