"""STEMIT walk across Music.app genres, N stem jobs per run.

Starts at ``--start`` (default African). Skips genres that never stem
(Acapella) or are finished (Rock). One queue, one factory. Re-running
picks up where the last run stopped: a track that already has
``.stem.m4a`` is skipped.

Does not write Traktor NML or rekordbox.xml. CRATER does that after the
decks quit. Never writes Apple Music media.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

from ix_crate.music_dupes import MusicDupesError
from ix_crate.music_fix import dump_genre
from ix_crate.paths import REPORTS
from ix_crate.stemit import (
    execute_links,
    plan_playlist,
    run_factory,
    write_queue,
    write_stemit_report,
)

SKIP_GENRES = {"acapella", "rock"}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def library_genres() -> list[str]:
    script = 'tell application "Music" to get genre of every file track of library playlist 1'
    out = subprocess.check_output(["osascript", "-e", script], text=True, timeout=600)
    names = {part.strip() for part in out.split(", ") if part.strip()}
    return sorted(names, key=str.casefold)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ix_crate stemit-chain", description=__doc__)
    parser.add_argument("--start", default="African")
    parser.add_argument("--budget", type=int, default=200)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="STEM factory in terminal only (BABYLON keeps one HUD).",
    )
    args = parser.parse_args(argv)

    try:
        genres = library_genres()
    except (MusicDupesError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        print("Open Music.app and run again.", file=sys.stderr)
        return 2
    start = next(
        (i for i, genre in enumerate(genres) if genre.casefold() == args.start.casefold()),
        None,
    )
    if start is None:
        print(f"genre {args.start!r} not in library", file=sys.stderr)
        return 2

    jobs: list[dict] = []
    seen: set[str] = set()
    per_genre: list[tuple[str, int, int]] = []
    last = ""
    for genre in genres[start:]:
        if genre.casefold() in SKIP_GENRES:
            continue
        payload = plan_playlist(f"genre:{genre}", rows=dump_genre(genre))
        took = 0
        for job in payload["jobs"]:
            if job["action"] != "stem" or job["dest"] in seen:
                continue
            if len(jobs) >= args.budget:
                break
            seen.add(job["dest"])
            jobs.append(job)
            took += 1
        per_genre.append((genre, payload["stem"], took))
        print(
            f"{utc()} {genre}: {payload['tracks']} tracks  {payload['stem']} to stem  queued {took}",
            flush=True,
        )
        last = genre
        if len(jobs) >= args.budget:
            break

    payload = {
        "tool": "ix.crate.stemit",
        "playlist": f"genre-chain:{args.start}..{last}",
        "tracks": len(jobs),
        "stem": len(jobs),
        "skip": 0,
        "jobs": jobs,
        "genres": [{"genre": genre, "open": open_, "queued": took} for genre, open_, took in per_genre],
    }
    print(f"queued {len(jobs)} across {len(per_genre)} genres ({args.start} → {last})", flush=True)
    if not jobs:
        print("nothing left to stem.", flush=True)
        return 0
    if not args.execute:
        write_stemit_report(payload)
        print("dry-run. pass --execute to hardlink and run the factory.")
        return 0

    execute_links(payload)
    queue = write_queue(payload["jobs"], playlist=f"genre-chain-{args.start}-{last}")
    payload["queue"] = str(queue)
    payload["execute"] = True
    report = write_stemit_report(payload)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "stemit-genre-chain-next.json").write_text(
        json.dumps({"last_genre": last, "at": utc(), "report": str(report)}, indent=2),
        encoding="utf-8",
    )
    print(f"linked {payload.get('linked', 0)}  queue {queue}", flush=True)
    return run_factory(queue, execute=True, gui=not args.no_gui)


if __name__ == "__main__":
    raise SystemExit(main())
