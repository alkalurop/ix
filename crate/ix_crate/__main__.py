"""ix crate — identify and rehome untagged stems_audio files.

Cascade: filename → tags → iTunes/Deezer → MusicBrainz → Ollama → Compilations/Mashups/Miscellaneous.
Dry-run is the default. Reports land in ~/local_tools/crate/reports (off git).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ix_crate.plan import (
    execute_moves,
    plan_mashups,
    plan_outliers,
    plan_unknown_album,
    write_report,
)
from ix_crate.safety import CrateSafetyError


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "music-dupes":
        from ix_crate.music_dupes import main as music_dupes_main

        return music_dupes_main(argv[1:])
    if argv and argv[0] == "music-repair":
        from ix_crate.music_repair import main as music_repair_main

        return music_repair_main(argv[1:])
    if argv and argv[0] == "music-replicants":
        from ix_crate.music_replicants import main as music_replicants_main

        return music_replicants_main(argv[1:])
    if argv and argv[0] == "music-genre":
        from ix_crate.music_genre import main as music_genre_main

        return music_genre_main(argv[1:])
    if argv and argv[0] == "consolidate":
        from ix_crate.consolidate import main as consolidate_main

        return consolidate_main(argv[1:])
    if argv and argv[0] == "music-reconcile":
        from ix_crate.music_reconcile import main as music_reconcile_main

        return music_reconcile_main(argv[1:])
    if argv and argv[0] == "music-fix":
        from ix_crate.music_fix import main as music_fix_main

        return music_fix_main(argv[1:])
    if argv and argv[0] == "stemit":
        from ix_crate.stemit import main as stemit_main

        return stemit_main(argv[1:])
    if argv and argv[0] == "riff-repair":
        from ix_crate.riff_repair import main as riff_repair_main

        return riff_repair_main(argv[1:])
    if argv and argv[0] == "music-cull":
        from ix_crate.music_cull import main as music_cull_main

        return music_cull_main(argv[1:])
    if argv and argv[0] == "music-playlist":
        from ix_crate.music_playlist import main as music_playlist_main

        return music_playlist_main(argv[1:])
    if argv and argv[0] == "music-organize":
        from ix_crate.music_organize import main as music_organize_main

        return music_organize_main(argv[1:])
    if argv and argv[0] == "traktor-nml":
        from ix_crate.traktor_nml import main as traktor_nml_main

        return traktor_nml_main(argv[1:])
    if argv and argv[0] == "crates":
        from ix_crate.crates import main as crates_main

        return crates_main(argv[1:])
    if argv and argv[0] == "favorites":
        from ix_crate.favorites import main as favorites_main

        return favorites_main(argv[1:])
    if argv and argv[0] == "crater":
        from ix_crate.crater import main as crater_main

        return crater_main(argv[1:])

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "unknown-album",
            "outliers",
            "mashups",
            "music-dupes",
            "music-repair",
            "music-reconcile",
            "music-genre",
            "music-replicants",
            "music-fix",
            "stemit",
            "consolidate",
            "riff-repair",
            "music-cull",
            "music-organize",
            "music-playlist",
            "traktor-nml",
            "crates",
            "favorites",
            "crater",
        ),
        help=(
            "Scan Unknown Album, re-ID Inbox, sort mashups, drop Music.app "
            "same-file rows, drop same-audio rows under two filenames, "
            "promote EDM, … genres, locate missing files, relink dead rows "
            "from the iTunes XML, pull audio into ~/Music, fill a playlist's "
            "identity, name Media.localized files from Music.app metadata, "
            "STEMIT a playlist into stems_audio, repair Traktor NML "
            "playlist dupes and missing artwork IDs, sync playlist "
            "membership between Music.app, Traktor NML, and rekordbox.xml, "
            "record play counts into configs/favorites.json, or run CRATER "
            "(daily celestial crate pass)."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform moves. Default is dry-run.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Filename + tags only. No catalogs or Ollama.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Override stems_audio root (must stay under ~/Music/stems_audio).",
    )
    args = parser.parse_args(argv)
    planners = {
        "unknown-album": plan_unknown_album,
        "outliers": plan_outliers,
        "mashups": plan_mashups,
    }
    planner = planners[args.command]

    try:
        payload = planner(args.root, lookup=not args.offline)
    except CrateSafetyError as exc:
        print(exc, file=sys.stderr)
        return 2

    report = write_report(payload)
    print(
        f"{payload['families']} families, {payload['files']} files, "
        f"sources={payload['sources']}, outliers={payload['outliers']}"
    )
    if payload.get("unknown_in_dest"):
        print(f"WARNING: Unknown still in dest paths: {len(payload['unknown_in_dest'])}")
    print(f"report: {report}")
    if not args.execute:
        print("dry-run. pass --execute to move families together.")
        return 0

    moved = execute_moves(payload)
    print(f"moved {moved} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
