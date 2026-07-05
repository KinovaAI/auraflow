"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";

/**
 * Dashboard keyboard shortcuts for front-desk staff.
 *
 *   /         focus the main search input
 *   c         open check-in page
 *   n         open new booking page
 *   g then s  go to schedule
 *   g then m  go to members
 *   esc       close any open modal
 *   ?         show this shortcut list (dispatches custom event)
 *
 * Intentionally ignores keypresses when the target is a form input or
 * contenteditable so typing into a field doesn't trigger navigation.
 */
export function useDashboardShortcuts() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let gPressed = false;
    let gTimer: ReturnType<typeof setTimeout> | undefined;

    const handler = (e: KeyboardEvent) => {
      // Don't intercept modifiers — let cmd/ctrl combos pass through
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      // Ignore when focus is inside an input, textarea, select, or
      // contenteditable — otherwise "/" would swallow every forward slash
      // a user types into their search box.
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const tag = target.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        target.isContentEditable
      ) {
        // Still allow Escape inside inputs so users can bail out fast.
        if (e.key !== "Escape") return;
      }

      // Single-key shortcuts
      switch (e.key) {
        case "/": {
          e.preventDefault();
          const el =
            document.querySelector<HTMLInputElement>(
              "[data-shortcut='search'], input[type='search'], input[placeholder*='Search' i]"
            ) ||
            document.querySelector<HTMLInputElement>("input[name='search']");
          el?.focus();
          return;
        }
        case "c":
          if (!pathname.startsWith("/dashboard/check-in")) {
            e.preventDefault();
            router.push("/dashboard/check-in");
          }
          return;
        case "n":
          e.preventDefault();
          // Fire a custom event that any page can listen for (e.g., to open
          // a "new X" modal). Pages that don't handle it fall back to
          // navigating to the booking/new route.
          const handled = !window.dispatchEvent(
            new CustomEvent("aura:new", { cancelable: true })
          );
          if (!handled) {
            router.push("/dashboard/schedule?new=1");
          }
          return;
        case "?":
          if (e.shiftKey) {
            e.preventDefault();
            window.dispatchEvent(new CustomEvent("aura:show-shortcuts"));
          }
          return;
        case "Escape":
          window.dispatchEvent(
            new CustomEvent("aura:escape", { cancelable: true })
          );
          return;
      }

      // Two-key "g, X" sequences
      if (gPressed) {
        gPressed = false;
        if (gTimer) clearTimeout(gTimer);
        if (e.key === "s") {
          e.preventDefault();
          router.push("/dashboard/schedule");
        } else if (e.key === "m") {
          e.preventDefault();
          router.push("/dashboard/members");
        } else if (e.key === "d") {
          e.preventDefault();
          router.push("/dashboard");
        }
        return;
      }
      if (e.key === "g") {
        gPressed = true;
        if (gTimer) clearTimeout(gTimer);
        gTimer = setTimeout(() => {
          gPressed = false;
        }, 800);
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      if (gTimer) clearTimeout(gTimer);
    };
  }, [router, pathname]);
}
