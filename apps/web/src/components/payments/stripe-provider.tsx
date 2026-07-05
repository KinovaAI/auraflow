"use client";

import { useMemo } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements } from "@stripe/react-stripe-js";

const stripeKey = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;

export function StripeProvider({ children }: { children: React.ReactNode }) {
  const stripePromise = useMemo(
    () => (stripeKey ? loadStripe(stripeKey) : null),
    []
  );

  if (!stripePromise) {
    return <>{children}</>;
  }

  return (
    <Elements
      stripe={stripePromise}
      options={{
        appearance: {
          theme: "stripe",
          variables: {
            colorPrimary: "#4f46e5",
            borderRadius: "8px",
          },
        },
      }}
    >
      {children}
    </Elements>
  );
}
