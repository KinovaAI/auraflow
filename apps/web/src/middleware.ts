import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/portal-register",
  "/tour",
  "/kiosk-locked",
  "/kiosk-unlock",
];

// Paths exempted from the kiosk-lock device gate — the kiosk itself
// must remain reachable on a locked iPad, otherwise the lock would
// brick the device for its intended use.
const KIOSK_LOCK_WHITELIST = [
  "/dashboard/check-in/kiosk",
];

function isKioskAllowedPath(pathname: string): boolean {
  return KIOSK_LOCK_WHITELIST.some((p) => pathname.startsWith(p))
    || /^\/[^/]+\/dashboard\/check-in\/kiosk/.test(pathname);
}

/**
 * Build Content-Security-Policy with a per-request nonce for inline scripts.
 *
 * Deployed in Report-Only mode first (CSP_ENFORCE=false). Flip CSP_ENFORCE=true
 * after 48 hours of a clean Sentry inbox for csp-violation reports.
 */
function buildCsp(nonce: string): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' https://js.stripe.com https://www.googletagmanager.com https://www.google-analytics.com https://connect.facebook.net`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://*.s3.amazonaws.com https://*.backblazeb2.com https://*.stripe.com https://www.google-analytics.com https://www.facebook.com",
    "font-src 'self' data:",
    "connect-src 'self' https://api.auraflow.fit https://*.auraflow.fit https://*.sentry.io https://www.google-analytics.com https://api.stripe.com https://checkout.stripe.com wss://*",
    "frame-src https://js.stripe.com https://hooks.stripe.com https://*.zoom.us",
    "media-src 'self' https://stream.mux.com blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self' https://checkout.stripe.com",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ];
  return directives.join("; ");
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Generate per-request nonce for CSP (16 random bytes -> base64)
  const nonceBytes = crypto.getRandomValues(new Uint8Array(16));
  let nonceBinary = "";
  for (let i = 0; i < nonceBytes.length; i++) {
    nonceBinary += String.fromCharCode(nonceBytes[i]);
  }
  const nonce = btoa(nonceBinary);

  const applyCspHeaders = (res: NextResponse): NextResponse => {
    const csp = buildCsp(nonce);
    const enforce = process.env.CSP_ENFORCE === "true";
    const headerName = enforce
      ? "Content-Security-Policy"
      : "Content-Security-Policy-Report-Only";
    res.headers.set(headerName, csp);
    res.headers.set("x-nonce", nonce);
    return res;
  };

  // Allow public auth paths
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    const authStatus = request.cookies.get("auth_status");
    if (authStatus && (pathname === "/login" || pathname === "/signup")) {
      return applyCspHeaders(NextResponse.redirect(new URL("/dashboard", request.url)));
    }
    return applyCspHeaders(NextResponse.next());
  }

  // Protect dashboard routes (both /dashboard and /[slug]/dashboard)
  if (pathname.startsWith("/dashboard") || /^\/[^/]+\/dashboard/.test(pathname)) {
    // Device-level kiosk lock. Two cookies are honored:
    //   - auraflow_kiosk_device  (NEW, httponly, server-issued, backed
    //     by af_global.kiosk_devices, survives Safari "Clear Cookies"
    //     because the API will rebind it from the device fingerprint)
    //   - auraflow_kiosk_lock    (LEGACY, client-side only, kept so
    //     studios that already set the old cookie still get the UX
    //     redirect after deploying the new system)
    // Either cookie present + path outside the kiosk allowlist → bounce
    // to /kiosk-locked. The new cookie is the authoritative lock; this
    // middleware only does the UX redirect. The actual API-level
    // enforcement lives in apps/api app/middleware/kiosk_device.py.
    const kioskDevice = request.cookies.get("auraflow_kiosk_device");
    const kioskLockLegacy = request.cookies.get("auraflow_kiosk_lock");
    const isKioskLocked =
      (kioskDevice && kioskDevice.value !== "") ||
      kioskLockLegacy?.value === "1";
    if (isKioskLocked && !isKioskAllowedPath(pathname)) {
      return applyCspHeaders(NextResponse.redirect(new URL("/kiosk-locked", request.url)));
    }
    const authStatus = request.cookies.get("auth_status");
    if (!authStatus) {
      return applyCspHeaders(NextResponse.redirect(new URL("/login", request.url)));
    }
  }

  // Protect portal routes
  if (pathname.startsWith("/portal")) {
    const authStatus = request.cookies.get("auth_status");
    if (!authStatus) {
      return applyCspHeaders(NextResponse.redirect(new URL("/login", request.url)));
    }
  }

  // Protect onboarding routes
  if (pathname.startsWith("/onboarding")) {
    const authStatus = request.cookies.get("auth_status");
    if (!authStatus) {
      return applyCspHeaders(NextResponse.redirect(new URL("/login", request.url)));
    }
  }

  return applyCspHeaders(NextResponse.next());
}

export const config = {
  matcher: [
    /*
     * Match all paths except static/image/font files and API routes.
     * CSP should apply to every HTML page served.
     */
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|woff|woff2|ttf|eot)).*)",
  ],
};
