"""BABYLON — hygiene, optional STEMIT batches, CRATER with RunLogger progress."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from ix_crate.batch_notify import estimate_minutes
from ix_crate.batch_progress import (
    HUD_TITLE,
    TOOL_ID,
    build_babylon_phases,
    open_music,
    run_with_runlog,
)
from ix_crate.stems_path import ensure_stems_path


def _parse_batches(raw: str | None) -> list[int] | None:
    if not raw or not raw.strip():
        return None
    out = [int(part) for part in raw.split() if part.strip()]
    return out or None


def run(args: argparse.Namespace) -> int:
    batches = _parse_batches(args.stemit_batches)
    lo, hi = estimate_minutes(
        budget=args.budget,
        batches=batches,
        follow=args.follow,
        hygiene=not args.skip_hygiene,
    )
    log_path = args.log.expanduser() if args.log else None
    if log_path:
        print(f"BABYLON log (shell): {log_path}", flush=True)

    print(f"ETA (rough): {lo}–{hi} min wall clock", flush=True)
    print(
        "Mixed In Key may stay open. Rekordbox + Traktor must quit before deck writes.",
        flush=True,
    )

    phases = build_babylon_phases(
        skip_hygiene=args.skip_hygiene,
        skip_crater=args.skip_crater,
        skip_stemit=args.skip_stemit,
        budget=args.budget,
        stemit_batches=batches,
        follow=args.follow,
    )
    if not phases:
        print("nothing to do (all steps skipped)", flush=True)
        return 0

    if not args.skip_hygiene:
        open_music()

    extra: dict = {"babylon_log": str(log_path)} if log_path else {}
    extra["phases"] = [p.name for p in phases]

    code = run_with_runlog(
        tool_id=TOOL_ID,
        title=HUD_TITLE,
        phases=phases,
        extra=extra,
        log_args=args,
    )
    if log_path and args.execute:
        _mirror_run_artifacts(log_path)
    return code


def _mirror_run_artifacts(shell_log: Path) -> None:
    """Copy latest stems run JSON next to the detached shell log when possible."""
    ensure_stems_path()
    from py.utils.paths import LOG_DIR

    jsons = sorted(LOG_DIR.glob("*ix.crate.babylon*.json"), key=lambda p: p.stat().st_mtime)
    if not jsons:
        return
    dest = shell_log.with_suffix(".json")
    try:
        shutil.copy2(jsons[-1], dest)
        print(f"run json (copy): {dest}", flush=True)
    except OSError as exc:
        print(f"run json copy skipped ({exc})", flush=True)


def build_parser() -> argparse.ArgumentParser:
    ensure_stems_path()
    from py.utils.runlog import add_log_flags

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run phases (default dry-run plan only).")
    parser.add_argument("--budget", type=int, default=0, help="STEMIT genre budget (0 = skip factory).")
    parser.add_argument(
        "--stemit-batches",
        default="",
        help="Space-separated STEMIT budgets, e.g. '50 100 200'.",
    )
    parser.add_argument("--skip-hygiene", action="store_true")
    parser.add_argument("--skip-crater", action="store_true")
    parser.add_argument("--skip-stemit", action="store_true")
    parser.add_argument("--follow", action="store_true", help="CRATER runs MusicBrainz + Shazam.")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Detached shell log path (also recorded in run JSON extra).",
    )
    add_log_flags(parser)
    parser.set_defaults(gui=True, notify=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.execute:
        batches = _parse_batches(args.stemit_batches)
        phases = build_babylon_phases(
            skip_hygiene=args.skip_hygiene,
            skip_crater=args.skip_crater,
            skip_stemit=args.skip_stemit,
            budget=args.budget,
            stemit_batches=batches,
            follow=args.follow,
        )
        print(f"dry-run: {len(phases)} phases")
        for spec in phases:
            tag = " (allow fail)" if spec.allow_fail else ""
            cmd = "quit-decks" if spec.name == "quit-decks" else " ".join(spec.argv[3:])
            print(f"  {spec.name}{tag}: {cmd}")
        print("pass --execute to run")
        return 0
    if args.gui is None:
        args.gui = True
    if args.notify is None:
        args.notify = True
    code = run(args)
    if code == 0:
        print("\nReload rekordbox xml (<>). Don't ask again + No on tag overwrite.", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
