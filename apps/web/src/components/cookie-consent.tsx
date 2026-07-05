"use client";

import { useEffect, useState, useCallback } from "react";

interface CookiePreferences {
  essential: boolean;
  analytics: boolean;
  marketing: boolean;
}

const STORAGE_KEY = "cookie-consent";

function getStoredPreferences(): CookiePreferences | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored) as CookiePreferences;
    }
  } catch {
    // ignore parse errors
  }
  return null;
}

function savePreferences(preferences: CookiePreferences) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
}

export function CookieConsent() {
  const [visible, setVisible] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  const [preferences, setPreferences] = useState<CookiePreferences>({
    essential: true,
    analytics: false,
    marketing: false,
  });

  useEffect(() => {
    const stored = getStoredPreferences();
    if (!stored) {
      setVisible(true);
    }
  }, []);

  const handleAcceptAll = useCallback(() => {
    const prefs: CookiePreferences = {
      essential: true,
      analytics: true,
      marketing: true,
    };
    savePreferences(prefs);
    setVisible(false);
  }, []);

  const handleEssentialOnly = useCallback(() => {
    const prefs: CookiePreferences = {
      essential: true,
      analytics: false,
      marketing: false,
    };
    savePreferences(prefs);
    setVisible(false);
  }, []);

  const handleSavePreferences = useCallback(() => {
    savePreferences({ ...preferences, essential: true });
    setVisible(false);
  }, [preferences]);

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 p-4">
      <div className="mx-auto max-w-3xl rounded-xl border border-gray-200 bg-white p-6 shadow-lg">
        {!showPreferences ? (
          <>
            <div className="mb-4">
              <h3 className="text-base font-semibold text-gray-900">
                Cookie Settings
              </h3>
              <p className="mt-1 text-sm text-gray-600">
                We use cookies to enhance your experience, analyze site traffic,
                and assist in our marketing efforts. By clicking &quot;Accept
                All&quot;, you consent to our use of cookies. You can manage your
                preferences or choose essential cookies only.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={handleAcceptAll}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
              >
                Accept All
              </button>
              <button
                onClick={handleEssentialOnly}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
              >
                Essential Only
              </button>
              <button
                onClick={() => setShowPreferences(true)}
                className="px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 rounded-lg"
              >
                Manage Preferences
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="mb-4">
              <h3 className="text-base font-semibold text-gray-900">
                Manage Cookie Preferences
              </h3>
            </div>
            <div className="mb-4 space-y-3">
              <label className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
                <div>
                  <span className="text-sm font-medium text-gray-900">
                    Essential
                  </span>
                  <p className="text-xs text-gray-500">
                    Required for the platform to function. Cannot be disabled.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked
                  disabled
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600"
                />
              </label>
              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-gray-200 px-4 py-3 transition-colors hover:bg-gray-50">
                <div>
                  <span className="text-sm font-medium text-gray-900">
                    Analytics
                  </span>
                  <p className="text-xs text-gray-500">
                    Help us understand how visitors interact with the platform.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={preferences.analytics}
                  onChange={(e) =>
                    setPreferences((prev) => ({
                      ...prev,
                      analytics: e.target.checked,
                    }))
                  }
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
              </label>
              <label className="flex cursor-pointer items-center justify-between rounded-lg border border-gray-200 px-4 py-3 transition-colors hover:bg-gray-50">
                <div>
                  <span className="text-sm font-medium text-gray-900">
                    Marketing
                  </span>
                  <p className="text-xs text-gray-500">
                    Used to deliver relevant advertisements and track campaign
                    performance.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={preferences.marketing}
                  onChange={(e) =>
                    setPreferences((prev) => ({
                      ...prev,
                      marketing: e.target.checked,
                    }))
                  }
                  className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={handleSavePreferences}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
              >
                Save Preferences
              </button>
              <button
                onClick={() => setShowPreferences(false)}
                className="px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 rounded-lg"
              >
                Back
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
