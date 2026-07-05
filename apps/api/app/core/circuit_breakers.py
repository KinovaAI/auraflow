"""
AuraFlow — Circuit Breakers for outbound integrations

Wraps every third-party API client in a pybreaker. When an integration starts
failing (5xx, timeouts) past the threshold, further calls fail fast with
`pybreaker.CircuitBreakerError` instead of hanging on timeouts and dragging
down request latency for unrelated traffic.

Usage in service modules::

    from app.core.circuit_breakers import stripe_breaker

    @stripe_breaker
    async def _stripe_call(...):
        ...

Breaker state is exported as a Prometheus gauge so on-call can see which
integrations are degraded at a glance.

Per-integration tuning — conservative defaults chosen so that a legitimate
hiccup (e.g. 3-second Stripe blip) doesn't trip the breaker but a genuine
outage stops the bleeding within ~30 seconds.
"""
from __future__ import annotations

from typing import Any

import pybreaker
from app.core.logging import logger


# Lazy prometheus gauge — only wire it up if prometheus_client is installed.
_state_gauge: Any = None
try:
    from prometheus_client import Gauge
    _state_gauge = Gauge(
        "auraflow_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=half-open, 2=open)",
        ["integration"],
    )
except ImportError:
    pass


class _LoggingListener(pybreaker.CircuitBreakerListener):
    """Mirror breaker state transitions into structured logs + Prometheus."""

    def __init__(self, name: str):
        self.name = name

    def state_change(self, cb, old_state, new_state):  # type: ignore[override]
        logger.warning(
            "Circuit breaker state change",
            integration=self.name,
            old_state=old_state.name,
            new_state=new_state.name,
        )
        if _state_gauge is not None:
            mapping = {"closed": 0, "half-open": 1, "open": 2}
            _state_gauge.labels(integration=self.name).set(
                mapping.get(new_state.name, 0)
            )

    def failure(self, cb, exc):  # type: ignore[override]
        logger.info(
            "Circuit breaker recorded failure",
            integration=self.name,
            exception=type(exc).__name__,
        )


def _make(name: str, *, fail_max: int = 5, reset_timeout: int = 60) -> pybreaker.CircuitBreaker:
    return pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        name=name,
        listeners=[_LoggingListener(name)],
        # Don't count these as failures — they indicate programmer error, not
        # the remote service being down. Adjust per-integration if needed.
        exclude=[ValueError, TypeError, KeyError],
    )


# ── Payment ───────────────────────────────────────────────────────────────────
stripe_breaker = _make("stripe", fail_max=5, reset_timeout=60)

# ── Video + Streaming ────────────────────────────────────────────────────────
zoom_breaker = _make("zoom", fail_max=5, reset_timeout=90)
mux_breaker = _make("mux", fail_max=5, reset_timeout=60)

# ── Messaging ─────────────────────────────────────────────────────────────────
twilio_breaker = _make("twilio", fail_max=5, reset_timeout=60)
sendgrid_breaker = _make("sendgrid", fail_max=5, reset_timeout=60)
purelymail_smtp_breaker = _make("purelymail_smtp", fail_max=10, reset_timeout=120)

# ── AI ────────────────────────────────────────────────────────────────────────
openai_breaker = _make("openai", fail_max=3, reset_timeout=30)
anthropic_breaker = _make("anthropic", fail_max=3, reset_timeout=30)

# ── Marketing / Integrations ──────────────────────────────────────────────────
mailchimp_breaker = _make("mailchimp", fail_max=5, reset_timeout=120)
meta_ads_breaker = _make("meta_ads", fail_max=5, reset_timeout=120)
google_ads_breaker = _make("google_ads", fail_max=5, reset_timeout=120)

# ── Storage + EMR ─────────────────────────────────────────────────────────────
backblaze_breaker = _make("backblaze", fail_max=5, reset_timeout=120)
emr_breaker = _make("emr", fail_max=5, reset_timeout=120)
fhir_breaker = _make("fhir", fail_max=5, reset_timeout=120)


__all__ = [
    "stripe_breaker",
    "zoom_breaker",
    "mux_breaker",
    "twilio_breaker",
    "sendgrid_breaker",
    "purelymail_smtp_breaker",
    "openai_breaker",
    "anthropic_breaker",
    "mailchimp_breaker",
    "meta_ads_breaker",
    "google_ads_breaker",
    "backblaze_breaker",
    "emr_breaker",
    "fhir_breaker",
]
