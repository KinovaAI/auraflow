"use client";

import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth-store";

export function useAuth() {
  // Use individual selectors for stable refs (prevents re-render loops)
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const loadUser = useAuthStore((s) => s.loadUser);
  const login = useAuthStore((s) => s.login);
  const register = useAuthStore((s) => s.register);
  const memberRegister = useAuthStore((s) => s.memberRegister);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    if (isLoading && !user) {
      loadUser();
    }
  }, [isLoading, user, loadUser]);

  return { user, isAuthenticated, isLoading, login, register, memberRegister, logout, loadUser };
}
