const { withSentryConfig } = require("@sentry/nextjs");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

// Bundle analyzer — run `ANALYZE=1 npm run build` (or set ANALYZE=1 in
// .env.local) to get a visual treemap of what's in each bundle. Catches
// fat dependencies that slipped in without being dynamic-imported.
const withBundleAnalyzer = require("@next/bundle-analyzer")({
  enabled: process.env.ANALYZE === "1",
  openAnalyzer: false,
});

module.exports = withSentryConfig(withBundleAnalyzer(nextConfig), {
  // Suppress source map upload warnings when no auth token is set
  silent: !process.env.SENTRY_AUTH_TOKEN,

  // Upload source maps only when an auth token is available
  disableServerWebpackPlugin: !process.env.SENTRY_AUTH_TOKEN,
  disableClientWebpackPlugin: !process.env.SENTRY_AUTH_TOKEN,

  // Hide source maps from users
  hideSourceMaps: true,

  // Disable telemetry
  telemetry: false,
});
