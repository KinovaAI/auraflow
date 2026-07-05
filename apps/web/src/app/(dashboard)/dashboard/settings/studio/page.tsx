"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Trash2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { studiosApi, roomsApi, type Studio, type Room } from "@/lib/scheduling-api";

export default function StudioSettingsPage() {
  const queryClient = useQueryClient();
  const [studioId, setStudioId] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [cancelHours, setCancelHours] = useState<number | "">("");
  const [bookingDays, setBookingDays] = useState<number | "">("");
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomCapacity, setNewRoomCapacity] = useState<number | "">("");

  const { data: studios, isLoading } = useQuery({
    queryKey: ["studios"],
    queryFn: () => studiosApi.list().then((r) => r.data),
  });

  const studio = studios?.find((s) => s.id === studioId) || studios?.[0];

  useEffect(() => {
    if (studio) {
      setStudioId(studio.id);
      setName(studio.name);
      setCity(studio.city || "");
      setState(studio.state || "");
      setPhone(studio.phone || "");
      setEmail(studio.email || "");
      setCancelHours(studio.cancellation_policy_hours ?? "");
      setBookingDays(studio.booking_window_days ?? "");
    }
  }, [studio?.id]);

  const { data: rooms } = useQuery({
    queryKey: ["rooms", studioId],
    queryFn: () => roomsApi.list(studioId!).then((r) => r.data),
    enabled: !!studioId,
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      studiosApi.update(studioId!, {
        name,
        city: city || undefined,
        state: state || undefined,
        phone: phone || undefined,
        email: email || undefined,
        cancellation_policy_hours: cancelHours || undefined,
        booking_window_days: bookingDays || undefined,
      }),
    onSuccess: () => {
      toast.success("Studio settings saved");
      queryClient.invalidateQueries({ queryKey: ["studios"] });
    },
    onError: () => toast.error("Failed to save"),
  });

  const addRoomMutation = useMutation({
    mutationFn: () =>
      roomsApi.create(studioId!, {
        name: newRoomName.trim(),
        capacity: newRoomCapacity || undefined,
      }),
    onSuccess: () => {
      toast.success("Room added");
      setNewRoomName("");
      setNewRoomCapacity("");
      queryClient.invalidateQueries({ queryKey: ["rooms", studioId] });
    },
    onError: () => toast.error("Failed to add room"),
  });

  const deleteRoomMutation = useMutation({
    mutationFn: (roomId: string) => roomsApi.delete(studioId!, roomId),
    onSuccess: () => {
      toast.success("Room removed");
      queryClient.invalidateQueries({ queryKey: ["rooms", studioId] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (!studio) {
    return (
      <div className="py-20 text-center text-gray-500">No studio found</div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Studio Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">General Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="studioName">Studio Name</Label>
            <Input
              id="studioName"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="city">City</Label>
              <Input
                id="city"
                value={city}
                onChange={(e) => setCity(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="state">State</Label>
              <Input
                id="state"
                value={state}
                onChange={(e) => setState(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="studioPhone">Phone</Label>
              <Input
                id="studioPhone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="studioEmail">Email</Label>
              <Input
                id="studioEmail"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Policies */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Booking Policies</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="cancelHours">
                Cancellation Policy (hours before)
              </Label>
              <Input
                id="cancelHours"
                type="number"
                value={cancelHours}
                onChange={(e) =>
                  setCancelHours(e.target.value ? Number(e.target.value) : "")
                }
                placeholder="e.g. 12"
              />
            </div>
            <div>
              <Label htmlFor="bookingDays">
                Booking Window (days in advance)
              </Label>
              <Input
                id="bookingDays"
                type="number"
                value={bookingDays}
                onChange={(e) =>
                  setBookingDays(e.target.value ? Number(e.target.value) : "")
                }
                placeholder="e.g. 14"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Button
        onClick={() => updateMutation.mutate()}
        disabled={!name.trim() || updateMutation.isPending}
      >
        {updateMutation.isPending && (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        )}
        Save Settings
      </Button>

      {/* Rooms */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Rooms</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {rooms?.map((room) => (
            <div
              key={room.id}
              className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2"
            >
              <div>
                <span className="text-sm font-medium text-gray-900">
                  {room.name}
                </span>
                {room.capacity && (
                  <span className="ml-2 text-xs text-gray-500">
                    (cap: {room.capacity})
                  </span>
                )}
              </div>
              <button
                onClick={() => {
                  if (confirm(`Delete room "${room.name}"?`)) {
                    deleteRoomMutation.mutate(room.id);
                  }
                }}
                className="rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}

          <div className="flex items-end gap-2 pt-2">
            <div className="flex-1">
              <Label htmlFor="newRoom">Add Room</Label>
              <Input
                id="newRoom"
                value={newRoomName}
                onChange={(e) => setNewRoomName(e.target.value)}
                placeholder="Room name"
              />
            </div>
            <div className="w-24">
              <Label htmlFor="newRoomCap">Capacity</Label>
              <Input
                id="newRoomCap"
                type="number"
                value={newRoomCapacity}
                onChange={(e) =>
                  setNewRoomCapacity(
                    e.target.value ? Number(e.target.value) : ""
                  )
                }
              />
            </div>
            <Button
              variant="outline"
              onClick={() => addRoomMutation.mutate()}
              disabled={!newRoomName.trim() || addRoomMutation.isPending}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
