"""Playlist membership bridge: Music.app ↔ Traktor NML ↔ rekordbox.xml.

Cues, energy, comments, and beatgrids stay on existing collection rows.
Membership matches by resolved path or hardlink inode. Files that are
in the source crate but not yet in the dest collection get a
**location** row (Name / Artist / Location) so Rekordbox and Traktor can
import and analyze — never a stub without a file (those load as 0.00
BPM). Skip ``.m4p``. STEMIT stays owned by ``stemit --genres``.

When writing ``rekordbox.xml``, empty **Genre** on collection rows is
filled from Traktor NML ``INFO GENRE`` first, then Apple Music library
XML (Share iTunes Library XML), including hardlink matches. Existing
non-empty Genre is only normalized (``music_genre.clean_genre``).
Cues on tracks Rekordbox does not already have wait for in-app Analyze.

Dry-run default. Quit Rekordbox for ``--to xml``. Quit Traktor for
``--to nml``. Music.app must be open for ``--from music`` / ``--to music``.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from ix_crate.music_dupes import MusicDupesError, _run_osascript, music_running
from ix_crate.xml_io import write_tree
from ix_crate.paths import APPLE_MUSIC, AUDIO_EXTS, REPORTS
from ix_crate.stems_playlists import (
    KIND,
    REKORDBOX_XML,
    TRAKTOR_NML,
    _ensure_traktor_folder,
    _ensure_traktor_playlist,
    _loc_to_path,
    _rb_location,
    _traktor_dir_file,
    rekordbox_is_running,
)
from ix_crate.traktor_nml import _walk_playlists, traktor_is_running

APPS = ("music", "nml", "xml")
PROTECTED = frozenset({"STEMIT"})
MUSIC_FOLDER = "MUSIC"
TRAKTOR_FOLDER = "TRAKTOR"
SKIP_NML_NAMES = frozenset({"_LOOPS", "_RECORDINGS", "_PREPARE", "Explorer", "History"})
SKIP_MUSIC_NAMES = frozenset(
    {
        "library",
        "music",
        "downloaded",
        "purchased music",
        "recently added",
        "recently played",
        "top 25 most played",
        "my top rated",
    }
)
TOOL_ID = "ix.crate.crates"
SKIP_INGEST_SUFFIXES = {".m4p"}


@dataclass
class TrackRef:
    path: Path
    label: str = ""
    artist: str = ""
    title: str = ""
    album: str = ""
    genre: str = ""
    bpm: str = ""
    key: str = ""
    total_time: str = ""
    comments: str = ""


@dataclass
class CratePlaylist:
    name: str
    tracks: list[TrackRef]
    folder: tuple[str, ...] = ()


@dataclass
class Hit:
    path: Path
    dest_key: str
    via: str
    extra: str = ""


@dataclass
class PlaylistPlan:
    name: str
    folder: tuple[str, ...]
    matched: list[Hit] = field(default_factory=list)
    missing: list[TrackRef] = field(default_factory=list)
    ingested: int = 0


@dataclass
class MusicList:
    index: int
    name: str
    folder: tuple[str, ...] = ()


@dataclass
class SyncPlan:
    source: str
    dest: str
    dest_folder: str
    playlists: list[PlaylistPlan] = field(default_factory=list)
    replace_folder: bool = False
    ingest: bool = True


class PathIndex:
    """path / hardlink → dest key. First writer wins so cues stay on that row."""

    def __init__(self) -> None:
        self.by_path: dict[Path, str] = {}
        self.by_inode: dict[tuple[int, int], str] = {}
        self.extra: dict[str, str] = {}

    def add(self, path: Path, key: str, extra: str = "") -> None:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path.expanduser()
        if resolved not in self.by_path:
            self.by_path[resolved] = key
            if extra:
                self.extra[key] = extra
        try:
            if resolved.is_file():
                stat = resolved.stat()
                inode = (stat.st_dev, stat.st_ino)
                if inode not in self.by_inode:
                    self.by_inode[inode] = key
                    if extra:
                        self.extra[key] = extra
        except OSError:
            return

    def lookup(self, path: Path) -> tuple[str, str] | None:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path.expanduser()
        key = self.by_path.get(resolved)
        if key:
            return key, "path"
        try:
            if resolved.is_file():
                stat = resolved.stat()
                key = self.by_inode.get((stat.st_dev, stat.st_ino))
                if key:
                    return key, "inode"
        except OSError:
            return None
        return None


def parse_rb_location(raw: str) -> Path | None:
    text = unquote((raw or "").replace("file://localhost", "").replace("file://", ""))
    if not text:
        return None
    path = Path(text)
    try:
        return path.resolve()
    except OSError:
        return path


def itunes_library_xml() -> Path:
    return APPLE_MUSIC.expanduser() / "iTunes Music Library.xml"


def dest_folder_for(source: str, dest: str) -> str:
    if dest == "xml" and source == "nml":
        return TRAKTOR_FOLDER
    return MUSIC_FOLDER


def bridge_folder(item: PlaylistPlan, dest_folder: str) -> tuple[str, ...]:
    """Drop a leading MUSIC/TRAKTOR so round-trips do not nest MUSIC/MUSIC."""
    folder = item.folder
    if folder and folder[0] in {MUSIC_FOLDER, TRAKTOR_FOLDER, dest_folder}:
        return folder[1:]
    return folder


def xml_path_index(xml: Path) -> PathIndex:
    index = PathIndex()
    collection = ET.parse(xml).getroot().find("COLLECTION")
    if collection is None:
        return index
    for track in collection.findall("TRACK"):
        tid = track.get("TrackID") or ""
        path = parse_rb_location(track.get("Location") or "")
        if tid and path is not None:
            index.add(path, tid)
    return index


def nml_path_index(nml: Path) -> PathIndex:
    index = PathIndex()
    collection = ET.parse(nml).getroot().find("COLLECTION")
    if collection is None:
        return index
    for entry in collection.findall("ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        directory = location.get("DIR") or ""
        file_attr = location.get("FILE") or ""
        volume = location.get("VOLUME") or "Macintosh HD"
        try:
            path = _loc_to_path(directory, file_attr)
        except OSError:
            continue
        pk_type = "STEM" if ".stem." in (file_attr or "").lower() else "TRACK"
        key = f"{volume}{directory}{file_attr}"
        index.add(path, key, extra=pk_type)
    return index


def music_path_index(xml: Path | None = None) -> PathIndex:
    index = PathIndex()
    lib = xml or itunes_library_xml()
    if not lib.is_file():
        return index
    with lib.open("rb") as handle:
        payload = plistlib.load(handle)
    tracks = payload.get("Tracks") or {}
    for row in tracks.values():
        if not isinstance(row, dict):
            continue
        pid = str(row.get("Persistent ID") or "").strip()
        location = str(row.get("Location") or "")
        path = parse_rb_location(location)
        if pid and path is not None:
            index.add(path, pid)
    return index


def _skip_nml_path(parts: tuple[str, ...], name: str) -> bool:
    blob = (parts + (name,))
    if any(part in PROTECTED for part in blob):
        return True
    if name in SKIP_NML_NAMES or name.startswith("_") or name.startswith("$"):
        return True
    if parts and (parts[0].startswith("_") or parts[0].startswith("$")):
        return True
    return False


def load_nml_playlists(
    nml: Path,
    *,
    names: set[str] | None = None,
    all_playlists: bool = False,
) -> list[CratePlaylist]:
    root = ET.parse(nml).getroot()
    playlists_el = root.find("PLAYLISTS")
    if playlists_el is None:
        return []
    root_node = playlists_el.find("NODE")
    if root_node is None:
        return []
    collection = nml_path_index(nml)
    key_to_path = {key: path for path, key in collection.by_path.items()}
    found: list[CratePlaylist] = []
    for node, path in _walk_playlists(root_node):
        parts = tuple(p for p in path.split("/") if p and p != "$ROOT")
        if not parts:
            continue
        name = parts[-1]
        folder = parts[:-1]
        if _skip_nml_path(folder, name):
            continue
        if names is not None and name not in names and "/".join(parts) not in names:
            continue
        if names is None and not all_playlists:
            continue
        playlist = node.find("PLAYLIST")
        if playlist is None:
            continue
        tracks: list[TrackRef] = []
        for entry in playlist.findall("ENTRY"):
            pk = entry.find("PRIMARYKEY")
            if pk is None:
                continue
            key = pk.get("KEY") or ""
            hit = key_to_path.get(key)
            if hit is None:
                continue
            tracks.append(TrackRef(path=hit, label=hit.name))
        found.append(CratePlaylist(name=name, folder=folder, tracks=tracks))
    return found


def _walk_rb_nodes(
    node: ET.Element,
    stack: tuple[str, ...],
    id_to_path: dict[str, Path],
) -> list[CratePlaylist]:
    found: list[CratePlaylist] = []
    name = node.get("Name") or ""
    if name in PROTECTED:
        return found
    kind = node.get("Type") or ""
    if kind == "1":
        tracks: list[TrackRef] = []
        for child in node.findall("TRACK"):
            tid = child.get("Key") or ""
            path = id_to_path.get(tid)
            if path is not None:
                tracks.append(TrackRef(path=path, label=path.name))
        found.append(CratePlaylist(name=name, folder=stack, tracks=tracks))
        return found
    child_stack = stack + ((name,) if name and name != "ROOT" else ())
    for child in node.findall("NODE"):
        found.extend(_walk_rb_nodes(child, child_stack, id_to_path))
    return found


def load_xml_playlists(
    xml: Path,
    *,
    names: set[str] | None = None,
    all_playlists: bool = False,
) -> list[CratePlaylist]:
    tree = ET.parse(xml)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    id_to_path: dict[str, Path] = {}
    if collection is not None:
        for track in collection.findall("TRACK"):
            tid = track.get("TrackID") or ""
            path = parse_rb_location(track.get("Location") or "")
            if tid and path is not None:
                id_to_path[tid] = path
    playlists_el = root.find("PLAYLISTS")
    if playlists_el is None:
        return []
    found: list[CratePlaylist] = []
    root_node = playlists_el.find("NODE")
    nodes = [root_node] if root_node is not None else list(playlists_el)
    for node in nodes:
        if node is None:
            continue
        found.extend(_walk_rb_nodes(node, (), id_to_path))
    kept: list[CratePlaylist] = []
    for item in found:
        if any(part in PROTECTED for part in item.folder + (item.name,)):
            continue
        if names is not None:
            full = "/".join(item.folder + (item.name,))
            if item.name not in names and full not in names:
                continue
        elif not all_playlists:
            continue
        kept.append(item)
    return kept


def list_music_playlists() -> list[str]:
    return [item.name for item in list_music_playlist_tree()]


def list_music_playlist_tree() -> list[MusicList]:
    """User playlists with folder parents. Index is 1-based in Music.app."""
    if not music_running():
        raise MusicDupesError("Music.app is not running. Open it and retry.")
    script = """
