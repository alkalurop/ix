"""CRATER — celestial daily crate pass.

One command that refreshes the DJ-facing crates from the live library:

1. **favorites** — play harvest, Played / Not Played But Should, then
   ``MUSIC/GENRES`` (Apple Music library) and ``MUSIC/ACAPELLAS``
   (STEMIT vocals matched to that library).
2. **follow** — MusicBrainz then Shazam for vocals Apple Music did not name;
   rewrites ``MUSIC/ACAPELLAS`` only.
3. **STEMIT sync** — Mixes / Stems / Acapellas / Instrumentals from
   ``stems_audio``.
4. **STEMIT genres** — ``STEMIT/Genres/<Genre>/{Mixes,…}`` into NML + xml.
5. **Music playlists** (optional) — when Music.app is open,
   ``crates --from music --all`` into NML and xml under ``MUSIC/``.
6. **xml prune** — drop rekordbox.xml rows Rekordbox cannot import
   (missing files, ``.m4p``) so the Import Log dialog stops repeating.
7. **rekordbox sample crate** — Pioneer ``Sampler/Capture`` → ``Saved``,
   playlist ``SAMPLES/Samplers`` in NML + xml.
8. **traktor remix crate** — every NML remix set → ``SAMPLES/Remixes/<set>``;
   ``~/Music/Traktor/Samples`` → ``SAMPLES/Remixes/Deck Captures``.
9. **mixed-in-crate** — Mixed In Key user playlists → ``MIXED IN KEY`` in
   NML + xml, with cues, energy, Camelot key, and file notes.

Never writes Apple Music media. Never runs the stem factory. Quit Traktor
before NML. Quit Rekordbox before xml. Dry-run default.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from ix_crate.stems_playlists import REKORDBOX_XML, TRAKTOR_NML, rekordbox_is_running
from ix_crate.traktor_nml import traktor_is_running


def require_xml(xml: Path) -> int:
    """0 when the file parses. A truncated write must not start CRATER."""
    if not xml.is_file():
        print(f"rekordbox.xml not found: {xml}", flush=True)
        return 2
    try:
        ET.parse(xml)
    except ET.ParseError as exc:
        bak = xml.with_suffix(xml.suffix + ".prune.bak")
        print(
            f"rekordbox.xml is not valid XML ({exc}).\n"
            f"  {xml}\n"
            "The file was cut off mid-write. Move it aside and copy the newest "
            f"backup that still parses ({bak.name} is the usual one), then run CRATER again.",
            flush=True,
        )
        return 2
    return 0


def run_favorites(*, execute: bool, force: bool, nml: Path, xml: Path) -> int:
    from ix_crate.favorites import (
        load_saved,
        record_result,
        suggest_playlists,
        write_app_playlists,
        write_json,
        PATTERNS_JSON,
        FAVORITES_JSON,
        format_plan,
    )

    result = record_result(nml=nml, xml=xml, dest=FAVORITES_JSON, merge=True)
    suggestions = suggest_playlists(result.rows, result.fingerprint)
    previous = load_saved(PATTERNS_JSON)
    unchanged = previous.get("fingerprint") == result.fingerprint
    print(format_plan(result.payload, suggestions), flush=True)
    if unchanged and not force:
        print("no new plays since last patterns file.", flush=True)
    if not execute:
        print("dry-run. pass --execute to write favorites JSON and playlists.", flush=True)
        return 0
    write_json(result.payload, FAVORITES_JSON)
    write_json(result.patterns, PATTERNS_JSON)
    print(f"wrote {FAVORITES_JSON}", flush=True)
    print(f"wrote {PATTERNS_JSON}", flush=True)
    if unchanged and previous.get("crates") and not force:
        print("playlist crates stay (fingerprint unchanged). pass --force to rewrite.", flush=True)
        return 0
    written = write_app_playlists(suggestions, nml=nml, xml=xml)
    result.patterns["crates"] = True
    write_json(result.patterns, PATTERNS_JSON)
    print(f"favorites playlists {', '.join(written)}", flush=True)
    return 0


def run_follow(*, execute: bool) -> int:
    if not execute:
        print("dry-run. follow (MusicBrainz / Shazam) skipped.", flush=True)
        return 0
    from ix_crate.library_genres import follow_unmatched

    follow_unmatched()
    return 0


def run_stemit_sync(*, execute: bool) -> int:
    from ix_crate.stems_playlists import format_plan, sync_playlists

    plan = sync_playlists(execute=execute)
    print(format_plan(plan), flush=True)
    if not execute:
        print("dry-run. pass --execute to write STEMIT Mixes/Stems/Acapellas/Instrumentals.", flush=True)
    return 0


def run_stemit_genres(*, execute: bool) -> int:
    from ix_crate.stemit_genres import format_genre_plan, plan_genre_crates, write_genre_report
    from ix_crate.stems_playlists import rebuild_stemit_nml, rebuild_stemit_xml

    plan, _files, _assigned = plan_genre_crates()
    print(format_genre_plan(plan), flush=True)
    write_genre_report(plan, {"execute": execute, "nml": True, "crater": True})
    if not execute:
        print("dry-run. pass --execute to write STEMIT/Genres into NML + xml.", flush=True)
        return 0
    if rekordbox_is_running():
        print("Rekordbox is open. STEMIT/Genres xml skipped.", flush=True)
        return 2
    if traktor_is_running():
        print("Traktor is open. STEMIT/Genres NML skipped.", flush=True)
        return 2
    rebuild_stemit_nml()
    print("STEMIT/Genres rebuilt in NML.", flush=True)
    added = rebuild_stemit_xml()
    print(f"rekordbox.xml STEMIT/Genres written (+{added} collection rows).", flush=True)
    return 0


def run_music_crates(*, execute: bool) -> int:
    from ix_crate.music_dupes import music_running

    if not music_running():
        print("Music.app closed. crates --from music --all skipped.", flush=True)
        return 0
    if not execute:
        print("dry-run. would run crates Music → NML and Music → xml --all.", flush=True)
        return 0
    from ix_crate.crates import main as crates_main

    print("CRATER crates Music → nml --all", flush=True)
    code = crates_main(["--from", "music", "--to", "nml", "--all", "--execute"])
    if code:
        return code
    print("CRATER crates Music → xml --all", flush=True)
    return crates_main(["--from", "music", "--to", "xml", "--all", "--execute"])


def run_rekordbox_sample_crate(*, execute: bool, nml: Path, xml: Path) -> int:
    from ix_crate.rekordbox_sample_crate import run as sample_run

    return sample_run(execute=execute, nml=nml, xml=xml)


def run_traktor_remix_crate(*, execute: bool, nml: Path, xml: Path) -> int:
    from ix_crate.traktor_remix_crate import run as remix_run

    return remix_run(execute=execute, nml=nml, xml=xml)


def run_mixed_in_crate(*, execute: bool, nml: Path, xml: Path) -> int:
    from ix_crate.mixed_in_crate import run as mixed_run

    return mixed_run(execute=execute, nml=nml, xml=xml)


def run_xml_prune(*, execute: bool, xml: Path) -> int:
    from ix_crate.xml_prune import format_plan, prune_xml

    if execute and rekordbox_is_running():
        print("Rekordbox is open. xml prune skipped.", flush=True)
        return 0
    plan = prune_xml(xml, execute=execute)
    print(format_plan(plan), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ix_crate crater", description=__doc__)
    parser.add_argument("--nml", type=Path, default=TRAKTOR_NML)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite favorites playlists even when the play fingerprint is unchanged.",
    )
    parser.add_argument(
        "--skip-follow",
        action="store_true",
        help="Skip MusicBrainz / Shazam for unmatched ACAPELLAS.",
    )
    parser.add_argument(
        "--skip-stemit",
        action="store_true",
        help="Skip STEMIT sync and STEMIT/Genres.",
    )
    parser.add_argument(
        "--skip-music",
        action="store_true",
        help="Skip Music.app user-playlist bridge even if Music is open.",
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print("CRATER  celestial crate pass", flush=True)
    code = require_xml(args.xml)
    if code:
        return code
    if rekordbox_is_running():
        print("note: Rekordbox is open — xml writes will skip.", flush=True)
    if traktor_is_running():
        print("note: Traktor is open — NML writes will skip.", flush=True)

    code = run_favorites(execute=args.execute, force=args.force or args.execute, nml=args.nml, xml=args.xml)
    if code:
        return code

    if not args.skip_follow:
        print("CRATER follow unmatched ACAPELLAS", flush=True)
        code = run_follow(execute=args.execute)
        if code:
            return code

    if not args.skip_stemit:
        print("CRATER STEMIT sync", flush=True)
        code = run_stemit_sync(execute=args.execute)
        if code:
            return code
        print("CRATER STEMIT genres", flush=True)
        code = run_stemit_genres(execute=args.execute)
        if code:
            return code

    if not args.skip_music:
        print("CRATER Music playlists", flush=True)
        code = run_music_crates(execute=args.execute)
        if code:
            return code

    print("CRATER prune dead rekordbox.xml rows", flush=True)
    run_xml_prune(execute=args.execute, xml=args.xml)

    print("CRATER rekordbox Capture → SAMPLES/Samplers", flush=True)
    code = run_rekordbox_sample_crate(execute=args.execute, nml=args.nml, xml=args.xml)
    if code:
        return code
    print("CRATER Traktor remix sets → SAMPLES/Remixes/*", flush=True)
    code = run_traktor_remix_crate(execute=args.execute, nml=args.nml, xml=args.xml)
    if code:
        return code

    print("CRATER Mixed In Key → MIXED IN KEY", flush=True)
    code = run_mixed_in_crate(execute=args.execute, nml=args.nml, xml=args.xml)
    if code:
        return code

    print("CRATER done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
