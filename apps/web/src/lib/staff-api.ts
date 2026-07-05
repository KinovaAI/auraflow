import { apiClient } from "./api-client";
import type {
  StaffMember,
  UpdateStaffProfile,
  UpdatePermissions,
  PermissionDefaults,
  UserPermissions,
} from "@/types/staff";

export const staffApi = {
  list: () => apiClient.get<StaffMember[]>("/staff"),

  invite: (orgSlug: string, data: { email: string; role: string }) =>
    apiClient.post(`/organizations/${orgSlug}/members`, data),

  get: (userId: string) => apiClient.get<StaffMember>(`/staff/${userId}`),

  updateProfile: (userId: string, data: UpdateStaffProfile) =>
    apiClient.put<StaffMember>(`/staff/${userId}`, data),

  updateRole: (userId: string, role: string) =>
    apiClient.put<StaffMember>(`/staff/${userId}/role`, { role }),

  updatePermissions: (userId: string, data: UpdatePermissions) =>
    apiClient.put<StaffMember>(`/staff/${userId}/permissions`, data),

  getDefaults: () =>
    apiClient.get<PermissionDefaults>("/staff/permissions/defaults"),

  getMyPermissions: () =>
    apiClient.get<UserPermissions>("/staff/me/permissions"),
};
