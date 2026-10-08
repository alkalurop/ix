"""Relink Music.app rows with no file, then fill artist/album/genre gaps.

Empty location (the Locate / ! mark) is matched to a unique file under
Media.localized. stems_audio is a fallback. Ambiguous copies are resolved
by album-folder name. No guesses. Never move Media.localized. Never
mutagen-write .stem.m4a or .m4p. Identity uses the crate cascade
(filename → tags → iTunes/Deezer → MusicBrainz → Ollama). Genre is filled
only when Music.app genre is empty, from iTunes primaryGenreName — not
Discogs, not Ollama.

Dry-run is the default. --execute writes locations and tags. Aqua HUD
via stems py.utils.progress.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ix_crate.families import Family, family_key, is_audio
from ix_crate.identify import (
    duration_close,
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
    count_file_tracks,
    music_running,
)
from ix_crate.paths import (
    APPLE_MEDIA_SKIP_DIRS,
    APPLE_MUSIC,
    REPORTS,
    STEMS_AUDIO,
    STEM_SUFFIXES,
)
from ix_crate.stems_path import ensure_stems_path

BATCH = 200
HUD_TITLE = "Music locate + identity"
TOOL_ID = "ix.crate.music_repair"
SKIP_SUFFIX = STEM_SUFFIXES + (".m4p",)
OWNED_TAG = {".mp3", ".m4a", ".wav", ".aiff", ".aif", ".flac"}
# ID3().save and EasyID3 prepend an ID3 header. On WAV/AIFF that replaces
# RIFF/FORM, and ffmpeg / Music.app refuse the file. That is how Unknown
# Album grew a corrupt unnumbered WAV plus valid ``(2)`` / ``(3)`` copies.
RIFF_NO_ID3 = {".wav", ".aiff", ".aif"}


def write_repair_report(payload: dict[str, Any]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = REPORTS / f"music-repair-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


@dataclass
class RepairRow:
    persistent_id: str
    database_id: int
    artist: str
    album: str
    name: str
    genre: str
    duration: float
    location: str


@dataclass
class DiskHit:
    path: Path
    artist_folder: str
    album_folder: str
    title_key: str


@dataclass
class LocatePlan:
    row: RepairRow
    path: Path
    reason: str


@dataclass
class TagPlan:
    persistent_id: str
    path: Path
    artist: str = ""
    album: str = ""
    title: str = ""
    genre: str = ""
    source: str = ""
    album_artist: str = ""
    compilation: bool | None = None
    write_file: bool = False
    write_library: bool = False


def _quote_as(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def dump_repair_batch(start: int, end: int) -> list[RepairRow]:
    script = f'''
tell application "Music"
  set pids to persistent ID of file tracks {start} thru {end} of library playlist 1
  set dbids to database ID of file tracks {start} thru {end} of library playlist 1
  set nms to name of file tracks {start} thru {end} of library playlist 1
  set ars to artist of file tracks {start} thru {end} of library playlist 1
  set als to album of file tracks {start} thru {end} of library playlist 1
  set gns to genre of file tracks {start} thru {end} of library playlist 1
  set durs to duration of file tracks {start} thru {end} of library playlist 1
  set locs to location of file tracks {start} thru {end} of library playlist 1
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
    text = _run_osascript(script, timeout=180)
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


def scan_missing(on_scan=None) -> tuple[list[RepairRow], int]:
    if not music_running():
        raise MusicDupesError("Music.app is not running. Open it and retry.")
    total = count_file_tracks()
    missing: list[RepairRow] = []
    start = 1
    while start <= total:
        end = min(start + BATCH - 1, total)
        if on_scan:
            on_scan(end, total)
        for row in dump_repair_batch(start, end):
            loc = row.location
            if not loc:
                missing.append(row)
                continue
            path = Path(loc)
            if loc.endswith(".itlp") or loc.endswith(".itlp/"):
                continue
            if not path.exists():
                missing.append(row)
        start = end + 1
    return missing, total


def _indexable(path: Path) -> bool:
    if not is_audio(path):
        return False
    # AppleDouble stubs on exFAT/SMB copies carry the audio extension but are
    # 4KB resource forks, not playable files.
    if path.name.startswith("._"):
        return False
    low = path.name.lower()
    return not any(low.endswith(suffix) for suffix in SKIP_SUFFIX)


def _folders(path: Path, root: Path) -> tuple[str, str]:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return "", ""
    parts = list(rel.parts)
    while parts and parts[0] in APPLE_MEDIA_SKIP_DIRS:
        parts = parts[1:]
    artist = fold_artist(parts[0]) if parts else ""
    album = normalize_title(parts[1]) if len(parts) >= 3 else ""
    return artist, album


COPY_SUFFIX = re.compile(r"\s*\((\d{1,2})\)$")


def strip_copy_suffix(title: str) -> str:
    """Drop a ``(2)`` collision suffix left by a consolidation copy.

    ``unique_dest`` numbers a name that is already taken, so the file lands as
    ``1-07 Bbydhyonchord (2).m4a`` and normalizes to ``bbydhyonchord 2``,
    which never matches the library row's ``Bbydhyonchord``.
    """
    return COPY_SUFFIX.sub("", title or "").strip()


def index_tree(root: Path) -> dict[str, Any]:
    by_title: dict[str, list[DiskHit]] = defaultdict(list)
    by_artist_title: dict[tuple[str, str], list[DiskHit]] = defaultdict(list)
    by_album_title: dict[tuple[str, str], list[DiskHit]] = defaultdict(list)
    if not root.is_dir():
        return {
            "by_title": by_title,
            "by_artist_title": by_artist_title,
            "by_album_title": by_album_title,
        }
    for path in root.rglob("*"):
        if not _indexable(path):
            continue
        bare = strip_track_number(path.stem)
        keys = {normalize_title(bare), normalize_title(strip_copy_suffix(bare))}
        keys.discard("")
        if not keys:
            continue
        artist, album = _folders(path, root)
        for title in keys:
            hit = DiskHit(
                path=path, artist_folder=artist, album_folder=album, title_key=title
            )
            by_title[title].append(hit)
            if artist:
                by_artist_title[(artist, title)].append(hit)
            if album:
                by_album_title[(album, title)].append(hit)
    return {
        "by_title": by_title,
        "by_artist_title": by_artist_title,
        "by_album_title": by_album_title,
    }


def _unique_paths(hits: list[DiskHit]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for hit in hits:
        path = hit.path
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _album_winner(paths: list[Path], album: str) -> Path | None:
    target = normalize_title(album)
    if not target or len(paths) < 2:
        return None
    scored: list[tuple[int, Path]] = []
    for path in paths:
        folder = normalize_title(path.parent.name)
        score = 0
        if folder == target:
            score = 3
        elif target in folder or folder in target:
            score = 2
        scored.append((score, path))
    scored.sort(key=lambda item: -item[0])
    if scored[0][0] <= 0:
        return None
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][1]
    return None


def _duration_winner(paths: list[Path], seconds: float) -> Path | None:
    if seconds <= 0 or len(paths) < 2:
        return None
    close: list[Path] = []
    for path in paths:
        length = _file_duration(path)
        if length is not None and duration_close(seconds, length):
            close.append(path)
    if len(close) == 1:
        return close[0]
    return None


def _file_duration(path: Path) -> float | None:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None
    try:
        audio = MutagenFile(path)
    except Exception:
        return None
    if audio is None:
        return None
    info = getattr(audio, "info", None)
    length = getattr(info, "length", None)
    return float(length) if length else None


def fold_artist(value: str) -> str:
    return normalize_title((value or "").replace("'", "").replace("’", ""))


def title_keys_for(row: RepairRow) -> list[str]:
    keys: list[str] = []
    primary = normalize_title(row.name)
    if primary:
        keys.append(primary)
    if " / " in row.name:
        right = normalize_title(row.name.split(" / ", 1)[1])
        if right and right not in keys:
            keys.append(right)
    return keys


def pick_match(row: RepairRow, index: dict[str, Any]) -> tuple[Path | None, str]:
    artist = fold_artist(row.artist)
    album = normalize_title(row.album)
    by_artist_title = index["by_artist_title"]
    by_album_title = index["by_album_title"]
    by_title = index["by_title"]
    generic = is_placeholder_title(row.name)

    for title in title_keys_for(row):
        if artist:
            paths = _unique_paths(by_artist_title.get((artist, title), []))
            if len(paths) == 1:
                return paths[0], "artist+title"
            winner = _album_winner(paths, row.album) or _duration_winner(paths, row.duration)
            if winner is not None:
                return winner, "artist+title+album"
        if album:
            paths = _unique_paths(by_album_title.get((album, title), []))
            if len(paths) == 1:
                return paths[0], "album+title"
            winner = _duration_winner(paths, row.duration)
            if winner is not None:
                return winner, "album+title+duration"
        if generic:
            continue
        paths = _unique_paths(by_title.get(title, []))
        if len(paths) == 1:
            return paths[0], "title"
        winner = _album_winner(paths, row.album) or _duration_winner(paths, row.duration)
        if winner is not None:
            return winner, "title+album"
    return None, ""


def set_track_location(persistent_id: str, path: Path) -> None:
    if not persistent_id.isalnum() or len(persistent_id) > 32:
        raise MusicDupesError(f"refusing persistent id {persistent_id!r}")
    if not path.is_file():
        raise MusicDupesError(f"missing file {path}")
    posix = _quote_as(str(path))
    script = f'''
tell application "Music"
  set hits to file tracks of library playlist 1 whose persistent ID is "{persistent_id}"
  if (count of hits) is not 1 then error "expected 1 track, got " & (count of hits)
  set location of item 1 of hits to (POSIX file "{posix}")
end tell
'''
    _run_osascript(script, timeout=45)


def set_track_fields(
    persistent_id: str,
    *,
    artist: str = "",
    album: str = "",
    name: str = "",
    genre: str = "",
    album_artist: str | None = None,
    compilation: bool | None = None,
) -> None:
    if not persistent_id.isalnum() or len(persistent_id) > 32:
        raise MusicDupesError(f"refusing persistent id {persistent_id!r}")
    assigns = []
    if artist:
        assigns.append(f'set artist of t to "{_quote_as(artist)}"')
    if album:
        assigns.append(f'set album of t to "{_quote_as(album)}"')
    if name:
        assigns.append(f'set name of t to "{_quote_as(name)}"')
    if genre:
        assigns.append(f'set genre of t to "{_quote_as(genre)}"')
    if album_artist is not None:
        assigns.append(f'set album artist of t to "{_quote_as(album_artist)}"')
    if compilation is not None:
        assigns.append(f"set compilation of t to {('true' if compilation else 'false')}")
    if not assigns:
        return
    body = "\n  ".join(assigns)
    script = f'''
tell application "Music"
  set hits to file tracks of library playlist 1 whose persistent ID is "{persistent_id}"
  if (count of hits) is not 1 then error "expected 1 track, got " & (count of hits)
  set t to item 1 of hits
  {body}
end tell
'''
    _run_osascript(script, timeout=45)


def write_file_tags(
    path: Path,
    *,
    artist: str,
    album: str,
    title: str,
    genre: str,
    album_artist: str = "",
) -> None:
    low = path.name.lower()
    if any(low.endswith(suffix) for suffix in SKIP_SUFFIX):
        raise MusicDupesError(f"refusing to tag {path.name}")
    if path.suffix.lower() not in OWNED_TAG:
        return
    if path.suffix.lower() in RIFF_NO_ID3:
        return
    from mutagen import File as MutagenFile

    audio = MutagenFile(path, easy=True)
    if audio is None:
        return
    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception:
            _write_id3_frames(
                path,
                artist=artist,
                album=album,
                title=title,
                genre=genre,
                album_artist=album_artist,
            )
            return
    try:
        if artist:
            audio.tags["artist"] = [artist]
        if album:
            audio.tags["album"] = [album]
        if title:
            audio.tags["title"] = [title]
        if genre:
            audio.tags["genre"] = [genre]
        if album_artist:
            audio.tags["albumartist"] = [album_artist]
        audio.save()
    except Exception:
        _write_id3_frames(
            path,
            artist=artist,
            album=album,
            title=title,
            genre=genre,
            album_artist=album_artist,
        )


def _write_id3_frames(
    path: Path,
    *,
    artist: str,
    album: str,
    title: str,
    genre: str,
    album_artist: str = "",
) -> None:
    from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1, TPE2, ID3NoHeaderError

    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    except Exception:
        return
    if artist:
        tags["TPE1"] = TPE1(encoding=3, text=[artist])
    if album:
        tags["TALB"] = TALB(encoding=3, text=[album])
    if title:
        tags["TIT2"] = TIT2(encoding=3, text=[title])
    if genre:
        tags["TCON"] = TCON(encoding=3, text=[genre])
    if album_artist:
        tags["TPE2"] = TPE2(encoding=3, text=[album_artist])
    tags.save(path, v2_version=3)


def plan_identity(row: RepairRow, path: Path) -> TagPlan | None:
    needs_id = (
        is_placeholder_artist(row.artist)
        or is_placeholder_title(row.name)
        or is_placeholder_album_folder(row.album)
        or not row.album.strip()
    )
    needs_genre = not row.genre.strip()
    if not needs_id and not needs_genre:
        return None
    family = Family(key=family_key(path), files=[path])
    identity = resolve(family, lookup=needs_id)
    artist = identity.artist if needs_id and not is_placeholder_artist(identity.artist) else ""
    album = identity.album if needs_id and identity.album and not is_placeholder_album_folder(identity.album) else ""
    title = identity.title if needs_id and not is_placeholder_title(identity.title) else ""
    genre = ""
    if needs_genre:
        cache: dict = {}
        try:
            from ix_crate.lookup import _load_cache

            cache = _load_cache()
        except Exception:
            cache = {}
        query_title = title or row.name
        query_artist = artist or row.artist
        hits = itunes_search(f"{query_artist} {query_title}".strip(), cache)
        hit = pick_catalog_hit(hits, query_title, row.duration or _file_duration(path))
        if hit and hit.get("genre"):
            genre = str(hit["genre"])
        if not genre:
            cat = catalog_identify(query_title, query_artist, row.duration or None, cache)
            if cat and cat.get("genre"):
                genre = str(cat["genre"])
    if not artist and not album and not title and not genre:
        return None
    can_file = path.suffix.lower() in OWNED_TAG and not any(
        path.name.lower().endswith(suffix) for suffix in SKIP_SUFFIX
    )
    return TagPlan(
        persistent_id=row.persistent_id,
        path=path,
        artist=artist,
        album=album,
        title=title,
        genre=genre,
        source=identity.source if needs_id else "itunes-genre",
        write_file=can_file and bool(artist or album or title or genre),
        write_library=True,
    )


class MusicRepair:
    run_log: Any = None

    def __init__(self, *, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self.report_path: Path | None = None
        self.locate: list[LocatePlan] = []
        self.unmatched: list[RepairRow] = []
        self.tags: list[TagPlan] = []

    def _panel(self):
        logger = getattr(self, "run_log", None)
        return getattr(logger, "panel", None) if logger is not None else None

    def _hud(self, index: int, total: int, name: str, action: str) -> None:
        panel = self._panel()
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

        def on_scan(done: int, total: int) -> None:
            print(f"scan {done}/{total} file tracks", flush=True)
            self._hud(done, total, "library", "scan")

        missing, file_tracks = scan_missing(on_scan=on_scan)
        print(f"missing locations {len(missing)} / {file_tracks}", flush=True)
        print("index Media.localized", flush=True)
        media_index = index_tree(APPLE_MUSIC.expanduser())
        print("index stems_audio", flush=True)
        stems_index = index_tree(STEMS_AUDIO.expanduser())

        self.locate = []
        self.unmatched = []
        for i, row in enumerate(missing, start=1):
            self._hud(i, len(missing), row.name or row.persistent_id, "match")
            path, reason = pick_match(row, media_index)
            if path is None:
                path, reason = pick_match(row, stems_index)
                if path is not None:
                    reason = f"stems:{reason}"
            if path is None:
                self.unmatched.append(row)
                continue
            self.locate.append(LocatePlan(row=row, path=path, reason=reason))

        self.tags = []
        for i, item in enumerate(self.locate, start=1):
            self._hud(i, max(len(self.locate), 1), item.row.name, "identify")
            try:
                plan = plan_identity(item.row, item.path)
            except Exception as exc:
                print(f"identify skip {item.row.name}: {exc}", flush=True)
                continue
            if plan is not None:
                self.tags.append(plan)

        payload = {
            "scanned": file_tracks,
            "missing": len(missing),
            "located": len(self.locate),
            "unmatched": len(self.unmatched),
            "tag_plans": len(self.tags),
            "locate": [
                {
                    "persistent_id": item.row.persistent_id,
                    "artist": item.row.artist,
                    "album": item.row.album,
                    "name": item.row.name,
                    "path": str(item.path),
                    "reason": item.reason,
                }
                for item in self.locate
            ],
            "unmatched_rows": [
                {
                    "persistent_id": row.persistent_id,
                    "artist": row.artist,
                    "album": row.album,
                    "name": row.name,
                }
                for row in self.unmatched
            ],
            "tags": [
                {
                    "persistent_id": plan.persistent_id,
                    "path": str(plan.path),
                    "artist": plan.artist,
                    "album": plan.album,
                    "title": plan.title,
                    "genre": plan.genre,
                    "source": plan.source,
                    "write_file": plan.write_file,
                    "write_library": plan.write_library,
                }
                for plan in self.tags
            ],
        }
        self.report_path = write_repair_report(payload)
        print(
            f"locate {len(self.locate)}  unmatched {len(self.unmatched)}  "
            f"identity/genre {len(self.tags)}",
            flush=True,
        )
        for item in self.locate[:20]:
            print(
                f"  {item.reason:16} {item.row.artist} — {item.row.name} -> {item.path.name}",
                flush=True,
            )
        if len(self.locate) > 20:
            print(f"  … {len(self.locate) - 20} more locates", flush=True)
        print(f"report: {self.report_path}", flush=True)

        tags_by_pid = {plan.persistent_id: plan for plan in self.tags}
        jobs = []
        for item in self.locate:
            jobs.append(
                Job(
                    item.path,
                    item.path,
                    "locate" if not self.dry_run else "plan-locate",
                    item.reason,
                    extra={
                        "persistent_id": item.row.persistent_id,
                        "name": item.row.name,
                    },
                )
            )
            plan = tags_by_pid.pop(item.row.persistent_id, None)
            if plan is None:
                continue
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
                        "write_file": plan.write_file,
                        "write_library": plan.write_library,
                    },
                )
            )
        for plan in tags_by_pid.values():
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
                        "write_file": plan.write_file,
                        "write_library": plan.write_library,
                    },
                )
            )
        return jobs

    def print_plan(self, jobs: list) -> None:
        mode = "dry-run" if self.dry_run else "execute"
        locates = sum(1 for job in jobs if "locate" in job.action)
        tags = sum(1 for job in jobs if "tag" in job.action)
        print(f"{mode}: {locates} locate / {tags} tag / {len(self.unmatched)} unmatched", flush=True)
        if self.dry_run:
            print("dry-run. pass --execute to set Music.app location + tags.", flush=True)

    def run(self) -> list:
        ensure_stems_path()
        from py.utils.base import Job
        from py.utils.runlog import execute_logged

        jobs = self.plan()
        self.print_plan(jobs)

        def apply(job: Job) -> dict[str, Any]:
            pid = str(job.extra.get("persistent_id") or "")
            if "locate" in job.action:
                set_track_location(pid, job.source)
                if not job.source.is_file():
                    raise MusicDupesError(f"file vanished after locate {job.source}")
                return {"handling": "locate", "path": str(job.source)}
            artist = str(job.extra.get("artist") or "")
            album = str(job.extra.get("album") or "")
            title = str(job.extra.get("title") or "")
            genre = str(job.extra.get("genre") or "")
            if job.extra.get("write_file"):
                write_file_tags(
                    job.source, artist=artist, album=album, title=title, genre=genre
                )
            if job.extra.get("write_library"):
                set_track_fields(
                    pid, artist=artist, album=album, name=title, genre=genre
                )
            return {"handling": "tag", "genre": genre, "source": job.reason}

        logger = getattr(self, "run_log", None)
        if logger is not None:
            return execute_logged(self, jobs, None if self.dry_run else apply)
        if self.dry_run:
            return jobs
        for job in jobs:
            apply(job)
            print(f"ok {job.action} {job.source.name}", flush=True)
        return jobs


def run_with_hud(
    args: argparse.Namespace,
    tool,
    *,
    title: str = HUD_TITLE,
    tool_id: str = TOOL_ID,
) -> int:
    ensure_stems_path()
    from py.utils.notify import notify_complete, resolve_charts, summary_from_payload
    from py.utils.runlog import RunLogger, is_verbose, want_notify

    want_panel = True if getattr(args, "gui", None) is None else bool(args.gui)
    panel = None
    if want_panel:
        from py.utils.progress import ProgressPanel

        panel = ProgressPanel.try_open(title)
    logger = RunLogger(
        tool_id,
        verbose=is_verbose(args),
        dry_run=tool.dry_run,
        panel=panel,
    )
    tool.run_log = logger

    def work() -> None:
        try:
            tool.run()
        except Exception as exc:
            print(f"run failed: {exc}", flush=True)
        finally:
            try:
                logger.close()
            except Exception as exc:
                print(f"run log close failed: {exc}", flush=True)
            payload = logger.payload or {}
            summary = summary_from_payload(payload) if payload else f"{TOOL_ID} finished"
            if tool.report_path:
                summary = f"{summary}  report {tool.report_path.name}"
            charts = resolve_charts(payload)
            if want_notify(args, tool.dry_run):
                notify_complete(title=title, body=summary, payload=payload)
            if panel is not None:
                try:
                    panel.finish(summary, charts=charts)
                except Exception as exc:
                    print(f"progress GUI finish skipped ({exc})", flush=True)

    if panel is None:
        work()
        return 0
    worker = threading.Thread(target=work, name=tool_id, daemon=False)
    worker.start()
    panel.mainloop()
    worker.join()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ensure_stems_path()
    from py.utils.runlog import add_log_flags

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Set Music.app locations and fill identity/genre gaps. Default is dry-run.",
    )
    add_log_flags(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "gui", None) is None:
        args.gui = True
    tool = MusicRepair(dry_run=not args.execute)
    try:
        return run_with_hud(args, tool)
    except MusicDupesError as exc:
        print(exc, file=sys.stderr)
        return 2
