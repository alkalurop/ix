"""STEMIT — Music.app playlist → stems_audio hardlink → local STEM factory.

Hardlink the mix into ``~/Music/stems_audio/Artist/Album/``, then run
[ixamal/stems](https://github.com/ixamal/stems) ``py.exec.separate``
(Mel pair + ``.stem.m4a``) with the Aqua HUD (``py.utils.progress``).

Never writes Apple Music ``Media.localized``. Acapellas stay in
``stems_audio`` — they are not pushed back to Music.app. ``--genre`` takes
exact Music.app genre in library order; ``--limit`` caps that list (or a
``--playlist``). ``--sync-playlists``
rewrites Traktor and Rekordbox crates from ``stems_audio`` in any state
(factory or not): Mixes / Stems / Acapellas / Instrumentals. Files not
yet imported get a collection location row. Analyze stays in-app.
``--fix-role-titles`` fills Title = vocals from the mix sibling / folder
onto owned ``.mp3`` / ``.m4a``. ``--fix-industry-artists`` fills artist
on Industry Stems WAV packs from the crate, patches Traktor NML, and
keeps one STEMIT playlist row per identity. ``--fix-titles`` pretties Beatport catalog TITLEs in NML and drops
Google Drive shortcut rows. ``--genres`` promotes STEMIT/Genres into ``rekordbox.xml`` from the
current NML. NML stays unless ``--nml``. Never mutagen-writes
``.stem.m4a``. Never stems Acapella. Skip if
that Artist/Album/Title already has a ``.stem.m4a``. Dry-run is the
default.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ix_crate.families import is_role_file
from ix_crate.identify import sanitize
from ix_crate.music_dupes import MusicDupesError
from ix_crate.music_fix import dump_genre, dump_playlist
from ix_crate.music_repair import RepairRow, SKIP_SUFFIX
from ix_crate.paths import REPORTS, STEMS_AUDIO
from ix_crate.safety import CrateSafetyError, assert_under_stems
from ix_crate.stems_path import STEMS_REPO, ensure_stems_path

HUD_TITLE = "STEMIT"
TOOL_ID = "ix.crate.stemit"
QUEUE_DIR = REPORTS.parent / "stemit-queues"
ACAPELLA = re.compile(r"\b(?:a\s*c+ap+ella|acapella|cappella)\b", re.I)
OWNED_EXT = {".mp3", ".m4a", ".wav", ".aiff", ".aif", ".flac"}


def is_acapella_row(row: RepairRow) -> bool:
    blob = " ".join(
        part
        for part in (row.genre, row.name, row.album, Path(row.location).name)
        if part
    )
    return bool(ACAPELLA.search(blob))


def dest_mix(row: RepairRow, *, stems_root: Path | None = None) -> Path:
    root = (stems_root or STEMS_AUDIO).expanduser()
    src = Path(row.location)
    artist = sanitize(row.artist, "Unknown Artist")
    album = sanitize(row.album, "Singles")
    return root / artist / album / src.name


def stem_sibling(mix: Path) -> Path:
    return mix.with_name(f"{mix.stem}.stem.m4a")


def skip_reason(row: RepairRow, *, stems_root: Path | None = None) -> str:
    loc = (row.location or "").strip()
    if not loc:
        return "no file"
    src = Path(loc)
    if any(src.name.lower().endswith(suffix) for suffix in SKIP_SUFFIX):
        return "skip stem or m4p"
    if src.suffix.lower() not in OWNED_EXT:
        return f"skip {src.suffix or 'unknown type'}"
    if not src.is_file():
        return "missing on disk"
    if is_role_file(src):
        return "role file"
    if is_acapella_row(row):
        return "acapella"
    dest = dest_mix(row, stems_root=stems_root)
    if stem_sibling(dest).is_file():
        return "already has .stem.m4a"
    return ""


def plan_playlist(
    playlist: str,
    *,
    stems_root: Path | None = None,
    rows: list[RepairRow] | None = None,
) -> dict[str, Any]:
    rows = list(rows if rows is not None else dump_playlist(playlist))
    jobs: list[dict[str, Any]] = []
    for row in rows:
        reason = skip_reason(row, stems_root=stems_root)
        dest = dest_mix(row, stems_root=stems_root) if row.location else Path()
        jobs.append(
            {
                "persistent_id": row.persistent_id,
                "artist": row.artist,
                "album": row.album,
                "name": row.name,
                "genre": row.genre,
                "source": row.location,
                "dest": str(dest) if row.location else "",
                "action": "skip" if reason else "stem",
                "reason": reason,
            }
        )
    return {
        "tool": TOOL_ID,
        "playlist": playlist,
        "tracks": len(jobs),
        "stem": sum(1 for job in jobs if job["action"] == "stem"),
        "skip": sum(1 for job in jobs if job["action"] == "skip"),
        "jobs": jobs,
    }


def write_stemit_report(payload: dict[str, Any]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = REPORTS / f"stemit-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def _same_inode(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_ino == right.stat().st_ino and left.stat().st_dev == right.stat().st_dev
    except OSError:
        return False


def hardlink_mix(source: Path, dest: Path) -> str:
    """Link Media.localized (or other) mix into stems_audio. Never copy Apple Music."""
    src = source.expanduser()
    dest = dest.expanduser()
    assert_under_stems(dest)
    if dest.exists() and _same_inode(src, dest):
        return "already-linked"
    if dest.exists():
        raise CrateSafetyError(f"dest exists and is not this mix: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.link(src, dest)
    return "linked"


def write_queue(jobs: list[dict[str, Any]], *, playlist: str) -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^\w]+", "-", playlist).strip("-").lower() or "playlist"
    dest = QUEUE_DIR / f"{stamp}-{slug}.m3u"
    lines = ["#EXTM3U"]
    for job in jobs:
        if job["action"] != "stem":
            continue
        lines.append(job["dest"])
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def factory_python() -> Path:
    ensure_stems_path()
    python = STEMS_REPO / ".venv" / "bin" / "python"
    if not python.is_file():
        raise FileNotFoundError(
            f"stems factory venv missing ({python}). Use Homebrew Python 3.12 .venv in ixamal/stems."
        )
    return python


def factory_env() -> dict[str, str]:
    """Same as stems RUNBOOK: ``export PATH="$PWD/.venv/bin:$PATH``."""
    python = factory_python()
    env = os.environ.copy()
    env["PATH"] = f"{python.parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def run_factory(queue: Path, *, execute: bool) -> int:
    python = factory_python()
    env = factory_env()
    cmd = [str(python), "-m", "py.exec.separate", "--path", str(queue)]
    if execute:
        cmd.append("--execute")
    print("factory", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=STEMS_REPO, env=env, check=False)
    return completed.returncode