tell application "Music"
  set out to ""
  set n to count of user playlists
  repeat with i from 1 to n
    set p to user playlist i
    set sk to "none"
    try
      set sk to (special kind of p as text)
    end try
    set sm to "no"
    try
      if smart of p is true then set sm to "yes"
    end try
    set folders to ""
    try
      set folders to name of parent of p as text
    end try
    set out to out & i & tab & (name of p as text) & tab & sk & tab & sm & tab & folders & linefeed
  end repeat
  return out
end tell
"""
    found: list[MusicList] = []
    for line in _run_osascript(script, timeout=180).splitlines():
        if not line.strip():
            continue
        parts = (line.split("\t") + [""] * 5)[:5]
        index_text, name, kind, smart, parent = (part.strip() for part in parts)
        if not name or name.lower() in SKIP_MUSIC_NAMES:
            continue
        if kind != "none" or smart == "yes":
            continue
        try:
            index = int(index_text)
        except ValueError:
            continue
        folder = tuple(part for part in parent.split("/") if part) if parent else ()
        found.append(MusicList(index=index, name=name, folder=folder))
    return found


def dump_user_playlist_index(index: int) -> list[TrackRef]:
    script = f'''
tell application "Music"
  set p to user playlist {index}
  set n to count of file tracks of p
  if n is 0 then return ""
  set nms to name of file tracks of p
  set ars to artist of file tracks of p
  set gns to genre of file tracks of p
  set locs to location of file tracks of p
  set out to ""
  repeat with i from 1 to n
    set locText to ""
    try
      set locText to POSIX path of (item i of locs)
    end try
    set out to out & (item i of ars as text) & tab & (item i of nms as text) & tab & (item i of gns as text) & tab & locText & linefeed
  end repeat
  return out
end tell
'''
    tracks: list[TrackRef] = []
    text = _run_osascript(script, timeout=600)
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = (line.split("\t") + [""] * 4)[:4]
        artist, name, genre, location = (part.strip() for part in parts)
        if not location:
            continue
        from ix_crate.music_genre import clean_genre

        tracks.append(
            TrackRef(
                path=Path(location).expanduser(),
                label=f"{artist} — {name}".strip(" —"),
                artist=artist,
                title=name,
                genre=clean_genre(genre),
            )
        )
    return tracks


def uniquify_playlist_names(playlists: list[CratePlaylist]) -> list[CratePlaylist]:
    counts: dict[tuple[str, ...], int] = {}
    unique: list[CratePlaylist] = []
    for item in playlists:
        key = item.folder + (item.name,)
        counts[key] = counts.get(key, 0) + 1
        n = counts[key]
        name = item.name if n == 1 else f"{item.name} ({n})"
        unique.append(CratePlaylist(name=name, folder=item.folder, tracks=item.tracks))
    return unique


def load_music_playlists(
    *,
    names: set[str] | None = None,
    all_playlists: bool = False,
) -> list[CratePlaylist]:
    if names is None and not all_playlists:
        return []
    tree = list_music_playlist_tree()
    found: list[CratePlaylist] = []
    total = len(tree)
    for i, item in enumerate(tree, start=1):
        full = "/".join(item.folder + (item.name,))
        if names is not None and item.name not in names and full not in names:
            continue
        path = full if item.folder else item.name
        print(f"dump {i}/{total}  {path}", flush=True)
        tracks = dump_user_playlist_index(item.index)
        found.append(CratePlaylist(name=item.name, folder=item.folder, tracks=tracks))
    return uniquify_playlist_names(found)


def plan_membership(playlists: list[CratePlaylist], index: PathIndex) -> list[PlaylistPlan]:
    planned: list[PlaylistPlan] = []
    for item in playlists:
        plan = PlaylistPlan(name=item.name, folder=item.folder)
        seen: set[str] = set()
        for track in item.tracks:
            hit = index.lookup(track.path)
            if hit is None:
                plan.missing.append(track)
                continue
            key, via = hit
            if key in seen:
                continue
            seen.add(key)
            plan.matched.append(
                Hit(
                    path=track.path,
                    dest_key=key,
                    via=via,
                    extra=index.extra.get(key, ""),
                )
            )
        planned.append(plan)
    return planned


def ingestible(track: TrackRef) -> bool:
    path = track.path.expanduser()
    try:
        if not path.is_file():
            return False
    except OSError:
        return False
    suffix = path.suffix.lower()
    if suffix in SKIP_INGEST_SUFFIXES:
        return False
    if ".stem." in path.name.lower():
        return True
    return suffix in AUDIO_EXTS


def _filing(track: TrackRef) -> tuple[str, str]:
    artist = (track.artist or "").strip()
    title = (track.title or "").strip()
    if not title and " — " in (track.label or ""):
        artist, title = (track.label.split(" — ", 1) + [""])[:2]
    if not title:
        title = track.path.stem
    return artist, title


def _next_xml_id(collection: ET.Element) -> int:
    used = set()
    for track in collection.findall("TRACK"):
        tid = track.get("TrackID") or ""
        if tid.isdigit():
            used.add(int(tid))
    return (max(used) + 1) if used else 900000000


def ingest_xml_collection(collection: ET.Element, plan: SyncPlan, *, nml: Path | None = None) -> int:
    if not plan.ingest:
        return 0
    from ix_crate.dj_metadata import _genre_lookup_indexes, enrich_track_genre

    nml_path = nml or TRAKTOR_NML
    nml_by_path, music_by_path, by_inode = _genre_lookup_indexes(nml=nml_path)
    added = 0
    next_id = _next_xml_id(collection)
    used = set()
    for track in collection.findall("TRACK"):
        tid = track.get("TrackID") or ""
        if tid.isdigit():
            used.add(int(tid))
    if next_id in used:
        next_id = max(used) + 1
    for item in plan.playlists:
        still: list[TrackRef] = []
        seen = {hit.dest_key for hit in item.matched}
        ingested = 0
        for miss in item.missing:
            if not ingestible(miss):
                still.append(miss)
                continue
            miss = enrich_track_genre(
                miss,
                nml_by_path=nml_by_path,
                music_by_path=music_by_path,
                by_inode=by_inode,
            )
            while next_id in used:
                next_id += 1
            artist, title = _filing(miss)
            suffix = miss.path.suffix.lower()
            kind = (
                "M4A File"
                if ".stem." in miss.path.name.lower()
                else KIND.get(suffix, "M4A File")
            )
            tid = str(next_id)
            used.add(next_id)
            next_id += 1
            from ix_crate.dj_metadata import xml_track_attrs

            filing = TrackRef(
                path=miss.path,
                artist=artist,
                title=title,
                album=miss.album,
                genre=miss.genre,
                bpm=miss.bpm,
                key=miss.key,
                total_time=miss.total_time,
                comments=miss.comments,
            )
            ET.SubElement(
                collection,
                "TRACK",
                **xml_track_attrs(
                    filing,
                    tid=tid,
                    kind=kind,
                    size=miss.path.stat().st_size,
                    location=_rb_location(miss.path),
                ),
            )
            if tid not in seen:
                item.matched.append(Hit(path=miss.path, dest_key=tid, via="ingest"))
                seen.add(tid)
            ingested += 1
            added += 1
        item.missing = still
        item.ingested = ingested
    collection.set("Entries", str(len(collection.findall("TRACK"))))
    return added


def ingest_nml_collection(collection: ET.Element, plan: SyncPlan) -> int:
    if not plan.ingest:
        return 0
    added = 0
    for item in plan.playlists:
        still: list[TrackRef] = []
        seen = {hit.dest_key for hit in item.matched}
        ingested = 0
        for miss in item.missing:
            if not ingestible(miss):
                still.append(miss)
                continue
            artist, title = _filing(miss)
            directory, file_attr = _traktor_dir_file(miss.path.resolve())
            pk_type = "STEM" if ".stem." in miss.path.name.lower() else "TRACK"
            key = f"Macintosh HD{directory}{file_attr}"
            from ix_crate.dj_metadata import append_nml_analysis

            filing = TrackRef(
                path=miss.path,
                artist=artist,
                title=title,
                album=miss.album,
                genre=miss.genre,
                bpm=miss.bpm,
                key=miss.key,
                total_time=miss.total_time,
                comments=miss.comments,
            )
            entry = ET.SubElement(
                collection, "ENTRY", TITLE=filing.title, ARTIST=filing.artist
            )
            ET.SubElement(
                entry,
                "LOCATION",
                DIR=directory,
                FILE=file_attr,
                VOLUME="Macintosh HD",
                VOLUMEID="Macintosh HD",
            )
            append_nml_analysis(entry, filing)
            if key not in seen:
                item.matched.append(
                    Hit(path=miss.path, dest_key=key, via="ingest", extra=pk_type)
                )
                seen.add(key)
            ingested += 1
            added += 1
        item.missing = still
        item.ingested = ingested
    collection.set("ENTRIES", str(len(collection.findall("ENTRY"))))
    return added


def format_plan(plan: SyncPlan) -> str:
    lines = [
        f"crates {plan.source} → {plan.dest}  folder {plan.dest_folder}  "
        f"{len(plan.playlists)} playlist(s)"
    ]
    for item in plan.playlists:
        path = "/".join(item.folder + (item.name,)) if item.folder else item.name
        to_ingest = sum(1 for miss in item.missing if ingestible(miss))
        to_skip = sum(1 for miss in item.missing if not ingestible(miss))
        lines.append(
            f"  {path}: {len(item.matched)} in dest  {to_ingest} ingest  {to_skip} skip"
        )
        for miss in item.missing[:8]:
            loc = str(miss.path).replace(str(Path.home()), "~")
            lines.append(f"    MISS  {miss.label or miss.path.name}  {loc}")
        if len(item.missing) > 8:
            lines.append(f"    … {len(item.missing) - 8} more missing")
    return "\n".join(lines)


def _rb_root(playlists_el: ET.Element) -> ET.Element:
    root_node = playlists_el.find("NODE")
    if root_node is None:
        root_node = ET.SubElement(
            playlists_el, "NODE", Name="ROOT", Type="0", Count="0"
        )
    return root_node


def _rb_child_folder(parent: ET.Element, name: str) -> ET.Element:
    for node in parent.findall("NODE"):
        if node.get("Name") == name and node.get("Type") == "0":
            return node
    folder = ET.SubElement(parent, "NODE", Name=name, Type="0", Count="0")
    parent.set("Count", str(len(parent.findall("NODE"))))
    return folder


def _rb_set_playlist(folder: ET.Element, name: str, track_ids: list[str]) -> None:
    for node in list(folder.findall("NODE")):
        if node.get("Name") == name and node.get("Type") == "1":
            folder.remove(node)
    node = ET.SubElement(
        folder,
        "NODE",
        Name=name,
        Type="1",
        KeyType="0",
        Entries=str(len(track_ids)),
    )
    for tid in track_ids:
        ET.SubElement(node, "TRACK", Key=tid)
    folder.set("Count", str(len(folder.findall("NODE"))))


def _rb_folder_path(root_node: ET.Element, dest_folder: str, parts: tuple[str, ...]) -> ET.Element:
    folder = _rb_child_folder(root_node, dest_folder)
    for part in parts:
        if part in PROTECTED:
            raise ValueError(f"refusing to write into {part}")
        folder = _rb_child_folder(folder, part)
    return folder


def apply_xml(plan: SyncPlan, xml: Path, *, nml: Path | None = None) -> int:
    tree = ET.parse(xml)
    root = tree.getroot()
    playlists_el = root.find("PLAYLISTS")
    if playlists_el is None:
        playlists_el = ET.SubElement(root, "PLAYLISTS")
    root_node = _rb_root(playlists_el)
    if plan.replace_folder:
        for node in list(root_node.findall("NODE")):
            if node.get("Name") == plan.dest_folder and node.get("Type") == "0":
                root_node.remove(node)
                root_node.set("Count", str(len(root_node.findall("NODE"))))
                break
    collection = root.find("COLLECTION")
    if collection is None:
        collection = ET.SubElement(root, "COLLECTION", Entries="0")
    nml_path = nml or TRAKTOR_NML
    ingest_xml_collection(collection, plan, nml=nml_path)
    from ix_crate.dj_metadata import sync_xml_collection_genres

    filled, cleaned = sync_xml_collection_genres(collection, nml=nml_path)
    if filled or cleaned:
        print(
            f"  genre: filled {filled} empty  cleaned {cleaned} existing TRACK rows",
            flush=True,
        )
    written = 0
    for item in plan.playlists:
        folder = _rb_folder_path(
            root_node, plan.dest_folder, bridge_folder(item, plan.dest_folder)
        )
        _rb_set_playlist(folder, item.name, [hit.dest_key for hit in item.matched])
        written += 1
    backup = xml.with_suffix(xml.suffix + ".crates.bak")
    shutil.copy2(xml, backup)
    write_tree(tree, xml)
    return written


def _nml_root_folder(nml_root: ET.Element) -> ET.Element:
    playlists = nml_root.find("PLAYLISTS")
    if playlists is None:
        raise RuntimeError("Traktor NML is missing PLAYLISTS")
    folder = playlists.find("NODE")
    if folder is None:
        raise RuntimeError("Traktor NML is missing PLAYLISTS/NODE")
    return folder


def apply_nml(plan: SyncPlan, nml: Path) -> int:
    tree = ET.parse(nml)
    root = tree.getroot()
    root_folder = _nml_root_folder(root)
    dest = _ensure_traktor_folder(root_folder, plan.dest_folder)
    collection = root.find("COLLECTION")
    if collection is None:
        raise RuntimeError("Traktor NML is missing COLLECTION")
    ingest_nml_collection(collection, plan)
    written = 0
    for item in plan.playlists:
        if item.name in PROTECTED or any(part in PROTECTED for part in item.folder):
            continue
        parent = dest
        for part in bridge_folder(item, plan.dest_folder):
            parent = _ensure_traktor_folder(parent, part)
        playlist = _ensure_traktor_playlist(parent, item.name)
        for hit in item.matched:
            pk_type = hit.extra or "TRACK"
            entry = ET.SubElement(playlist, "ENTRY")
            ET.SubElement(entry, "PRIMARYKEY", TYPE=pk_type, KEY=hit.dest_key)
        playlist.set("ENTRIES", str(len(item.matched)))
        written += 1
    backup = nml.with_suffix(nml.suffix + ".crates.bak")
    shutil.copy2(nml, backup)
    write_tree(tree, nml)
    return written


def set_music_playlist(name: str, pids: list[str]) -> int:
    quoted = name.replace("\\", "\\\\").replace('"', '\\"')
    pid_list = ", ".join(f'"{pid}"' for pid in pids)
    script = f'''
tell application "Music"
  try
    set p to user playlist "{quoted}"
  on error
    set p to make new user playlist with properties {{name:"{quoted}"}}
  end try
  try
    delete (every track of p)
  end try
  set added to 0
  repeat with pid in {{{pid_list}}}
    set hits to file tracks of library playlist 1 whose persistent ID is pid
    if (count of hits) > 0 then
      duplicate (item 1 of hits) to p
      set added to added + 1
    end if
  end repeat
  return added as text
end tell
'''
    if not pids:
        script = f'''
tell application "Music"
  try
    set p to user playlist "{quoted}"
  on error
    set p to make new user playlist with properties {{name:"{quoted}"}}
  end try
  try
    delete (every track of p)
  end try
  return "0"
end tell
'''
    out = _run_osascript(script, timeout=300).strip()
    try:
        return int(out)
    except ValueError:
        return len(pids)


def apply_music(plan: SyncPlan) -> int:
    if not music_running():
        raise MusicDupesError("Music.app is not running. Open it and retry.")
    written = 0
    for item in plan.playlists:
        set_music_playlist(item.name, [hit.dest_key for hit in item.matched])
        written += 1
    return written


def load_source(
    source: str,
    *,
    names: set[str] | None,
    all_playlists: bool,
    nml: Path,
    xml: Path,
) -> list[CratePlaylist]:
    if source == "music":
        return load_music_playlists(names=names, all_playlists=all_playlists)
    if source == "nml":
        return load_nml_playlists(nml, names=names, all_playlists=all_playlists)
    return load_xml_playlists(xml, names=names, all_playlists=all_playlists)


def dest_index(dest: str, *, nml: Path, xml: Path) -> PathIndex:
    if dest == "xml":
        if not xml.is_file():
            raise FileNotFoundError(f"rekordbox.xml not found: {xml}")
        return xml_path_index(xml)
    if dest == "nml":
        if not nml.is_file():
            raise FileNotFoundError(f"collection.nml not found: {nml}")
        return nml_path_index(nml)
    index = music_path_index()
    if not index.by_path:
        raise MusicDupesError(
            "No Music.app location index. Enable Share iTunes Library XML "
            f"or add tracks to {itunes_library_xml()}."
        )
    return index


def write_report(plan: SyncPlan, extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "source": plan.source,
        "dest": plan.dest,
        "dest_folder": plan.dest_folder,
        "playlists": [
            {
                "name": item.name,
                "folder": list(item.folder),
                "matched": len(item.matched),
                "ingested": item.ingested,
                "missing": [
                    {"path": str(miss.path), "label": miss.label} for miss in item.missing
                ],
                "hits": [
                    {"path": str(hit.path), "key": hit.dest_key, "via": hit.via}
                    for hit in item.matched
                ],
            }
            for item in plan.playlists
        ],
        **(extra or {}),
    }
    dest = REPORTS / f"crates-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ix_crate crates", description=__doc__)
    parser.add_argument(
        "--from",
        dest="source",
        choices=APPS,
        default="music",
        help="Source crates (default music).",
    )
    parser.add_argument(
        "--to",
        dest="dest",
        choices=APPS,
        default="xml",
        help="Destination crates (default xml).",
    )
    parser.add_argument(
        "--playlist",
        action="append",
        default=[],
        help="Playlist name (repeatable). Full NML/XML path also matches.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Every user playlist except STEMIT / smart / library lists.",
    )
    parser.add_argument("--nml", type=Path, default=TRAKTOR_NML)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument(
        "--no-ingest",
        action="store_true",
        help="Do not add missing files to the dest collection (old skip-only behavior).",
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.source == args.dest:
        print("source and dest are the same app. Pick two of music / nml / xml.", flush=True)
        return 2
    if not args.playlist and not args.all:
        print("pass --playlist NAME or --all.", flush=True)
        return 2
    names = set(args.playlist) or None
    try:
        playlists = load_source(
            args.source,
            names=names,
            all_playlists=args.all,
            nml=args.nml,
            xml=args.xml,
        )
    except MusicDupesError as exc:
        print(exc, flush=True)
        return 2
    if not playlists:
        print("no matching playlists.", flush=True)
        return 2
    try:
        index = dest_index(args.dest, nml=args.nml, xml=args.xml)
    except (FileNotFoundError, MusicDupesError) as exc:
        print(exc, flush=True)
        return 2
    plan = SyncPlan(
        source=args.source,
        dest=args.dest,
        dest_folder=dest_folder_for(args.source, args.dest),
        playlists=plan_membership(playlists, index),
        replace_folder=bool(args.all and args.dest == "xml"),
        ingest=bool(args.dest != "music" and not args.no_ingest),
    )
    if plan.ingest:
        would = sum(
            1 for item in plan.playlists for miss in item.missing if ingestible(miss)
        )
        skipped = sum(
            1 for item in plan.playlists for miss in item.missing if not ingestible(miss)
        )
        print(f"  ingest {would} missing files into dest collection  skip {skipped}", flush=True)
    print(format_plan(plan), flush=True)
    report = write_report(plan, {"execute": bool(args.execute)})
    print(f"report {report}", flush=True)
    if not args.execute:
        print(
            "dry-run. pass --execute to rewrite playlist membership. "
            "Missing files that exist on disk get a Location row (Rekordbox/Traktor "
            "analyze after reload). .m4p and missing files stay skipped. "
            "Existing cues / energy / comments stay.",
            flush=True,
        )
        return 0
    if args.dest == "xml" and rekordbox_is_running():
        print("Rekordbox is open. Quit it before --execute writes rekordbox.xml.", flush=True)
        return 2
    if args.dest == "nml" and traktor_is_running():
        print("Traktor is open. Quit it before --execute writes collection.nml.", flush=True)
        return 2
    if args.dest == "xml":
        written = apply_xml(plan, args.xml)
        print(
            f"wrote {written} xml playlist(s) under {plan.dest_folder}. "
            "Reload rekordbox xml (<>). Don't ask again + No on tag overwrite.",
            flush=True,
        )
        return 0
    if args.dest == "nml":
        written = apply_nml(plan, args.nml)
        print(f"wrote {written} NML playlist(s) under {plan.dest_folder}.", flush=True)
        return 0
    try:
        written = apply_music(plan)
    except MusicDupesError as exc:
        print(exc, flush=True)
        return 2
    print(f"wrote {written} Music.app playlist(s).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
