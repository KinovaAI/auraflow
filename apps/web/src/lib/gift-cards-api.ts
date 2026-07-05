import { apiClient } from "./api-client";

// ── Types ────────────────────────────────────────────────────────────────────

export interface GiftCard {
  id: string;
  code: string;
  // Backend returns `amount_cents`. `initial_amount_cents` is a legacy
  // alias kept for places that still read it; both are populated.
  amount_cents: number;
  initial_amount_cents: number;
  balance_cents: number;
  status: "active" | "fully_redeemed" | "voided" | "expired";
  recipient_email?: string;
  recipient_name?: string;
  purchaser_name?: string;
  purchaser_member_id?: string;
  personal_message?: string;
  message?: string;
  expires_at?: string;
  created_at: string;
  updated_at?: string;
  redemptions?: GiftCardRedemption[];
  // Set on /gift-cards/my responses so the portal can label cards
  // as bought-by-me vs received-as-gift.
  relationship?: "purchased" | "received" | "purchased_and_received";
}

export interface GiftCardRedemption {
  id: string;
  gift_card_id: string;
  amount_cents: number;
  redeemed_by_member_id?: string;
  redeemed_by_name?: string;
  transaction_id?: string;
  created_at: string;
}

export interface CreateGiftCardRequest {
  amount_cents: number;
  recipient_email?: string;
  recipient_name?: string;
  purchaser_name?: string;
  personal_message?: string;
  expires_at?: string;
  // Payment method is now required. Stripe-based methods return a
  // checkout_url; cash/check/comp/venmo create the card immediately.
  payment_method?: string;
  purchaser_member_id?: string;
  success_url?: string;
  cancel_url?: string;
}

export interface CreateGiftCardResponse {
  gift_card?: GiftCard;
  checkout_url?: string;
  checkout_session_id?: string;
  payment_method: string;
}

export interface RedeemRequest {
  code: string;
  amount_cents: number;
}

export interface CheckBalanceResponse {
  code: string;
  initial_amount_cents: number;
  balance_cents: number;
  status: string;
  expires_at?: string;
}

export interface GiftCardStats {
  total_issued_cents: number;
  total_redeemed_cents: number;
  outstanding_balance_cents: number;
  total_count: number;
  active_count: number;
}

// ── API ──────────────────────────────────────────────────────────────────────

export const giftCardsApi = {
  create: (data: CreateGiftCardRequest) =>
    apiClient.post<CreateGiftCardResponse>("/gift-cards", data),

  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    apiClient.get<GiftCard[]>("/gift-cards", { params }),

  getById: (id: string) =>
    apiClient.get<GiftCard>(`/gift-cards/${id}`),

  void: (id: string) =>
    apiClient.post<{ data: GiftCard }>(`/gift-cards/${id}/void`),

  adjust: (id: string, data: { amount_cents: number; reason?: string }) =>
    apiClient.post<{ data: GiftCard }>(`/gift-cards/${id}/adjust`, data),

  resend: (id: string) =>
    apiClient.post<{ message: string }>(`/gift-cards/${id}/resend`),

  checkBalance: (code: string) =>
    apiClient.get<{ data: CheckBalanceResponse }>(`/gift-cards/balance/${code}`),

  redeem: (data: RedeemRequest) =>
    apiClient.post<{ data: GiftCardRedemption }>("/gift-cards/redeem", data),

  getStats: () =>
    apiClient.get<GiftCardStats>("/gift-cards/stats"),

  listMyGiftCards: () =>
    apiClient.get<GiftCard[]>("/gift-cards/my"),
};
