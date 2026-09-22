"""Fill artist / album / title / genre on a Music.app playlist.

Default playlist is ``Fix``. Cascade: filename → tags → AcoustID →
Shazam → iTunes/Deezer → MusicBrainz. Unidentified leftovers stay
untouched (no Various Artists salvage). Never Discogs. Never moves
Media.localized. Never mutagen-writes ``.stem.m4a`` or ``.m4p``.

``--aggressive`` (default on) uses fingerprints and duration-only catalog
hits. ``--strict`` is the old dual-catalog path. Dry-run is the default.
``--execute`` writes file tags and Music.app. Aqua HUD via stems
``py.utils.progress``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ix_crate.families import Family, family_key, is_audio
from ix_crate.identify import (
    clean_text,
    is_placeholder_album_folder,
    is_placeholder_artist,
    is_placeholder_title,
    normalize_title,
    strip_track_number,
)
from ix_crate.lookup import catalog_identify, itunes_search, pick_catalog_hit, resolve
from ix_crate.music_dupes import (
    MusicDupesError,
    _clean_field,
    _parse_int,
    _run_osascript,
    music_running,
)
from ix_crate.music_repair import (
    OWNED_TAG,
    SKIP_SUFFIX,
    RepairRow,
    TagPlan,
    _file_duration,
    run_with_hud,
    set_track_fields,
    write_file_tags,
)
from ix_crate.paths import REPORTS
from ix_crate.stems_path import ensure_stems_path

HUD_TITLE = "Music Fix playlist"
TOOL_ID = "ix.crate.music_fix"
DEFAULT_PLAYLIST = "Fix"
JUNK_ALBUMS = {
    "rain or shine summer",
    "unknown album",
    "untitled",
    "untitled album",
}
LEADING_JUNK = re.compile(r"^[\s._\-]+")


def is_junk_album(value: str) -> bool:
    return is_placeholder_album_folder(value) or normalize_title(value) in JUNK_ALBUMS


def title_is_junk(row: RepairRow) -> bool:
    if is_placeholder_title(row.name):
        return True
    album_key = normalize_title(row.album)
    name_key = normalize_title(row.name)
    if album_key and name_key.startswith(album_key) and is_junk_album(row.album):
        return True
    return False


def row_needs_fix(row: RepairRow) -> bool:
    return (
        is_placeholder_artist(row.artist)
        or title_is_junk(row)
        or not row.album.strip()
        or is_junk_album(row.album)
    )


def salvage_title(row: RepairRow, path: Path) -> str:
    stem = LEADING_JUNK.sub("", strip_track_number(clean_text(path.stem)))
    if stem and not is_placeholder_title(stem):
        return stem
    name = LEADING_JUNK.sub("", strip_track_number(clean_text(row.name)))
    if name and not is_placeholder_title(name):
        return name
    album = row.album.strip() or path.parent.name or "Untitled"
    digits = re.search(r"(\d{1,3})", path.stem) or re.search(r"(\d{1,3})", row.name)
    suffix = digits.group(1) if digits else (stem or path.stem)
    return f"{album} {suffix}".strip()


def _parse_repair_rows(text: str) -> list[RepairRow]:
    rows: list[RepairRow] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            parts = parts + [""] * (8 - len(parts))
        pid, dbid, artist, album, name, genre, duration, location = parts[:8]
        if not pid.strip():
            continue
        rows.append(
            RepairRow(
                persistent_id=pid.strip(),
                database_id=_parse_int(dbid),
                artist=_clean_field(artist),
                album=_clean_field(album),
                name=_clean_field(name),
                genre=_clean_field(genre),
                duration=float(_parse_int(duration)),
                location=location.strip(),
            )
        )
    return rows


def dump_playlist(name: str) -> list[RepairRow]:
    if not music_running():
        raise MusicDupesError("Music.app is not running. Open it and retry.")
    quoted = name.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Music"
  try
    set p to user playlist "{quoted}"
  on error
    error "playlist not found: {quoted}"
  end try
  set n to count of file tracks of p
  if n is 0 then return ""
  set pids to persistent ID of file tracks of p
  set dbids to database ID of file tracks of p
  set nms to name of file tracks of p
  set ars to artist of file tracks of p
  set als to album of file tracks of p
  set gns to genre of file tracks of p
  set durs to duration of file tracks of p
  set locs to location of file tracks of p
  set out to ""
  repeat with i from 1 to count of pids
    set locText to ""
    try
      set locText to POSIX path of (item i of locs)
    end try
    set out to out & (item i of pids as text) & tab & (item i of dbids as text) & tab & (item i of ars as text) & tab & (item i of als as text) & tab & (item i of nms as text) & tab & (item i of gns as text) & tab & (item i of durs as text) & tab & locText & linefeed
  end repeat
  return out
end tell
'''
    return _parse_repair_rows(_run_osascript(script, timeout=180))


def dump_genre(genre: str, *, limit: int = 0, offset: int = 0) -> list[RepairRow]:
    """Library file tracks whose genre matches exactly, in library order."""
    if not music_running():
        raise MusicDupesError("Music.app is not running. Open it and retry.")
    quoted = genre.replace("\\", "\\\\").replace('"', '\\"')
    skip = max(int(offset), 0)
    cap = max(int(limit), 0)
    start = skip + 1
    if cap:
        end_line = (
            f"set endIndex to {skip + cap}\n"
            f"  if endIndex > n then set endIndex to n"
        )
    else:
        end_line = "set endIndex to n"
    script = f'''
tell application "Music"
  set hits to every file track of library playlist 1 whose genre is "{quoted}"
  set n to count of hits
  if n is 0 then return ""
  set startIndex to {start}
  {end_line}
  if startIndex > n then return ""
  set out to ""
  repeat with i from startIndex to endIndex
    set t to item i of hits
    set locText to ""
    try
      set locText to POSIX path of (location of t as alias)
    end try
    set out to out & (persistent ID of t as text) & tab & (database ID of t as text) & tab & (artist of t as text) & tab & (album of t as text) & tab & (name of t as text) & tab & (genre of t as text) & tab & (duration of t as text) & tab & locText & linefeed
  end repeat
  return out
end tell
'''
    return _parse_repair_rows(_run_osascript(script, timeout=300))


def dump_various_artists() -> list[RepairRow]:
    if not music_running():
        raise MusicDupesError("Music.app is not running. Open it and retry.")
    script = '''
tell application "Music"
  set hits to every file track of library playlist 1 whose artist is "Various Artists"
  set out to ""
  repeat with t in hits
    set locText to ""
    try
      set locText to POSIX path of (location of t as alias)
    end try
    set out to out & (persistent ID of t as text) & tab & (database ID of t as text) & tab & (artist of t as text) & tab & (album of t as text) & tab & (name of t as text) & tab & (genre of t as text) & tab & (duration of t as text) & tab & locText & linefeed
  end repeat
  return out
end tell
'''
    return _parse_repair_rows(_run_osascript(script, timeout=180))


def choose_album(row_album: str, proposed: str, artist: str) -> str:
    """Keep real Music.app albums (Cream Live). Replace dump folders with Singles."""
    cleaned = proposed if proposed and not is_junk_album(proposed) else ""
    if artist and not cleaned:
        cleaned = "Singles"
    if row_album.strip() and not is_junk_album(row_album):
        if cleaned and cleaned != "Singles" and cleaned != row_album:
            return cleaned
        return ""
    return cleaned


def plan_fix_row(
    row: RepairRow, *, aggressive: bool = True, gaps_only: bool = True
) -> TagPlan | None:
    path = Path(row.location) if row.location else None
    if path is None or not path.is_file():
        return None
    if not is_audio(path):
        return None
    if any(path.name.lower().endswith(suffix) for suffix in SKIP_SUFFIX):
        return None
    if gaps_only and not row_needs_fix(row):
        return None
    family = Family(key=family_key(path), files=[path])
    identity = resolve(family, lookup=True, aggressive=aggressive)
    artist = identity.artist if not is_placeholder_artist(identity.artist) else ""
    if not artist:
        return None
    identified_title = identity.title if not is_placeholder_title(identity.title) else ""
    junk_title = title_is_junk(row)
    title = identified_title
    if not title and junk_title:
        title = salvage_title(row, path)
        if is_placeholder_title(title) or (
            is_junk_album(row.album) and normalize_title(title).startswith(normalize_title(row.album))
        ):
            title = identified_title
    proposed_album = identity.album if identity.album and not is_junk_album(identity.album) else ""
    album = choose_album(row.album, proposed_album, artist)
    source = identity.source
    genre = ""
    if not row.genre.strip():
        genre = identity.genre.strip()
        if not genre:
            cache: dict = {}
            try:
                from ix_crate.lookup import _load_cache

                cache = _load_cache()
            except Exception:
                cache = {}
            query_title = identified_title or (row.name if not junk_title else title)
            if query_title and not is_placeholder_title(query_title):
                hits = itunes_search(f"{artist} {query_title}".strip(), cache)
                hit = pick_catalog_hit(hits, query_title, row.duration or _file_duration(path))
                if hit and hit.get("genre"):
                    genre = str(hit["genre"])
                if not genre:
                    cat = catalog_identify(
                        query_title,
                        artist,
                        row.duration or None,
                        cache,
                        aggressive=aggressive,
                    )
                    if cat and cat.get("genre"):
                        genre = str(cat["genre"])

    if not artist and not album and not title and not genre:
        return None
    can_file = path.suffix.lower() in OWNED_TAG
    return TagPlan(
        persistent_id=row.persistent_id,
        path=path,
        artist=artist,
        album=album,
        title=title,
        genre=genre,
        source=source,
        album_artist=artist,
        compilation=False,
        write_file=can_file,
        write_library=True,
    )


class MusicFix:
    run_log: Any = None

    def __init__(
        self,
        playlist: str,
        *,
        dry_run: bool = True,
        aggressive: bool = True,
        gaps_only: bool = True,
        library_va: bool = False,
    ) -> None:
        self.playlist = playlist
        self.dry_run = dry_run
        self.aggressive = aggressive
        self.gaps_only = gaps_only
        self.library_va = library_va
        self.report_path: Path | None = None
        self.tags: list[TagPlan] = []
        self.skipped: list[dict[str, str]] = []

    def _hud(self, index: int, total: int, name: str, action: str) -> None:
        logger = getattr(self, "run_log", None)
        panel = getattr(logger, "panel", None) if logger is not None else None
        if panel is None:
            return
        try:
            panel.set_totals(max(total, 1), max(total, 1))
            panel.set_job(index, max(total, 1), name, action)
        except Exception:
            pass

    def plan(self) -> list:
        ensure_stems_path()
        from py.utils.base import Job

        source = "library Various Artists" if self.library_va else f"playlist {self.playlist!r}"
        print(f"{source}  aggressive={self.aggressive}  gaps_only={self.gaps_only}", flush=True)
        rows = dump_various_artists() if self.library_va else dump_playlist(self.playlist)
        print(f"tracks {len(rows)}", flush=True)
        self.tags = []
        self.skipped = []
        for i, row in enumerate(rows, start=1):
            self._hud(i, len(rows), row.name or row.persistent_id, "identify")
            try:
                plan = plan_fix_row(
                    row, aggressive=self.aggressive, gaps_only=self.gaps_only
                )
            except Exception as exc:
                print(f"identify skip {row.name}: {exc}", flush=True)
                self.skipped.append({"name": row.name, "reason": str(exc)})
                continue
            if plan is None:
                self.skipped.append(
                    {
                        "name": row.name,
                        "album": row.album,
                        "reason": "no unique identity",
                    }
                )
                continue
            self.tags.append(plan)
            print(
                f"  {plan.source:12} {plan.artist or '—'} — {plan.title or row.name}"
                f"{'  [' + plan.genre + ']' if plan.genre else ''}",
                flush=True,
            )

        payload = {
            "playlist": self.playlist,
            "tracks": len(rows),
            "tag_plans": len(self.tags),
            "skipped": len(self.skipped),
            "tags": [
                {
                    "persistent_id": plan.persistent_id,
                    "path": str(plan.path),
                    "artist": plan.artist,
                    "album": plan.album,
                    "title": plan.title,
                    "genre": plan.genre,
                    "source": plan.source,
                }
                for plan in self.tags
            ],
            "skipped_rows": self.skipped,
        }
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.report_path = REPORTS / f"music-fix-{stamp}.json"
        self.report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(
            f"identify {len(self.tags)}  skip {len(self.skipped)}  report {self.report_path}",
            flush=True,
        )
        jobs = []
        for plan in self.tags:
            jobs.append(
                Job(
                    plan.path,
                    plan.path,
                    "tag" if not self.dry_run else "plan-tag",
                    plan.source,
                    extra={
                        "persistent_id": plan.persistent_id,
                        "artist": plan.artist,
                        "album": plan.album,
                        "title": plan.title,
                        "genre": plan.genre,
                        "album_artist": plan.album_artist,
                        "compilation": plan.compilation,
                        "write_file": plan.write_file,
                        "write_library": plan.write_library,
                    },
                )
            )
        return jobs

    def print_plan(self, jobs: list) -> None:
        mode = "dry-run" if self.dry_run else "execute"
        print(f"{mode}: {len(jobs)} tag / {len(self.skipped)} skip", flush=True)
        if self.dry_run:
            print("dry-run. pass --execute to write file tags + Music.app.", flush=True)

    def run(self) -> list:
        ensure_stems_path()
        from py.utils.base import Job
        from py.utils.runlog import execute_logged

        jobs = self.plan()
        self.print_plan(jobs)

        def apply(job: Job) -> dict[str, Any]:
            pid = str(job.extra.get("persistent_id") or "")
            artist = str(job.extra.get("artist") or "")
            album = str(job.extra.get("album") or "")
            title = str(job.extra.get("title") or "")
            genre = str(job.extra.get("genre") or "")
            album_artist = str(job.extra.get("album_artist") or "")
            compilation = job.extra.get("compilation")
            file_error = ""
            if job.extra.get("write_file"):
                try:
                    write_file_tags(
                        job.source,
                        artist=artist,
                        album=album,
                        title=title,
                        genre=genre,
                        album_artist=album_artist,
                    )
                except Exception as exc:
                    file_error = str(exc)
                    print(f"file tags skipped {job.source.name}: {exc}", flush=True)
            if job.extra.get("write_library"):
                set_track_fields(
                    pid,
                    artist=artist,
                    album=album,
                    name=title,
                    genre=genre,
                    album_artist=album_artist,
                    compilation=None if compilation is None else bool(compilation),
                )
            result = {"handling": "tag", "source": job.reason}
            if file_error:
                result["file_error"] = file_error
            return result

        logger = getattr(self, "run_log", None)
        if logger is not None:
            return execute_logged(self, jobs, None if self.dry_run else apply)
        if self.dry_run:
            return jobs
        for job in jobs:
            apply(job)
            print(f"ok {job.action} {job.source.name}", flush=True)
        return jobs


def build_parser() -> argparse.ArgumentParser:
    ensure_stems_path()
    from py.utils.runlog import add_log_flags

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--playlist", default=DEFAULT_PLAYLIST)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Dual-catalog only. No AcoustID, no Shazam, no duration-only hits.",
    )
    parser.add_argument(
        "--library-va",
        action="store_true",
        help="Scan library tracks whose artist is Various Artists instead of a playlist.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-identify tracks that already have an artist. Default is gaps only.",
    )
    add_log_flags(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "gui", None) is None:
        args.gui = True
    tool = MusicFix(
        args.playlist,
        dry_run=not args.execute,
        aggressive=not args.strict,
        gaps_only=not args.all,
        library_va=bool(getattr(args, "library_va", False)),
    )
    try:
        return run_with_hud(args, tool, title=HUD_TITLE, tool_id=TOOL_ID)
    except MusicDupesError as exc:
        print(exc, file=sys.stderr)
        return 2