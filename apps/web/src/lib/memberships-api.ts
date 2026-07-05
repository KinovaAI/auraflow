import { apiClient } from "./api-client";

export interface MembershipType {
  id: string;
  studio_id: string;
  name: string;
  description?: string;
  type: "unlimited" | "class_pack" | "intro_offer" | "day_pass" | "single_class";
  access_scope: "in_studio" | "online" | "all_access";
  template_key?: string;
  is_template: boolean;
  class_count?: number;
  price_cents: number;
  billing_period?: string;
  duration_days?: number;
  is_founding_rate: boolean;
  max_enrollments?: number;
  auto_renew: boolean;
  trial_days: number;
  freeze_allowed: boolean;
  max_freeze_days: number;
  cancellation_notice_days: number;
  is_active: boolean;
  is_public: boolean;
  sort_order: number;
}

export interface MemberMembership {
  id: string;
  member_id: string;
  membership_type_id: string;
  type_name?: string;
  membership_type?: string;
  access_scope?: "in_studio" | "online" | "all_access";
  member_first_name?: string;
  member_last_name?: string;
  status: string;
  starts_at: string;
  ends_at?: string;
  classes_remaining?: number;
  total_classes?: number;
  price_cents?: number;
  frozen_at?: string;
  frozen_until?: string;
  cancelled_at?: string;
  cancellation_reason?: string;
}

export interface Eligibility {
  eligible: boolean;
  membership_id?: string;
  type?: string;
  classes_remaining?: number;
}

export const membershipTypesApi = {
  list: (studioId: string) =>
    apiClient.get<MembershipType[]>(`/memberships/types?studio_id=${studioId}`),

  get: (id: string) =>
    apiClient.get<MembershipType>(`/memberships/types/${id}`),

  create: (data: Partial<MembershipType> & { studio_id: string; name: string; type: string; price_cents: number }) =>
    apiClient.post<MembershipType>("/memberships/types", data),

  update: (id: string, data: Partial<MembershipType>) =>
    apiClient.put<MembershipType>(`/memberships/types/${id}`, data),

  deactivate: (id: string) => apiClient.delete(`/memberships/types/${id}`),

  listTemplates: () =>
    apiClient.get<MembershipType[]>("/memberships/templates"),

  seedDefaults: (studioId: string) =>
    apiClient.post<MembershipType[]>(
      `/memberships/types/seed-defaults?studio_id=${studioId}`
    ),
};

export const memberMembershipsApi = {
  listAll: (activeOnly: boolean = true) =>
    apiClient.get<MemberMembership[]>(
      `/memberships/active?active_only=${activeOnly}`
    ),

  listForMember: (memberId: string, activeOnly: boolean = true) =>
    apiClient.get<MemberMembership[]>(
      `/memberships/member/${memberId}?active_only=${activeOnly}`
    ),

  get: (id: string) =>
    apiClient.get<MemberMembership>(`/memberships/${id}`),

  assign: (memberId: string, typeId: string, startsAt?: string) =>
    apiClient.post<MemberMembership>("/memberships/assign", {
      member_id: memberId,
      membership_type_id: typeId,
      starts_at: startsAt,
    }),

  purchaseWithGiftCard: (memberId: string, typeId: string, giftCardCode: string) =>
    apiClient.post<MemberMembership>("/memberships/purchase-with-gift-card", {
      member_id: memberId,
      membership_type_id: typeId,
      gift_card_code: giftCardCode,
    }),

  freeze: (id: string, until?: string) =>
    apiClient.post<MemberMembership>(`/memberships/${id}/freeze`, { until }),

  unfreeze: (id: string) =>
    apiClient.post<MemberMembership>(`/memberships/${id}/unfreeze`),

  cancel: (id: string, reason?: string) =>
    apiClient.post<MemberMembership>(`/memberships/${id}/cancel`, { reason }),

  checkEligibility: (memberId: string) =>
    apiClient.get<Eligibility>(`/memberships/eligibility/${memberId}`),
};
