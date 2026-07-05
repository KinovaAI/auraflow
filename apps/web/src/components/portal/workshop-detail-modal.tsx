"use client";

import { useEffect, useState } from "react";
import {
  Calendar,
  Clock,
  User,
  Loader2,
  MapPin,
  Video,
  X,
  Tag,
  Hash,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { portalApi } from "@/lib/portal-api";
import type { PortalCourse, PortalCourseDetail } from "@/lib/portal-api";
import toast from "react-hot-toast";

interface WorkshopDetailModalProps {
  course: PortalCourse;
  onClose: () => void;
  onEnrolled: () => void;
}

function formatDate(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatTime(iso?: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
}

export function WorkshopDetailModal({ course, onClose, onEnrolled }: WorkshopDetailModalProps) {
  const [detail, setDetail] = useState<PortalCourseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [enrolling, setEnrolling] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await portalApi.getWorkshopDetail(course.id);
        // Axios response: res.data is the API response body
        const data = (res as any).data || res;
        setDetail(data as PortalCourseDetail);
      } catch (err) {
        console.error("Workshop detail error:", err);
        toast.error("Failed to load workshop details");
        onClose();
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [course.id]);

  const effectivePrice =
    course.is_early_bird_active && course.early_bird_price_cents != null
      ? course.early_bird_price_cents
      : course.price_cents;

  const handleEnroll = async () => {
    setEnrolling(true);
    try {
      const res = await portalApi.enrollInWorkshop(course.id, {
        success_url: `${window.location.origin}/portal/workshops?enrolled=1`,
        cancel_url: `${window.location.origin}/portal/workshops?cancelled=1`,
      });
      const resData = (res as { data?: { data?: Record<string, unknown> } }).data?.data || (res as { data?: Record<string, unknown> }).data || res;
      const data = resData as { enrolled?: boolean; url?: string };
      if (data.enrolled) {
        toast.success("Successfully enrolled!");
        onEnrolled();
      } else if (data.url) {
        window.location.href = data.url;
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Enrollment failed");
    } finally {
      setEnrolling(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between border-b bg-white px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">{course.title}</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 px-6 py-4">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : (
            <>
              {/* Meta */}
              <div className="space-y-2 text-sm text-gray-600">
                {(course.guest_instructor_name || course.instructor_name) && (
                  <div className="flex items-center gap-2">
                    <User className="h-4 w-4 text-gray-400" />
                    <span>
                      {course.guest_instructor_name || course.instructor_name}
                      {course.guest_instructor_name && (
                        <span className="ml-1.5 inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                          Guest Instructor
                        </span>
                      )}
                    </span>
                  </div>
                )}
                {course.starts_at && (
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-gray-400" />
                    {formatDate(course.starts_at)}
                    {course.ends_at && ` – ${formatDate(course.ends_at)}`}
                  </div>
                )}
                {course.location && (
                  <div className="flex items-center gap-2">
                    {course.is_virtual ? (
                      <Video className="h-4 w-4 text-purple-500" />
                    ) : (
                      <MapPin className="h-4 w-4 text-gray-400" />
                    )}
                    {course.is_virtual ? "Virtual (Online)" : course.location}
                  </div>
                )}
              </div>

              {/* Description */}
              {course.description && (
                <div>
                  <h3 className="mb-1 text-sm font-medium text-gray-900">About</h3>
                  <p className="text-sm leading-relaxed text-gray-600">{course.description}</p>
                </div>
              )}

              {/* Guest instructor spotlight (workshops only) */}
              {course.guest_instructor_name && (course.guest_instructor_bio || course.guest_instructor_photo_url) && (
                <div className="rounded-md border border-amber-200 bg-amber-50/40 p-3">
                  <h3 className="mb-2 text-sm font-medium text-amber-900">
                    About the Guest Instructor
                  </h3>
                  <div className="flex gap-3">
                    {course.guest_instructor_photo_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={course.guest_instructor_photo_url}
                        alt={course.guest_instructor_name}
                        className="h-16 w-16 rounded-full object-cover shrink-0"
                      />
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-900">
                        {course.guest_instructor_name}
                      </p>
                      {course.guest_instructor_bio && (
                        <p className="mt-1 text-sm leading-relaxed text-gray-700">
                          {course.guest_instructor_bio}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Prerequisites */}
              {course.prerequisites && (
                <div>
                  <h3 className="mb-1 text-sm font-medium text-gray-900">Prerequisites</h3>
                  <p className="text-sm text-gray-600">{course.prerequisites}</p>
                </div>
              )}

              {/* Session Schedule */}
              {detail?.sessions && detail.sessions.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-medium text-gray-900">
                    Session Schedule ({detail.sessions.length} session
                    {detail.sessions.length !== 1 ? "s" : ""})
                  </h3>
                  <div className="space-y-2">
                    {detail.sessions.map((s) => (
                      <div
                        key={s.id}
                        className="flex items-center gap-3 rounded-md bg-gray-50 px-3 py-2 text-sm"
                      >
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-xs font-medium text-indigo-700">
                          {s.session_number}
                        </span>
                        <div className="flex-1">
                          {s.title && (
                            <span className="font-medium text-gray-900">{s.title}</span>
                          )}
                          <div className="flex items-center gap-3 text-gray-500">
                            {s.starts_at && (
                              <span>
                                {formatDate(s.starts_at)} {formatTime(s.starts_at)}
                                {s.ends_at && ` – ${formatTime(s.ends_at)}`}
                              </span>
                            )}
                            {s.is_virtual && (
                              <span className="flex items-center gap-1 text-purple-600">
                                <Video className="h-3 w-3" /> Virtual
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Pricing */}
              <div className="rounded-md bg-gray-50 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    {course.is_early_bird_active && course.early_bird_price_cents != null ? (
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-lg font-bold text-green-600">
                            {formatPrice(course.early_bird_price_cents)}
                          </span>
                          <span className="text-sm text-gray-400 line-through">
                            {formatPrice(course.price_cents)}
                          </span>
                        </div>
                        {course.early_bird_deadline && (
                          <p className="text-xs text-green-600">
                            Early bird price until {formatDate(course.early_bird_deadline)}
                          </p>
                        )}
                      </div>
                    ) : effectivePrice > 0 ? (
                      <span className="text-lg font-bold text-gray-900">
                        {formatPrice(effectivePrice)}
                      </span>
                    ) : (
                      <span className="text-lg font-bold text-green-600">Free</span>
                    )}
                  </div>
                  {course.spots_remaining !== null &&
                    course.spots_remaining !== undefined && (
                      <span className="text-sm text-gray-500">
                        {course.spots_remaining > 0
                          ? `${course.spots_remaining} spots left`
                          : "Full"}
                      </span>
                    )}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t bg-white px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleEnroll}
            disabled={
              enrolling ||
              loading ||
              (course.spots_remaining !== null &&
                course.spots_remaining !== undefined &&
                course.spots_remaining <= 0)
            }
          >
            {enrolling ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Processing...
              </>
            ) : effectivePrice > 0 ? (
              `Enroll Now – ${formatPrice(effectivePrice)}`
            ) : (
              "Enroll for Free"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
