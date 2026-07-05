import { apiClient } from "./api-client";
import type {
  AuthTokens,
  User,
  LoginCredentials,
  RegisterData,
  MemberRegisterData,
} from "@/types/auth";

export const authApi = {
  login: (credentials: LoginCredentials) =>
    apiClient.post<AuthTokens>("/auth/login/json", credentials),

  register: (data: RegisterData) =>
    apiClient.post<AuthTokens>("/auth/register", data),

  memberRegister: (data: MemberRegisterData) =>
    apiClient.post<AuthTokens>("/auth/member-register", data),

  refresh: (refreshToken: string) =>
    apiClient.post<AuthTokens>("/auth/refresh", {
      refresh_token: refreshToken,
    }),

  logout: (refreshToken: string) =>
    apiClient.post("/auth/logout", { refresh_token: refreshToken }),

  getMe: () => apiClient.get<User>("/users/me"),

  updateMe: (data: { first_name?: string; last_name?: string; phone?: string }) =>
    apiClient.put<User>("/users/me", data),

  forgotPassword: (email: string) =>
    apiClient.post("/auth/forgot-password", { email }),

  resetPassword: (token: string, newPassword: string) =>
    apiClient.post("/auth/reset-password", {
      token,
      new_password: newPassword,
    }),

  changePassword: (newPassword: string, currentPassword?: string) =>
    apiClient.post<{ message: string }>("/auth/change-password", {
      new_password: newPassword,
      ...(currentPassword ? { current_password: currentPassword } : {}),
    }),

  verifyEmail: (token: string) =>
    apiClient.get<{ message: string }>(`/auth/verify-email?token=${encodeURIComponent(token)}`),

  resendVerification: () =>
    apiClient.post<{ message: string }>("/auth/resend-verification"),

  validateInvite: (token: string) =>
    apiClient.get<{ org_slug: string; org_name: string; role: string; email: string }>(
      `/auth/validate-invite?token=${encodeURIComponent(token)}`
    ),

  mfaVerify: (mfaToken: string, code: string) =>
    apiClient.post<AuthTokens>("/auth/mfa/verify", {
      mfa_token: mfaToken,
      code,
    }),
};
