"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function PortalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error, {
      tags: { segment: "portal" },
    });
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-amber-50">
        <svg
          className="h-7 w-7 text-amber-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m0-10.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z"
          />
        </svg>
      </div>
      <h2 className="mt-5 text-xl font-bold text-gray-900">
        Something went wrong
      </h2>
      <p className="mt-2 text-sm text-gray-600">
        We couldn't load that page. The studio has been notified automatically.
        Try again, or head back to your dashboard.
      </p>
      {error.digest && (
        <p className="mt-2 text-xs text-gray-400">
          Reference:{" "}
          <code className="rounded bg-gray-100 px-1 py-0.5 font-mono">
            {error.digest}
          </code>
        </p>
      )}
      <div className="mt-6 flex items-center justify-center gap-3">
        <button
          onClick={reset}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
        >
          Try again
        </button>
        <a
          href="/portal"
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          Back to portal
        </a>
      </div>
    </div>
  );
}
