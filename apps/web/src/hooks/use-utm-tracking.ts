"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";

const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
] as const;

const CLICK_ID_KEYS = ["gclid", "fbclid"] as const;

const SESSION_KEY = "utm_params";

export interface UtmParams {
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  utm_term?: string;
  gclid?: string;
  fbclid?: string;
}

/**
 * On mount, captures UTM parameters and click IDs (gclid, fbclid) from the
 * current URL and stores them in sessionStorage so they persist across
 * in-session navigations but do not leak across sessions.
 */
export function useUtmTracking() {
  const searchParams = useSearchParams();

  useEffect(() => {
    if (typeof window === "undefined") return;

    const params: UtmParams = {};
    let hasAny = false;

    for (const key of UTM_KEYS) {
      const val = searchParams.get(key);
      if (val) {
        params[key] = val;
        hasAny = true;
      }
    }

    for (const key of CLICK_ID_KEYS) {
      const val = searchParams.get(key);
      if (val) {
        params[key] = val;
        hasAny = true;
        // Also store click IDs individually for easy access
        sessionStorage.setItem(key, val);
      }
    }

    if (hasAny) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(params));
    }
  }, [searchParams]);
}

/**
 * Read stored UTM params from sessionStorage.
 */
export function getStoredUtmParams(): UtmParams {
  if (typeof window === "undefined") return {};
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) return JSON.parse(raw) as UtmParams;
  } catch {
    // ignore
  }
  return {};
}
