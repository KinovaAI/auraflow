import { useAuthStore } from "@/stores/auth-store";

/**
 * Check if the current user has any of the given action-level permission keys
 * (OR semantics — passes if the user holds ANY one of them).
 *
 * Action-level keys come from app.services.permissions.ALL_PERMISSIONS on the
 * backend and are returned by /users/me.
 *
 * Owner and platform_admin always return true; member always returns false.
 */
export function usePermission(...permissionKeys: string[]): boolean {
  const permissions = useAuthStore((s) => s.permissions);
  const user = useAuthStore((s) => s.user);

  if (!user) return false;

  // Platform admin sees everything
  if (user.is_platform_admin) return true;

  // Use the active org role from JWT context, fallback to first org
  const role = user.active_org_role ?? user.organizations?.[0]?.role;
  if (!role) return false;

  // Owner always has access
  if (role === "owner") return true;

  // Member has no staff permissions
  if (role === "member") return false;

  return permissionKeys.some((k) => permissions.includes(k));
}
