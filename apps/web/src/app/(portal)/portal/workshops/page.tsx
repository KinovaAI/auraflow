"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Calendar,
  Clock,
  User,
  Loader2,
  MapPin,
  Video,
  Tag,
  Users,
  X,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { portalApi } from "@/lib/portal-api";
import type { PortalCourse, PortalEnrollment } from "@/lib/portal-api";
import { WorkshopDetailModal } from "@/components/portal/workshop-detail-modal";
import toast from "react-hot-toast";

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  workshop: { label: "Workshop", color: "bg-amber-50 text-amber-700" },
  course: { label: "Course", color: "bg-blue-50 text-blue-700" },
  teacher_training: { label: "Teacher Training", color: "bg-purple-50 text-purple-700" },
  retreat: { label: "Retreat", color: "bg-emerald-50 text-emerald-700" },
};

const ENROLLMENT_STATUS: Record<string, { color: string; label: string }> = {
  enrolled: { color: "bg-green-50 text-green-700", label: "Enrolled" },
  withdrawn: { color: "bg-gray-100 text-gray-500", label: "Withdrawn" },
  completed: { color: "bg-blue-50 text-blue-700", label: "Completed" },
};

function formatDate(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
}

type TypeFilter = "all" | "workshop" | "course" | "teacher_training" | "retreat";

