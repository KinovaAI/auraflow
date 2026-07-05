"use client";

import { useEffect, useState } from "react";
import {
  User,
  Loader2,
  Clock,
  Video,
  X,
  ChevronLeft,
  DollarSign,
  ArrowRight,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { portalApi } from "@/lib/portal-api";
import type {
  PortalInstructor,
  PortalPrivateService,
  PortalTimeSlot,
} from "@/lib/portal-api";
import { SlotPicker } from "@/components/portal/slot-picker";
import toast from "react-hot-toast";

interface InstructorDetailModalProps {
  instructor: PortalInstructor;
  onClose: () => void;
  onBooked: () => void;
}

type Step = "services" | "slots" | "confirm";

function formatPrice(cents: number): string {
  return `$${(cents / 100).toFixed(cents % 100 === 0 ? 0 : 2)}`;
}

function formatSlotTime(timeStr: string): string {
  const [h, m] = timeStr.split(":");
  const hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  return `${displayHour}:${m} ${ampm}`;
}

export function InstructorDetailModal({
  instructor,
  onClose,
  onBooked,
}: InstructorDetailModalProps) {
  const [step, setStep] = useState<Step>("services");
  const [services, setServices] = useState<PortalPrivateService[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedService, setSelectedService] = useState<PortalPrivateService | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<PortalTimeSlot | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [intakeNotes, setIntakeNotes] = useState("");
  const [booking, setBooking] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await portalApi.getInstructorServices(instructor.id);
        setServices(res.data);
      } catch {
        toast.error("Failed to load services");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [instructor.id]);

  const handleServiceSelect = (service: PortalPrivateService) => {
    setSelectedService(service);
    setStep("slots");
  };

  const handleSlotSelected = (slot: PortalTimeSlot, dateStr: string) => {
    setSelectedSlot(slot);
    setSelectedDate(dateStr);
    setStep("confirm");
  };

  const handleBook = async () => {
    if (!selectedService || !selectedSlot || !selectedDate) return;
    setBooking(true);

    // Build ISO datetime from date + slot start_time
    const startsAt = `${selectedDate}T${selectedSlot.start_time}`;

    try {
      const res = await portalApi.bookPrivateSession({
        instructor_id: instructor.id,
        private_service_id: selectedService.id,
        starts_at: startsAt,
        intake_notes: intakeNotes || undefined,
        success_url: `${window.location.origin}/portal/private-lessons?booked=1`,
        cancel_url: `${window.location.origin}/portal/private-lessons?cancelled=1`,
      });
      const resData = (res as { data?: { data?: Record<string, unknown> } }).data?.data || (res as { data?: Record<string, unknown> }).data || res;
      const data = resData as { booked?: boolean; url?: string };
      if (data.booked) {
        toast.success("Session booked!");
        onBooked();
      } else if (data.url) {
        window.location.href = data.url;
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Booking failed");
    } finally {
      setBooking(false);
    }
  };

  const goBack = () => {
    if (step === "confirm") {
      setStep("slots");
      setSelectedSlot(null);
      setSelectedDate("");
    } else if (step === "slots") {
      setStep("services");
      setSelectedService(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between border-b bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            {step !== "services" && (
              <button
                onClick={goBack}
                className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <ChevronLeft className="h-5 w-5" />
              </button>
            )}
            <div className="flex items-center gap-2">
              {instructor.photo_url ? (
                <img
                  src={instructor.photo_url}
                  alt={instructor.display_name}
                  className="h-8 w-8 rounded-full object-cover"
                />
              ) : (
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-sm font-medium text-indigo-600">
                  {instructor.display_name[0]}
                </div>
              )}
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {instructor.display_name}
                </h2>
                <p className="text-xs text-gray-400">
                  {step === "services"
                    ? "Select a service"
                    : step === "slots"
                    ? `${selectedService?.name} – Pick a time`
                    : "Confirm booking"}
                </p>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4">
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
            </div>
          ) : step === "services" ? (
            /* Step 1: Select Service */
            <div className="space-y-3">
              {services.length === 0 ? (
                <p className="py-8 text-center text-sm text-gray-400">
                  No services available
                </p>
              ) : (
                services.map((svc) => (
                  <button
                    key={svc.id}
                    onClick={() => handleServiceSelect(svc)}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-200 p-4 text-left transition-colors hover:border-indigo-300 hover:bg-indigo-50/50"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{svc.name}</span>
                        {svc.is_virtual && (
                          <span className="flex items-center gap-1 rounded-full bg-purple-50 px-2 py-0.5 text-xs text-purple-700">
                            <Video className="h-3 w-3" /> Virtual
                          </span>
                        )}
                      </div>
                      {svc.description && (
                        <p className="text-sm text-gray-500">{svc.description}</p>
                      )}
                      <div className="flex items-center gap-3 text-sm text-gray-400">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3.5 w-3.5" /> {svc.duration_minutes} min
                        </span>
                        <span className="font-medium text-gray-700">
                          {svc.price_cents > 0 ? formatPrice(svc.price_cents) : "Free"}
                        </span>
                      </div>
                    </div>
                    <ArrowRight className="h-5 w-5 text-gray-300" />
                  </button>
                ))
              )}
            </div>
          ) : step === "slots" && selectedService ? (
            /* Step 2: Select Date & Time */
            <SlotPicker
              instructorId={instructor.id}
              serviceId={selectedService.id}
              onSlotSelected={handleSlotSelected}
            />
          ) : step === "confirm" && selectedService && selectedSlot ? (
            /* Step 3: Confirm & Book */
            <div className="space-y-4">
              <div className="rounded-lg bg-gray-50 p-4">
                <h3 className="mb-3 text-sm font-medium text-gray-900">Booking Summary</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Instructor</span>
                    <span className="font-medium text-gray-900">{instructor.display_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Service</span>
                    <span className="font-medium text-gray-900">{selectedService.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Date</span>
                    <span className="font-medium text-gray-900">
                      {new Date(selectedDate + "T00:00").toLocaleDateString("en-US", {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Time</span>
                    <span className="font-medium text-gray-900">
                      {formatSlotTime(selectedSlot.start_time)} –{" "}
                      {formatSlotTime(selectedSlot.end_time)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Duration</span>
                    <span className="font-medium text-gray-900">
                      {selectedService.duration_minutes} min
                    </span>
                  </div>
                  <div className="flex justify-between border-t pt-2">
                    <span className="font-medium text-gray-700">Total</span>
                    <span className="font-semibold text-gray-900">
                      {selectedService.price_cents > 0
                        ? formatPrice(selectedService.price_cents)
                        : "Free"}
                    </span>
                  </div>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Notes for instructor (optional)
                </label>
                <textarea
                  value={intakeNotes}
                  onChange={(e) => setIntakeNotes(e.target.value)}
                  rows={3}
                  className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-1 focus:ring-indigo-300"
                  placeholder="Any goals, injuries, or preferences to share..."
                />
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        {step === "confirm" && selectedService && (
          <div className="sticky bottom-0 flex items-center justify-end gap-3 border-t bg-white px-6 py-4">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleBook} disabled={booking}>
              {booking ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : selectedService.price_cents > 0 ? (
                `Book Now – ${formatPrice(selectedService.price_cents)}`
              ) : (
                "Book for Free"
              )}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
