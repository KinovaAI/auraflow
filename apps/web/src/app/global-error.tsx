"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
        <h1 className="text-6xl font-bold text-red-600">Error</h1>
        <p className="mt-4 text-xl text-gray-600">Something went wrong</p>
        <button
          onClick={reset}
          className="mt-8 rounded-lg bg-indigo-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 transition-colors"
        >
          Try again
        </button>
      </body>
    </html>
  );
}