function WorkshopsContent() {
  const searchParams = useSearchParams();
  const [courses, setCourses] = useState<PortalCourse[]>([]);
  const [enrollments, setEnrollments] = useState<PortalEnrollment[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [selectedCourse, setSelectedCourse] = useState<PortalCourse | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [coursesRes, enrollRes] = await Promise.all([
        portalApi.getWorkshops(typeFilter !== "all" ? { type: typeFilter } : undefined),
        portalApi.getMyEnrollments(),
      ]);
      setCourses(coursesRes.data);
      setEnrollments(enrollRes.data);
    } catch {
      toast.error("Failed to load workshops");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [typeFilter]);

  useEffect(() => {
    if (searchParams.get("enrolled") === "1") {
      toast.success("Successfully enrolled!");
      window.history.replaceState({}, "", "/portal/workshops");
    }
    if (searchParams.get("cancelled") === "1") {
      window.history.replaceState({}, "", "/portal/workshops");
    }
  }, [searchParams]);

  const handleWithdraw = async (enrollmentId: string) => {
    if (!confirm("Are you sure you want to withdraw from this workshop?")) return;
    try {
      await portalApi.withdrawEnrollment(enrollmentId);
      toast.success("Withdrawn successfully");
      loadData();
    } catch {
      toast.error("Failed to withdraw");
    }
  };

  const activeEnrollments = enrollments.filter((e) => e.status === "enrolled");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Workshops & Events</h1>
        <p className="mt-1 text-sm text-gray-500">
          Browse and enroll in workshops, courses, trainings, and retreats
        </p>
      </div>

      {/* Type Filter */}
      <div className="flex flex-wrap gap-2">
        {(["all", "workshop", "course", "teacher_training", "retreat"] as TypeFilter[]).map(
          (t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                typeFilter === t
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {t === "all"
                ? "All"
                : t === "teacher_training"
                ? "Teacher Training"
                : t.charAt(0).toUpperCase() + t.slice(1) + "s"}
            </button>
          ),
        )}
      </div>

      {/* My Enrollments */}
      {activeEnrollments.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold text-gray-900">My Enrollments</h2>
          <div className="space-y-3">
            {activeEnrollments.map((e) => {
              const status = ENROLLMENT_STATUS[e.status] || ENROLLMENT_STATUS.enrolled;
              const typeInfo = TYPE_LABELS[e.course_type || "workshop"];
              return (
                <Card key={e.id} className="transition-shadow hover:shadow-md">
                  <CardContent className="flex items-center justify-between p-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{e.course_title}</span>
                        {typeInfo && (
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${typeInfo.color}`}>
                            {typeInfo.label}
                          </span>
                        )}
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${status.color}`}>
                          {status.label}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-sm text-gray-500">
                        {e.instructor_name && (
                          <span className="flex items-center gap-1">
                            <User className="h-3.5 w-3.5" /> {e.instructor_name}
                          </span>
                        )}
                        {e.starts_at && (
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3.5 w-3.5" /> {formatDate(e.starts_at)}
                            {e.ends_at && ` – ${formatDate(e.ends_at)}`}
                          </span>
                        )}
                      </div>
                    </div>
                    {e.status === "enrolled" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:bg-red-50 hover:text-red-700"
                        onClick={() => handleWithdraw(e.id)}
                      >
                        Withdraw
                      </Button>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Available Workshops */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">Available</h2>
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
          </div>
        ) : courses.length === 0 ? (
          <div className="py-12 text-center">
            <Calendar className="mx-auto h-10 w-10 text-gray-300" />
            <p className="mt-3 text-sm text-gray-500">No workshops available right now</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {courses.map((course) => {
              const typeInfo = TYPE_LABELS[course.type] || TYPE_LABELS.workshop;
              const isEnrolled = enrollments.some(
                (e) => e.course_id === course.id && e.status === "enrolled",
              );
              return (
                <Card
                  key={course.id}
                  className="overflow-hidden transition-shadow hover:shadow-md"
                >
                  {/* Image / Placeholder */}
                  {course.image_url ? (
                    <img
                      src={course.image_url}
                      alt={course.title}
                      className="h-40 w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-32 items-center justify-center bg-gradient-to-br from-indigo-100 to-purple-100">
                      <Tag className="h-8 w-8 text-indigo-300" />
                    </div>
                  )}
                  <CardContent className="space-y-3 p-4">
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${typeInfo.color}`}>
                        {typeInfo.label}
                      </span>
                      {course.is_virtual && (
                        <span className="flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                          <Video className="h-3 w-3" /> Virtual
                        </span>
                      )}
                      {isEnrolled && (
                        <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                          Enrolled
                        </span>
                      )}
                    </div>

                    <div>
                      <h3 className="font-semibold text-gray-900">{course.title}</h3>
                      {course.description && (
                        <p className="mt-1 line-clamp-2 text-sm text-gray-500">
                          {course.description}
                        </p>
                      )}
                    </div>

                    <div className="space-y-1 text-sm text-gray-500">
                      {(course.guest_instructor_name || course.instructor_name) && (
                        <div className="flex items-center gap-1.5">
                          <User className="h-3.5 w-3.5" />
                          <span>
                            {course.guest_instructor_name || course.instructor_name}
                            {course.guest_instructor_name && (
                              <span className="ml-1.5 inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                                Guest
                              </span>
                            )}
                          </span>
                        </div>
                      )}
                      {course.starts_at && (
                        <div className="flex items-center gap-1.5">
                          <Calendar className="h-3.5 w-3.5" />
                          {formatDate(course.starts_at)}
                          {course.ends_at && ` – ${formatDate(course.ends_at)}`}
                        </div>
                      )}
                      {course.location && (
                        <div className="flex items-center gap-1.5">
                          <MapPin className="h-3.5 w-3.5" /> {course.location}
                        </div>
                      )}
                    </div>

                    {/* Price */}
                    <div className="flex items-center gap-2">
                      {course.is_early_bird_active && course.early_bird_price_cents != null ? (
                        <>
                          <span className="font-semibold text-green-600">
                            {formatPrice(course.early_bird_price_cents)}
                          </span>
                          <span className="text-sm text-gray-400 line-through">
                            {formatPrice(course.price_cents)}
                          </span>
                          <span className="rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-600">
                            Early Bird
                          </span>
                        </>
                      ) : course.price_cents > 0 ? (
                        <span className="font-semibold text-gray-900">
                          {formatPrice(course.price_cents)}
                        </span>
                      ) : (
                        <span className="font-semibold text-green-600">Free</span>
                      )}
                    </div>

                    {/* Spots */}
                    {course.spots_remaining !== null && course.spots_remaining !== undefined && (
                      <div className="flex items-center gap-1.5 text-sm">
                        <Users className="h-3.5 w-3.5 text-gray-400" />
                        {course.spots_remaining > 0 ? (
                          <span className="text-gray-500">
                            {course.spots_remaining} spot{course.spots_remaining !== 1 ? "s" : ""} remaining
                          </span>
                        ) : (
                          <span className="font-medium text-red-600">Full</span>
                        )}
                      </div>
                    )}

                    <Button
                      className="w-full"
                      onClick={() => setSelectedCourse(course)}
                      disabled={isEnrolled}
                    >
                      {isEnrolled ? "Already Enrolled" : "View Details"}
                      {!isEnrolled && <ArrowRight className="ml-1.5 h-4 w-4" />}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedCourse && (
        <WorkshopDetailModal
          course={selectedCourse}
          onClose={() => setSelectedCourse(null)}
          onEnrolled={() => {
            setSelectedCourse(null);
            loadData();
          }}
        />
      )}
    </div>
  );
}

export default function WorkshopsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
        </div>
      }
    >
      <WorkshopsContent />
    </Suspense>
  );
}
