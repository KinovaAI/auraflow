"use client";

import { useState, useRef, useEffect } from "react";
import { MapPin, ChevronDown, Check } from "lucide-react";
import { useStudioStore } from "@/stores/studio-store";

export function LocationSwitcher() {
  const { studios, activeStudioId, switchStudio } = useStudioStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const activeStudio = studios.find((s) => s.studio_id === activeStudioId);
  const studioName = activeStudio?.studio_name ?? "All Locations";

  // Single studio — just show the name
  if (studios.length <= 1) {
    return (
      <div className="flex items-center gap-1.5 text-sm font-medium text-gray-700">
        <MapPin className="h-3.5 w-3.5 text-gray-400" />
        <span>{studioName}</span>
      </div>
    );
  }

  // Multiple studios — show dropdown
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors"
      >
        <MapPin className="h-3.5 w-3.5 text-gray-400" />
        <span>{studioName}</span>
        <ChevronDown className={`h-3.5 w-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-md border border-gray-200 bg-white py-1 shadow-lg">
          {studios.map((studio) => (
            <button
              key={studio.studio_id}
              onClick={() => {
                switchStudio(studio.studio_id);
                setOpen(false);
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-50"
            >
              <div>
                <div className="font-medium text-gray-900">{studio.studio_name}</div>
                <div className="text-xs text-gray-500 capitalize">{studio.role}</div>
              </div>
              {studio.studio_id === activeStudioId && (
                <Check className="h-4 w-4 text-indigo-600" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
