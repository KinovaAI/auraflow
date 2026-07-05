export interface StaffMember {
  user_id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: string;
  title: string | null;
  department: string | null;
  hire_date: string | null;
  is_active: boolean;
  permissions: string[];
}

export interface UpdateStaffProfile {
  title?: string;
  department?: string;
  hire_date?: string;
  notes?: string;
}

export interface UpdatePermissions {
  permissions: Record<string, boolean>;
}

export interface PermissionDefaults {
  all_permissions: string[];
  defaults: Record<string, string[]>;
}

export interface UserPermissions {
  role: string;
  permissions: string[];
}
