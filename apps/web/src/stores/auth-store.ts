import { create } from "zustand";
import type { User } from "@/types/auth";
import { authApi } from "@/lib/auth-api";
import { useStudioStore } from "@/stores/studio-store";

interface AuthState {
  user: User | null;
  permissions: string[];
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  completeMfaLogin: (mfaToken: string, code: string) => Promise<void>;
  register: (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
    organization_name?: string;
    organization_slug?: string;
    invite_token?: string;
    utm_source?: string;
    utm_medium?: string;
    utm_campaign?: string;
    gclid?: string;
    fbclid?: string;
  }) => Promise<void>;
  memberRegister: (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
    phone?: string;
    organization_slug: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  loadUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  permissions: [],
  isAuthenticated: false,
  isLoading: true,

  login: async (email, password) => {
    const { data: tokens } = await authApi.login({ email, password });

    // If MFA is required, store the MFA token and throw a special error
    // so the login page can show the MFA verification step
    if ((tokens as unknown as { requires_mfa?: boolean }).requires_mfa) {
      const mfaToken = (tokens as unknown as { mfa_token: string }).mfa_token;
      const err = new Error("MFA_REQUIRED");
      (err as unknown as { mfaToken: string }).mfaToken = mfaToken;
      throw err;
    }

    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    document.cookie = "auth_status=1; path=/; max-age=2592000; Secure; SameSite=Strict";

    // Check if user must reset/change password before proceeding.
    // Both flags route to the same /change-password screen — `_reset`
    // is the email-link path (clears on token use); `_change` is the
    // in-app-only path (admin forced it, no email). Previously only
    // _reset was wired up, and Mira Dick was able to log in past the
    // change-password gate even though force_password_change=TRUE.
    if (tokens.force_password_reset || tokens.force_password_change) {
      localStorage.setItem("force_password_reset", "1");
    }

    const { data: user } = await authApi.getMe();
    set({
      user,
      permissions: user.permissions ?? [],
      isAuthenticated: true,
      isLoading: false,
    });
    useStudioStore.getState().setStudios(user.studios ?? []);
  },

  completeMfaLogin: async (mfaToken: string, code: string) => {
    const { data: tokens } = await authApi.mfaVerify(mfaToken, code);
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    document.cookie = "auth_status=1; path=/; max-age=2592000; Secure; SameSite=Strict";

    if (tokens.force_password_reset || tokens.force_password_change) {
      localStorage.setItem("force_password_reset", "1");
    }

    const { data: user } = await authApi.getMe();
    set({
      user,
      permissions: user.permissions ?? [],
      isAuthenticated: true,
      isLoading: false,
    });
    useStudioStore.getState().setStudios(user.studios ?? []);
  },

  register: async (data) => {
    const { data: tokens } = await authApi.register(data);
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    document.cookie = "auth_status=1; path=/; max-age=2592000; Secure; SameSite=Strict";

    const { data: user } = await authApi.getMe();
    set({
      user,
      permissions: user.permissions ?? [],
      isAuthenticated: true,
      isLoading: false,
    });
    useStudioStore.getState().setStudios(user.studios ?? []);
  },

  memberRegister: async (data) => {
    const { data: tokens } = await authApi.memberRegister(data);
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    document.cookie = "auth_status=1; path=/; max-age=2592000; Secure; SameSite=Strict";

    const { data: user } = await authApi.getMe();
    set({
      user,
      permissions: user.permissions ?? [],
      isAuthenticated: true,
      isLoading: false,
    });
    useStudioStore.getState().setStudios(user.studios ?? []);
  },

  logout: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        // Best effort
      }
    }
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("active_studio_id");
    localStorage.removeItem("dismiss_verify_banner");
    document.cookie = "auth_status=; path=/; max-age=0";
    set({ user: null, permissions: [], isAuthenticated: false, isLoading: false });
    useStudioStore.getState().setStudios([]);
  },

  loadUser: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      set({ isLoading: false });
      return;
    }
    try {
      const { data: user } = await authApi.getMe();
      set({
        user,
        permissions: user.permissions ?? [],
        isAuthenticated: true,
        isLoading: false,
      });
      useStudioStore.getState().setStudios(user.studios ?? []);
    } catch (err: unknown) {
      // Only clear tokens on 401 (unauthorized) — not on network/timeout errors
      // to prevent mass logout when the API is temporarily unreachable
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        document.cookie = "auth_status=; path=/; max-age=0";
        set({ user: null, permissions: [], isAuthenticated: false, isLoading: false });
      } else {
        set({ isLoading: false });
      }
    }
  },
}));
