/**
 * Square POS deeplink return page.
 *
 * Square POS (iPhone) deep-links here after a payment completes or
 * fails. We proxy the query params to the API's reconciliation
 * endpoint, then redirect the browser to wherever the API tells us.
 *
 * Why this exists as a Next.js page: the URL registered in the Square
 * Developer Console points at app.auraflow.fit (the web app), but the
 * actual reconciliation handler lives on api.auraflow.fit. Without
 * this page, Square's callback hit a 404 and POS charges stayed
 * pending forever (Helene Kemp's Sound Bath + Breathwork charges,
 * 2026-06-10). Server component so the reconciliation happens before
 * the browser sees anything — no flash of empty state.
 */
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function POSReturnPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const qs = new URLSearchParams();
  for (const k of ["data", "error_code", "error_description"]) {
    const v = params[k];
    if (typeof v === "string") qs.set(k, v);
  }

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://api.auraflow.fit";
  const apiUrl = `${apiBase}/api/v1/payments/pos/deeplink-return?${qs.toString()}`;

  let destination = "/dashboard/pos?pos_status=unknown";
  try {
    const res = await fetch(apiUrl, {
      redirect: "manual",
      cache: "no-store",
    });
    // The API returns a 302 with the next-hop location
    const loc = res.headers.get("location");
    if (loc) destination = loc;
  } catch (e) {
    console.error("POS return proxy failed:", e);
    destination = "/dashboard/pos?pos_status=proxy_error";
  }

  redirect(destination);
}
