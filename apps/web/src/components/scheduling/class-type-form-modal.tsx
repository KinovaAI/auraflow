"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { X, Loader2 } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { classTypesApi } from "@/lib/scheduling-api";

interface ClassTypeFormModalProps {
  studioId: string;
  onClose: () => void;
  onCreated: () => void;
}

const COLORS = [
  "#4F46E5", "#7C3AED", "#EC4899", "#EF4444",
  "#F59E0B", "#10B981", "#06B6D4", "#6366F1",
];

export function ClassTypeFormModal({
  studioId,
  onClose,
  onCreated,
}: ClassTypeFormModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [capacity, setCapacity] = useState(20);
  const [color, setColor] = useState("#4F46E5");
  const [level, setLevel] = useState("all_levels");

  const createMutation = useMutation({
    mutationFn: () =>
      classTypesApi.create({
        studio_id: studioId,
        name: name.trim(),
        description: description.trim() || undefined,
        duration_minutes: durationMinutes,
        capacity,
        color,
        level,
      }),
    onSuccess: () => {
      toast.success("Class type created");
      onCreated();
    },
    onError: () => toast.error("Failed to create class type"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Create Class Type
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 px-6 py-4">
          <div>
            <Label htmlFor="ctName">Name *</Label>
            <Input
              id="ctName"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Vinyasa Flow"
            />
          </div>

          <div>
            <Label htmlFor="ctDesc">Description</Label>
            <textarea
              id="ctDesc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="flex w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Describe this class type..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="ctDuration">Duration (min)</Label>
              <Input
                id="ctDuration"
                type="number"
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(Number(e.target.value))}
                min={15}
                max={240}
              />
            </div>
            <div>
              <Label htmlFor="ctCapacity">Default Capacity</Label>
              <Input
                id="ctCapacity"
                type="number"
                value={capacity}
                onChange={(e) => setCapacity(Number(e.target.value))}
                min={1}
              />
            </div>
          </div>

          <div>
            <Label htmlFor="ctLevel">Level</Label>
            <select
              id="ctLevel"
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="all_levels">All Levels</option>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </div>

          <div>
            <Label>Color</Label>
            <div className="mt-1 flex gap-2">
              {COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`h-8 w-8 rounded-full border-2 transition-all ${
                    color === c
                      ? "border-gray-900 scale-110"
                      : "border-transparent hover:border-gray-300"
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Create Class Type
          </Button>
        </div>
      </div>
    </div>
  );
}
