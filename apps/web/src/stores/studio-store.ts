import { create } from "zustand";
import type { UserStudioRole } from "@/types/auth";

interface StudioState {
  studios: UserStudioRole[];
  activeStudioId: string | null;
  activeStudioRole: string | null;
  setStudios: (studios: UserStudioRole[]) => void;
  switchStudio: (studioId: string) => void;
  getEffectivePermissions: (orgPermissions: string[]) => string[];
}

export const useStudioStore = create<StudioState>((set, get) => ({
  studios: [],
  activeStudioId: null,
  activeStudioRole: null,

  setStudios: (studios) => {
    if (!studios.length) {
      set({ studios, activeStudioId: null, activeStudioRole: null });
      return;
    }

    // Try to restore from localStorage
    const saved = typeof window !== "undefined" ? localStorage.getItem("active_studio_id") : null;
    const savedStudio = saved ? studios.find((s) => s.studio_id === saved) : null;

    // Use saved, or primary, or first
    const active = savedStudio || studios.find((s) => s.is_primary) || studios[0];
    set({
      studios,
      activeStudioId: active.studio_id,
      activeStudioRole: active.role,
    });

    if (typeof window !== "undefined") {
      localStorage.setItem("active_studio_id", active.studio_id);
    }
  },

  switchStudio: (studioId) => {
    const { studios } = get();
    const studio = studios.find((s) => s.studio_id === studioId);
    if (!studio) return;

    set({
      activeStudioId: studio.studio_id,
      activeStudioRole: studio.role,
    });

    if (typeof window !== "undefined") {
      localStorage.setItem("active_studio_id", studio.studio_id);
    }
  },

  getEffectivePermissions: (orgPermissions) => {
    // Per-user permissions from the API are the final authority.
    // The owner sets these via Staff > Permissions. No filtering.
    return orgPermissions;
  },
}));
