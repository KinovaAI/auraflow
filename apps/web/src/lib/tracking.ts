/**
 * AuraFlow — Analytics tracking utilities.
 *
 * All functions are safe to call even when tracking scripts are not loaded
 * (e.g. user has not consented). They degrade gracefully to no-ops.
 */

declare global {
  interface Window {
    fbq?: (...args: any[]) => void;
    gtag?: (...args: any[]) => void;
  }
}

/**
 * Fire a custom event to both Facebook Pixel and GA4.
 */
export function trackEvent(eventName: string, params?: Record<string, any>) {
  // Facebook Pixel
  if (typeof window !== "undefined" && window.fbq) {
    window.fbq("trackCustom", eventName, params ?? {});
  }

  // Google Analytics 4
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", eventName, params ?? {});
  }
}

type ConversionType = "signup" | "purchase" | "booking";

/**
 * Fire a conversion event to both platforms.
 *
 * @param type    — "signup" | "purchase" | "booking"
 * @param valueCents — optional value in cents (used for purchase conversions)
 */
export function trackConversion(type: ConversionType, valueCents?: number) {
  const value = valueCents ? valueCents / 100 : undefined;

  switch (type) {
    case "signup":
      if (typeof window !== "undefined" && window.fbq) {
        window.fbq("track", "Lead");
      }
      if (typeof window !== "undefined" && window.gtag) {
        window.gtag("event", "sign_up", { method: "email" });
      }
      break;

    case "purchase":
      if (typeof window !== "undefined" && window.fbq) {
        window.fbq("track", "Purchase", {
          value: value ?? 0,
          currency: "USD",
        });
      }
      if (typeof window !== "undefined" && window.gtag) {
        window.gtag("event", "purchase", {
          value: value ?? 0,
          currency: "USD",
        });
      }
      break;

    case "booking":
      if (typeof window !== "undefined" && window.fbq) {
        window.fbq("track", "Schedule");
      }
      if (typeof window !== "undefined" && window.gtag) {
        window.gtag("event", "begin_checkout");
      }
      break;
  }
}
