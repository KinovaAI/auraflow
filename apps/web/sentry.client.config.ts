import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  enabled: !!process.env.NEXT_PUBLIC_SENTRY_DSN,

  // Only error tracking — no performance tracing
  tracesSampleRate: 0,

  // Filter out noisy browser errors
  ignoreErrors: [
    "ResizeObserver loop",
    "Non-Error promise rejection",
    /Loading chunk \d+ failed/,
  ],
});
