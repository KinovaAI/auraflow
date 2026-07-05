"use client";

/**
 * Public hosted card-save page.
 *
 * Reached from every studio's "Manage Billing" / "Manage Payment Methods"
 * button via a public URL: /save-card?token=<jwt>. The JWT is signed by
 * the API and carries member_id + org_id + return_url; this page mounts
 * the Square Web Payments SDK, tokenizes the entered card, posts the
 * nonce to /save-card/submit, then bounces the user back to return_url.
 *
 * Why public + JWT instead of cookie auth: the studio's website (e.g.
 * your-domain.com) lives on a different origin than this page
 * (app.auraflow.fit), so the member's portal session cookies are not
 * available here. The signed JWT proves the click came from a legit
 * authenticated session on the studio side.
 */
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, CheckCircle2, AlertTriangle, CreditCard, ShieldCheck } from "lucide-react";

type SquareCardInstance = {
  attach: (selector: string) => Promise<void>;
  destroy: () => Promise<void> | void;
  tokenize: () => Promise<{ status: string; token?: string; errors?: { message: string }[] }>;
};

type SquarePayments = {
  payments: (
    appId: string,
    locationId: string,
  ) => { card: () => Promise<SquareCardInstance> };
};

type SaveCardConfig = {
  application_id: string;
  location_id: string;
  environment: string;
  studio_name: string;
  member_name: string;
  return_url: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.auraflow.fit";

function SaveCardInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [phase, setPhase] = useState<"loading" | "ready" | "saving" | "done" | "error">("loading");
  const [config, setConfig] = useState<SaveCardConfig | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardholderName, setCardholderName] = useState("");
  const cardRef = useRef<SquareCardInstance | null>(null);

  // 1. Load config from the API (validates the token + fetches Square IDs)
  useEffect(() => {
    if (!token) {
      setErrorMsg("This link is missing its security token. Please go back to the studio website and click 'Manage Billing' again.");
      setPhase("error");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`${API_BASE}/api/v1/save-card/config?token=${encodeURIComponent(token)}`);
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(body?.detail || `Could not load this link (HTTP ${resp.status}).`);
        }
        const json = await resp.json();
        const data = (json?.data ?? json) as SaveCardConfig;
        if (!cancelled) {
          setConfig(data);
          setCardholderName(data.member_name || "");
        }
      } catch (err) {
        if (!cancelled) {
          setErrorMsg(err instanceof Error ? err.message : "Could not load this link.");
          setPhase("error");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // 2. Once we have config, mount the Square Web Payments SDK card field
  useEffect(() => {
    if (!config) return;
    let cancelled = false;
    (async () => {
      try {
        if (!(window as unknown as { Square?: SquarePayments }).Square) {
          const script = document.createElement("script");
          script.src = config.environment === "production"
            ? "https://web.squarecdn.com/v1/square.js"
            : "https://sandbox.web.squarecdn.com/v1/square.js";
          script.async = true;
          await new Promise<void>((resolve, reject) => {
            script.onload = () => resolve();
            script.onerror = () => reject(new Error("Could not load Square's payment library."));
            document.head.appendChild(script);
          });
        }
        if (cancelled) return;
        const sq = (window as unknown as { Square?: SquarePayments }).Square;
        if (!sq) throw new Error("Square's payment library failed to load.");
        const payments = sq.payments(config.application_id, config.location_id);
        const card = await payments.card();
        await card.attach("#square-card-container");
        if (!cancelled) {
          cardRef.current = card;
          setPhase("ready");
        }
      } catch (err) {
        if (!cancelled) {
          setErrorMsg(err instanceof Error ? err.message : "Card form failed to load.");
          setPhase("error");
        }
      }
    })();
    return () => {
      cancelled = true;
      if (cardRef.current) {
        try { cardRef.current.destroy(); } catch {}
      }
    };
  }, [config]);

  const handleSubmit = useCallback(async () => {
    if (!cardRef.current || !config) return;
    setPhase("saving");
    setErrorMsg(null);
    try {
      const result = await cardRef.current.tokenize();
      if (result.status !== "OK" || !result.token) {
        const detail = result.errors?.[0]?.message || "Card information was rejected.";
        throw new Error(detail);
      }
      const resp = await fetch(`${API_BASE}/api/v1/save-card/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          source_id: result.token,
          cardholder_name: cardholderName.trim() || undefined,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(body?.detail || `Could not save the card (HTTP ${resp.status}).`);
      }
      setPhase("done");
      // Bounce back to the studio site after a moment so the user sees the success state.
      setTimeout(() => {
        if (config.return_url) {
          window.location.href = config.return_url;
        }
      }, 1800);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Something went wrong saving the card.");
      setPhase("ready");
    }
  }, [config, token, cardholderName]);

  if (phase === "loading" || !config) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md rounded-lg border border-red-200 bg-white p-6 shadow-sm">
          <AlertTriangle className="mx-auto h-10 w-10 text-red-500" />
          <h1 className="mt-3 text-center text-lg font-semibold text-gray-900">
            We couldn&apos;t open this page
          </h1>
          <p className="mt-2 text-center text-sm text-gray-600">{errorMsg}</p>
        </div>
      </div>
    );
  }

  if (phase === "done") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <div className="w-full max-w-md rounded-lg border border-green-200 bg-white p-6 shadow-sm">
          <CheckCircle2 className="mx-auto h-12 w-12 text-green-500" />
          <h1 className="mt-3 text-center text-lg font-semibold text-gray-900">
            Card saved
          </h1>
          <p className="mt-2 text-center text-sm text-gray-600">
            Taking you back to {config.studio_name}…
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 py-10">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <CreditCard className="h-5 w-5 text-indigo-600" />
          <h1 className="text-lg font-semibold text-gray-900">Save your card</h1>
        </div>
        <p className="mb-4 text-sm text-gray-600">
          {config.studio_name} keeps your card securely on file so future
          purchases and renewals happen automatically. Your card is stored by
          Square — never on the studio&apos;s servers.
        </p>

        <label className="mb-1 block text-xs font-medium text-gray-700" htmlFor="cardholder">
          Cardholder name
        </label>
        <input
          id="cardholder"
          type="text"
          value={cardholderName}
          onChange={(e) => setCardholderName(e.target.value)}
          className="mb-4 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Name on the card"
        />

        <label className="mb-1 block text-xs font-medium text-gray-700">
          Card details
        </label>
        <div
          id="square-card-container"
          className="mb-4 rounded-md border border-gray-300 px-3 py-2"
        />

        {errorMsg && (
          <p className="mb-3 text-sm text-red-600">{errorMsg}</p>
        )}

        <button
          type="button"
          onClick={handleSubmit}
          disabled={phase === "saving"}
          className="flex w-full items-center justify-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {phase === "saving" ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving…
            </>
          ) : (
            "Save card"
          )}
        </button>

        <div className="mt-4 flex items-start gap-2 rounded-md bg-gray-50 p-3">
          <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" />
          <p className="text-xs text-gray-500">
            Your card is tokenized and stored by Square. Neither the studio
            nor AuraFlow ever sees the full number.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function SaveCardPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
      </div>
    }>
      <SaveCardInner />
    </Suspense>
  );
}
