"""HTML → PDF rendering for signed workshop contracts.

Uses weasyprint. Requires apt: libcairo2 libpango-1.0-0 libpangoft2-1.0-0
(added to the production stage of apps/api/Dockerfile).
"""
from __future__ import annotations

import asyncio


async def render_contract_pdf(html: str) -> bytes:
    """Render the given HTML to a PDF, returning the bytes.

    weasyprint is sync + can be slow on large docs, so we run it in a thread
    so we don't block the event loop.
    """
    return await asyncio.to_thread(_render_sync, html)


def _render_sync(html: str) -> bytes:
    # Import inside so unit tests + imports of contract_service don't pull in
    # weasyprint unless we're actually rendering.
    from weasyprint import HTML
    return HTML(string=html).write_pdf()
