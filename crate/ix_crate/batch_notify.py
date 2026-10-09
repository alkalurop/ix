"""Completion notify for long shell batches (BABYLON, library hygiene).

Uses the stems factory ``notify_complete`` + local ``box.py`` address — not
raw Mail AppleScript from bash (log tails break ``json.dumps`` in osascript).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ix_crate.paths import REPORTS
from ix_crate.stems_path import ensure_stems_path

TOOL_BABYLON = "ix.crate.babylon"
TOOL_HYGIENE = "ix.crate.hygiene"


def _tail(path: Path, lines: int = 40) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = text.splitlines()
    return "\n".join(rows[-lines:])


def estimate_minutes(
    *,
    budget: int = 0,
    batches: list[int] | None = None,
    follow: bool = False,
    hygiene: bool = True,
) -> tuple[int, int]:
    """Rough wall-clock band (minutes). STEMIT dominates when budget > 0."""
    stem_total = sum(batches or []) if batches else max(0, budget)
    lo = 15 if hygiene else 5
    hi = 45 if hygiene else 20
    if follow:
        lo += 60
        hi += 180
    if stem_total > 0:
        # ~3.5–4.5 min per stem track on this Mac (factory + queue walk).
        lo += int(stem_total * 3.2)
        hi += int(stem_total * 4.5)
    return lo, hi


def build_payload(
    *,
    tool_id: str,
    log_path: Path,
    status: str,
    started_at: float,
    extra: dict | None = None,
) -> dict:
    wall = max(0.0, time.time() - started_at)
    return {
        "tool": tool_id,
        "run_id": log_path.stem,
        "started_at": started_at,
        "ended_at": time.time(),
        "log_path": str(log_path),
        "json_path": "",
        "charts": [],
        "host": {},
        "extra": extra or {},
        "summary": {
            "tracks": 0,
            "results": {
                "pass": 1 if status == "ok" else 0,
                "fail": 1 if status != "ok" else 0,
                "skip": 0,
            },
            "wall_s_total": round(wall, 2),
        },
    }


def finalize_batch(
    *,
    tool_id: str,
    log_path: Path,
    status: str,
    started_at: float,
    title: str,
    summary_line: str,
    extra: dict | None = None,
    notify: bool = True,
) -> int:
    ensure_stems_path()
    from py.utils.notify import notify_complete

    payload = build_payload(
        tool_id=tool_id,
        log_path=log_path,
        status=status,
        started_at=started_at,
        extra=extra,
    )
    json_path = REPORTS / f"{log_path.stem}.json"
    try:
        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        payload["json_path"] = str(json_path)
    except OSError as exc:
        print(f"batch json skipped ({exc})", flush=True)

    minutes = payload["summary"]["wall_s_total"] / 60.0
    body = (
        f"{summary_line}\n\n"
        f"status: {status}\n"
        f"wall: {minutes:.0f} min\n"
        f"log: {log_path}\n"
    )
    tail = _tail(log_path)
    if tail:
        body += f"\n--- log tail ---\n{tail}\n"
    if notify:
        notify_complete(title=tool_id, body=body, payload=payload)
    else:
        print(body, flush=True)
    return 0 if status == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-id", default=TOOL_HYGIENE)
    parser.add_argument("--title", default="Library hygiene")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--status", choices=("ok", "fail"), required=True)
    parser.add_argument("--started-at", type=float, required=True)
    parser.add_argument("--summary", default="Batch finished.")
    parser.add_argument("--no-notify", action="store_true")
    parser.add_argument("--extra-json", default="")
    args = parser.parse_args(argv)
    extra = json.loads(args.extra_json) if args.extra_json.strip() else None
    return finalize_batch(
        tool_id=args.tool_id,
        log_path=args.log.expanduser(),
        status=args.status,
        started_at=args.started_at,
        title=args.title,
        summary_line=args.summary,
        extra=extra,
        notify=not args.no_notify,
    )


if __name__ == "__main__":
    sys.exit(main())