def execute_links(payload: dict[str, Any]) -> dict[str, Any]:
    linked = 0
    for job in payload["jobs"]:
        if job["action"] != "stem":
            continue
        try:
            result = hardlink_mix(Path(job["source"]), Path(job["dest"]))
        except CrateSafetyError as exc:
            job["action"] = "skip"
            job["reason"] = str(exc)
            continue
        job["link"] = result
        linked += 1
    payload["linked"] = linked
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--playlist",
        default="",
        help="Music.app playlist name (exact). Required unless --genre, --sync-playlists, --fix-role-titles, --fix-titles, --fix-industry-artists, --genres, --dedupe, or --drop-copies.",
    )
    parser.add_argument(
        "--genre",
        default="",
        help="Music.app genre (exact). First tracks in library order. Use with --limit.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap source tracks from --playlist or --genre (0 = all).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip this many source tracks (library order). Use with --limit for the next page.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Hardlink mixes into stems_audio and run py.exec.separate with HUD.",
    )
    parser.add_argument(
        "--no-factory",
        action="store_true",
        help="Hardlink only. Do not launch the STEM factory.",
    )
    parser.add_argument(
        "--sync-playlists",
        action="store_true",
        help="Rewrite Traktor/Rekordbox STEMIT crates from stems_audio in any state (no factory).",
    )
    parser.add_argument(
        "--fix-role-titles",
        action="store_true",
        help="Fill vocals/instrumental titles from sibling mix + folder onto mp3/m4a (never wav).",
    )
    parser.add_argument(
        "--fix-titles",
        action="store_true",
        help="Pretty Beatport catalog titles in collection.nml and drop Google Drive shortcut rows.",
    )
    parser.add_argument(
        "--fix-industry-artists",
        action="store_true",
        help="Resolve Industry Stems artists from the crate, then drop STEMIT crate identity dupes.",
    )
    parser.add_argument(
        "--genres",
        action="store_true",
        help="Promote STEMIT/Genres into rekordbox.xml from current NML keepers. NML stays unless --nml.",
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="Delete confirmed stems_audio copies (Mashups dumps, Unknown Album, same-audio twins) and rebuild STEMIT crates.",
    )
    parser.add_argument(
        "--drop-copies",
        action="store_true",
        help="Delete Finder (2)/(3) copies with the same title+artist role, drop missing NML rows, rebuild STEMIT.",
    )
    parser.add_argument(
        "--nml",
        action="store_true",
        help="With --fix-role-titles, --fix-industry-artists, or --genres, also patch collection.nml. Quit Traktor first.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="With --fix-industry-artists, crate match only (no iTunes/Deezer/MusicBrainz).",
    )
    args = parser.parse_args(argv)

    if args.fix_titles:
        from ix_crate.role_titles import (
            apply_nml_store_titles,
            format_store_title_plan,
            plan_nml_store_titles,
            traktor_is_running,
            write_role_report,
        )

        fixes = plan_nml_store_titles()
        print(format_store_title_plan(fixes), flush=True)
        write_role_report(
            [],
            {
                "tool": "ix.crate.stemit-titles",
                "execute": args.execute,
                "titles": [
                    {"path": item.path, "old": item.old, "new": item.new, "cloud": item.cloud}
                    for item in fixes
                ],
            },
        )
        if args.execute and traktor_is_running():
            print("Traktor is open. Quit it before --execute writes collection.nml.", flush=True)
            return 2
        if not args.execute:
            print(
                "dry-run. pass --execute to pretty Beatport TITLEs and drop CloudStorage rows. "
                "File names stay. Never writes Apple Music.",
                flush=True,
            )
            return 0
        titled, dropped = apply_nml_store_titles(fixes, execute=True)
        print(
            f"patched {titled} titles  dropped {dropped} cloud rows. Reopen Traktor.",
            flush=True,
        )
        return 0

    if args.genres:
        from ix_crate.stemit_genres import (
            format_genre_plan,
            plan_genre_crates,
            write_genre_report,
        )
        from ix_crate.role_titles import traktor_is_running
        from ix_crate.stems_playlists import rebuild_stemit_nml, rebuild_stemit_xml, rekordbox_is_running

        plan, _files, _assigned = plan_genre_crates()
        print(format_genre_plan(plan), flush=True)
        report = write_genre_report(plan, {"execute": args.execute, "nml": args.nml})
        print(f"report: {report}", flush=True)
        if args.execute and rekordbox_is_running():
            print("Rekordbox is open. Quit it before --execute writes rekordbox.xml.", flush=True)
            return 2
        if args.execute and args.nml and traktor_is_running():
            print("Traktor is open. Quit it before --nml --execute writes collection.nml.", flush=True)
            return 2
        if not args.execute:
            print(
                "dry-run. pass --execute to write STEMIT/Genres into rekordbox.xml. "
                "NML stays unless --nml. Never writes wav or .stem.m4a tags.",
                flush=True,
            )
            return 0
        if args.nml:
            rebuild_stemit_nml()
            print("STEMIT/Genres rebuilt in NML.", flush=True)
        added = rebuild_stemit_xml()
        print(
            f"rekordbox.xml STEMIT/Genres written (+{added} collection rows). "
            "Reopen Rekordbox and refresh the XML crate (or drag STEMIT in).",
            flush=True,
        )
        return 0

    if args.drop_copies:
        from ix_crate.stemit_dupes import (
            apply_disk_dupes,
            format_dedupe_plan,
            plan_finder_copies,
            rebuild_after_dedupe,
            write_dedupe_report,
        )
        from ix_crate.role_titles import traktor_is_running

        plan = plan_finder_copies()
        print(format_dedupe_plan(plan), flush=True)
        write_dedupe_report(plan, {"execute": args.execute, "mode": "finder-copies"})
        if args.execute and traktor_is_running():
            print("Traktor is open. Quit it before --execute deletes files and writes collection.nml.", flush=True)
            return 2
        if not args.execute:
            print(
                "dry-run. pass --execute to delete Finder (2) copies and drop missing NML rows. "
                "Mix / stem / vocals / instrumental stay four files. Live vs studio stays.",
                flush=True,
            )
            return 0

        def on_delete(index: int, total: int, name: str, crate: str) -> None:
            print(f"  drop  {index}/{total}  {crate}  {name}", flush=True)

        deleted = apply_disk_dupes(plan, on_progress=on_delete)
        added = rebuild_after_dedupe(plan)
        write_dedupe_report(
            plan,
            {"execute": True, "mode": "finder-copies", "deleted": deleted, "stemit_added": added},
        )
        print(
            f"deleted {deleted}  pruned {plan.pruned} empty folders. STEMIT rebuilt. Reopen Traktor.",
            flush=True,
        )
        return 0

    if args.dedupe:
        from ix_crate.stemit_dupes import (
            apply_disk_dupes,
            format_dedupe_plan,
            plan_disk_dupes,
            rebuild_after_dedupe,
            write_dedupe_report,
        )
        from ix_crate.role_titles import traktor_is_running

        def on_progress(index: int, total: int, name: str, crate: str) -> None:
            print(f"  group  {index}/{total}  {crate}  {name[:80]}", flush=True)

        plan = plan_disk_dupes(on_progress=on_progress)
        print(format_dedupe_plan(plan), flush=True)
        report = write_dedupe_report(plan, {"execute": args.execute})
        print(f"report: {report}", flush=True)
        if args.execute and traktor_is_running():
            print("Traktor is open. Quit it before --execute deletes files and writes collection.nml.", flush=True)
            return 2
        if not args.execute:
            print(
                "dry-run. pass --execute to delete confirmed copies under stems_audio and rebuild STEMIT. "
                "Unique mashups and Industry Stems WAV packs stay.",
                flush=True,
            )
            return 0

        def on_delete(index: int, total: int, name: str, crate: str) -> None:
            print(f"  drop  {index}/{total}  {crate}  {name}", flush=True)

        deleted = apply_disk_dupes(plan, on_progress=on_delete)
        added = rebuild_after_dedupe(plan)
        write_dedupe_report(
            plan,
            {"execute": True, "deleted": deleted, "stemit_added": added},
        )
        print(
            f"deleted {deleted}  pruned {plan.pruned} empty folders. STEMIT rebuilt. Reopen Traktor.",
            flush=True,
        )
        return 0

    if args.fix_industry_artists:
        from ix_crate.industry_stems import (
            apply_industry_plan,
            build_industry_plan,
            format_industry_plan,
            traktor_is_running,
            write_applescript_tsv,
            write_industry_report,
        )
        from ix_crate.stems_playlists import rekordbox_is_running

        def on_progress(index: int, total: int, name: str, artist: str, source: str) -> None:
            label = artist or "unresolved"
            print(f"  pack  {index}/{total}  {label} — {name}  ({source})", flush=True)

        plan = build_industry_plan(lookup=not args.offline, on_progress=on_progress)
        tsv = write_applescript_tsv(plan.fixes)
        print(format_industry_plan(plan), flush=True)
        print(f"applescript tsv: {tsv}", flush=True)
        write_industry_report(plan, {"execute": args.execute, "applescript_tsv": str(tsv)})
        if not args.execute:
            print(
                "dry-run. pass --execute to patch Traktor + rekordbox.xml ARTIST "
                "(AcoustID / MusicBrainz / Shazam on leftovers). WAV tags stay untouched. "
                "Music.app has 0 IndustryStems rows.",
                flush=True,
            )
            return 0
        if traktor_is_running():
            print("Traktor is open — NML skipped. Quit it to patch collection.nml.", flush=True)
        if rekordbox_is_running():
            print("Rekordbox is open — xml skipped. Quit it to patch rekordbox.xml.", flush=True)
        apply_industry_plan(plan)
        write_industry_report(
            plan,
            {
                "execute": True,
                "applescript_tsv": str(tsv),
                "nml_patched": plan.nml_patched,
                "xml_patched": plan.xml_patched,
                "stemit_rebuilt": not traktor_is_running(),
            },
        )
        print(
            f"patched nml {plan.nml_patched}  xml {plan.xml_patched}. "
            "Reload the sidecar that was closed.",
            flush=True,
        )
        return 0

    if args.fix_role_titles:
        from ix_crate.role_titles import (
            apply_role_tags,
            format_role_plan,
            patch_nml_titles,
            plan_role_titles,
            traktor_is_running,
            write_role_report,
        )

        fixes = plan_role_titles()
        extra = {"execute": args.execute, "nml": args.nml, "traktor_running": traktor_is_running()}
        report = write_role_report(fixes, extra)
        print(format_role_plan(fixes), flush=True)
        print(f"report: {report}", flush=True)
        if args.nml and traktor_is_running():
            print("Traktor is open. Quit it before --nml --execute. Disk tags can still run.", flush=True)
            if args.execute:
                written = apply_role_tags(fixes)
                print(f"wrote {written} file tags. NML skipped.", flush=True)
                return 0
            print("dry-run. pass --execute to write mp3/m4a tags.", flush=True)
            return 0
        if not args.execute:
            print(
                "dry-run. pass --execute to write mp3/m4a tags"
                + (" and patch collection.nml." if args.nml else "."),
                flush=True,
            )
            return 0
        written = apply_role_tags(fixes)
        print(f"wrote {written} file tags.", flush=True)
        if args.nml:
            patched = patch_nml_titles(fixes, execute=True)
            print(f"patched {patched} Traktor NML titles. Reopen Traktor, then DJCU2 to Rekordbox.", flush=True)
        else:
            print("disk tags only. Quit Traktor, then --fix-role-titles --nml --execute. Then DJCU2.", flush=True)
        return 0

    if args.sync_playlists and not args.playlist:
        from ix_crate.stems_playlists import format_plan, sync_playlists

        plan = sync_playlists(execute=args.execute)
        print(format_plan(plan), flush=True)
        if not args.execute:
            print("dry-run. pass --execute to write Traktor NML and Rekordbox XML.", flush=True)
        else:
            print("wrote STEMIT playlists. Quit/reopen Traktor. Refresh rekordbox xml.", flush=True)
        return 0

    if args.genre and args.playlist:
        parser.error("use --playlist or --genre, not both")
    if not args.playlist and not args.genre:
        parser.error(
            "--playlist or --genre is required unless you pass --sync-playlists, --fix-role-titles, "
            "--fix-titles, --fix-industry-artists, --genres, --dedupe, or --drop-copies"
        )

    try:
        if args.genre:
            rows = dump_genre(args.genre, limit=args.limit, offset=args.offset)
            payload = plan_playlist(f"genre:{args.genre}", rows=rows)
        else:
            rows = dump_playlist(args.playlist)
            start = max(args.offset, 0)
            end = start + args.limit if args.limit > 0 else None
            rows = rows[start:end]
            payload = plan_playlist(args.playlist, rows=rows)
    except MusicDupesError as exc:
        print(exc, file=sys.stderr)
        return 2

    report = write_stemit_report(payload)
    print(
        f"STEMIT playlist {payload['playlist']!r}: "
        f"{payload['stem']} stem / {payload['skip']} skip / {payload['tracks']} tracks"
    )
    for job in payload["jobs"]:
        mark = "skip" if job["action"] == "skip" else "stem"
        extra = f" ({job['reason']})" if job["reason"] else ""
        print(f"  {mark}  {job['artist']} — {job['name']}{extra}")
    print(f"report: {report}")
    if not args.execute:
        print("dry-run. pass --execute to hardlink into stems_audio and run the factory HUD.")
        return 0

    try:
        execute_links(payload)
    except CrateSafetyError as exc:
        print(exc, file=sys.stderr)
        return 2

    queue = write_queue(payload["jobs"], playlist=payload["playlist"])
    payload["queue"] = str(queue)
    payload["execute"] = True
    write_stemit_report(payload)
    print(f"linked {payload.get('linked', 0)}  queue {queue}")
    if args.no_factory:
        print("hardlink only (--no-factory).")
        return 0
    print(f"{HUD_TITLE}: launching py.exec.separate (Aqua HUD until Close).", flush=True)
    code = run_factory(queue, execute=True)
    from ix_crate.stems_playlists import format_plan, sync_playlists

    plan = sync_playlists(execute=True)
    print(format_plan(plan), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
