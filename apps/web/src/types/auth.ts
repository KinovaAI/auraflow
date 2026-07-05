export interface UserStudioRole {
  studio_id: string;
  studio_name: string;
  studio_slug: string;
  role: string;
  is_primary: boolean;
}

export interface User {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  avatar_url: string | null;
  is_platform_admin: boolean;
  email_verified: boolean;
  organizations: UserOrganization[];
  permissions?: string[];
  active_org_slug?: string | null;
  active_org_role?: string | null;
  has_video_access?: boolean;
  studios?: UserStudioRole[];
}

export interface UserOrganization {
  id: string;
  slug: string;
  name: string;
  role: "owner" | "admin" | "instructor" | "front_desk" | "member";
  status: string;
  trial_ends_at?: string | null;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  force_password_reset?: boolean;
  force_password_change?: boolean;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
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
}

export interface MemberRegisterData {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  phone?: string;
  organization_slug: string;
}
