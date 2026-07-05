"""AuraFlow — CSV export utility for external API responses.

Produces a streaming CSV download from a list of row dicts.
Handles None values, datetime, and UUID serialization.
"""
import csv
import io
from datetime import datetime, date
from typing import Any
from uuid import UUID

from fastapi.responses import StreamingResponse


def _serialize_value(value: Any) -> str:
    """Convert a single value to a CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "; ".join(_serialize_value(v) for v in value)
    return str(value)


def export_csv(
    rows: list[dict],
    columns: list[tuple[str, str]],
    filename: str,
) -> StreamingResponse:
    """Build a streaming CSV response.

    Args:
        rows:     List of dicts (e.g. from DB fetch).
        columns:  List of (field_name, header_label) tuples defining column
                  order and human-readable headers.
        filename: Value for the Content-Disposition attachment filename.

    Returns:
        A FastAPI StreamingResponse with text/csv content type.
    """
    def _generate():
        buf = io.StringIO()
        writer = csv.writer(buf)

        # Header row
        writer.writerow([label for _, label in columns])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        # Data rows
        for row in rows:
            writer.writerow(
                [_serialize_value(row.get(field)) for field, _ in columns]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    safe_filename = filename.replace('"', "'")

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
        },
    )
