from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ...auth import Identity
from ..dependencies import require_human_full_control_read, services


router = APIRouter(prefix="/logs", tags=["logs"])


def _bounds(period: str) -> tuple[str | None, str | None]:
    if period == "all":
        return None, None
    durations = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "365d": timedelta(days=365)}
    if period not in durations:
        raise HTTPException(status_code=400, detail="Periodo de registro no válido")
    now = datetime.now(timezone.utc)
    return (now - durations[period]).isoformat().replace("+00:00", "Z"), now.isoformat().replace("+00:00", "Z")


def _read(
    request: Request,
    limit: int,
    cursor: str | None,
    from_at: str | None,
    to_at: str | None,
    level: str | None,
    actor: str | None,
    node: str | None,
    action: str | None,
    source: str | None,
    result: str | None,
) -> dict:
    try:
        return services(request).store.read_audit_page(limit, cursor, from_at, to_at, level, actor, node, action, source, result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("")
def list_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    from_at: str | None = Query(default=None, alias="from"),
    to_at: str | None = Query(default=None, alias="to"),
    level: str | None = None,
    actor: str | None = None,
    node: str | None = None,
    action: str | None = None,
    source: str | None = None,
    result: str | None = None,
    _: Identity = Depends(require_human_full_control_read),
) -> dict:
    return _read(request, limit, cursor, from_at, to_at, level, actor, node, action, source, result)


@router.get("/export")
def export_logs(
    request: Request,
    period: str = Query("all", alias="range"),
    output_format: str = Query("jsonl", alias="format"),
    from_at: str | None = Query(default=None, alias="from"),
    to_at: str | None = Query(default=None, alias="to"),
    level: str | None = None,
    actor: str | None = None,
    node: str | None = None,
    action: str | None = None,
    source: str | None = None,
    result: str | None = None,
    _: Identity = Depends(require_human_full_control_read),
) -> Response:
    if output_format not in {"jsonl", "csv"}:
        raise HTTPException(status_code=400, detail="Formato de registro no válido")
    period_from, period_to = _bounds(period)
    items: list[dict] = []
    cursor: str | None = None
    while True:
        page = _read(request, 200, cursor, period_from or from_at, period_to or to_at, level, actor, node, action, source, result)
        items.extend(page["items"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    if output_format == "jsonl":
        content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
        media_type = "application/x-ndjson"
    else:
        buffer = io.StringIO()
        fields = ["timestamp", "level", "source", "actor", "node", "action", "result", "entity_type", "entity_id", "event_id", "operation_id"]
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)
        content = buffer.getvalue()
        media_type = "text/csv; charset=utf-8"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="rtfm-{period}.{output_format}"'})
