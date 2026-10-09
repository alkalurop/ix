"""Mixed In Key playlists → rekordbox.xml and Traktor NML.

Reads ``Collection11.mikdb`` (cues, energy, Camelot key, file notes) and
writes a ``MIXED IN KEY`` folder in both libraries. The Library itself,
and any playlist that contains every Library track, stays out so a daily
CRATER pass does not restamp the whole collection. Name that playlist
with ``--playlist`` when you want it.

Hot cues (Rekordbox ``Num`` 0–7, Traktor ``HOTCUE`` 0–7) are replaced
with Mixed In Key cue points named ``Energy N``. Memory cues, grids, and
BPM stay. Comment becomes ``5A - Energy 6`` plus the file note, which is
the shape ``favorites`` already reads.

Dry-run default. Quit Rekordbox before xml. Quit Traktor before NML.
Mixed In Key may stay open — ``Collection11.mikdb`` is opened read-only.
"""

from __future__ import annotations

import argparse
import html
import json
import plistlib
import re
import shutil
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ix_crate.crates import (
    PathIndex,
    TrackRef,
    _next_xml_id,
    _nml_root_folder,
    _rb_folder_path,
    _rb_root,
    _rb_set_playlist,
    ingestible,
)
from ix_crate.dj_metadata import append_nml_analysis, xml_track_attrs
from ix_crate.favorites import HEX_COMMENT
from ix_crate.paths import REPORTS
from ix_crate.stems_playlists import (
    KIND,
    REKORDBOX_XML,
    TRAKTOR_NML,
    _ensure_traktor_folder,
    _ensure_traktor_playlist,
    _loc_to_path,
    _rb_location,
    _traktor_dir_file,
    _traktor_key,
    rekordbox_is_running,
)
from ix_crate.traktor_nml import traktor_is_running
from ix_crate.xml_io import write_tree

MIK_DB = Path.home() / "Library" / "Application Support" / "Mixedinkey" / "Collection11.mikdb"
FOLDER_NAME = "MIXED IN KEY"
TOOL_ID = "ix.crate.mixed-in-crate"
HOTCUE_SLOTS = 8

_PATH_IN_BOOKMARK = re.compile(
    rb"(/[^\x00]{1,500}?\.(?:wav|aiff|aif|mp3|m4a|flac|aac|mp4))",
    re.IGNORECASE,
)
_CAMELOT = re.compile(r"^(\d{1,2})\s*([ABab])$")
_MIK_COMMENT = re.compile(
    r"^\d{1,2}[ABab]\s*-\s*Energy\s+\d{1,2}(?:\s*-\s*(?P<rest>.*))?$",
    re.IGNORECASE,
)
_BARE_ENERGY = re.compile(r"^Energy\s+\d{1,2}$", re.IGNORECASE)
_HEX_BODY = re.compile(r"^(?:[0-9A-Fa-f]{8}\s*)+$")

# Traktor MUSICAL_KEY: C=0 … B=11, Cm=12 … Bm=23.
_MUSICAL: dict[str, int] = {
    "1A": 20,
    "2A": 15,
    "3A": 22,
    "4A": 17,
    "5A": 12,
    "6A": 19,
    "7A": 14,
    "8A": 21,
    "9A": 16,
    "10A": 23,
    "11A": 18,
    "12A": 13,
    "1B": 11,
    "2B": 6,
    "3B": 1,
    "4B": 8,
    "5B": 3,
    "6B": 10,
    "7B": 5,
    "8B": 0,
    "9B": 7,
    "10B": 2,
    "11B": 9,
    "12B": 4,
}


@dataclass(frozen=True)
class MikCue:
    seconds: float
    energy: int


@dataclass
class MikTrack:
    path: Path
    artist: str = ""
    title: str = ""
    album: str = ""
    genre: str = ""
    key: str = ""
    energy: int = 0
    tempo: float = 0.0
    notes: list[str] = field(default_factory=list)
    cues: list[MikCue] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} — {self.title}"
        return self.title or self.path.name


@dataclass
class MikPlaylist:
    name: str
    tracks: list[MikTrack] = field(default_factory=list)


@dataclass(frozen=True)
class SkippedPlaylist:
    name: str
    count: int
    reason: str


def bookmark_path(data: bytes | None) -> Path | None:
    """Absolute path stored inside a Mixed In Key security-scoped bookmark."""
    if not data:
        return None
    found: list[Path] = []
    for match in _PATH_IN_BOOKMARK.finditer(data):
        try:
            found.append(Path(match.group(1).decode("utf-8")))
        except UnicodeDecodeError:
            continue
    for path in found:
        try:
            if path.is_file():
                return path.resolve()
        except OSError:
            continue
    return found[-1] if found else None


def normalize_camelot(raw: str) -> str:
    match = _CAMELOT.match((raw or "").strip())
    if not match:
        return ""
    number = int(match.group(1))
    if not 1 <= number <= 12:
        return ""
    return f"{number}{match.group(2).upper()}"


def musical_key_value(camelot: str) -> int | None:
    return _MUSICAL.get(normalize_camelot(camelot))


def energy_int(value: float | int | None) -> int:
    if value is None:
        return 0
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return number if 1 <= number <= 10 else 0


def cue_name(level: int) -> str:
    if 1 <= level <= 10:
        return f"Energy {level}"
    return "Cue"


def _human_note(value: str) -> str:
    text = html.unescape(value or "").strip()
    if not text or HEX_COMMENT.match(text) or _HEX_BODY.match(text):
        return ""
    match = _MIK_COMMENT.match(text)
    if match:
        text = (match.group("rest") or "").strip()
    if not text or _BARE_ENERGY.match(text) or _HEX_BODY.match(text):
        return ""
    return text


def _deref(objects: list, obj: object) -> object:
    if isinstance(obj, plistlib.UID):
        index = int(obj)
        if 0 <= index < len(objects):
            return objects[index]
    return obj


def _as_list(objects: list, obj: object) -> list:
    obj = _deref(objects, obj)
    if isinstance(obj, list):
        return [_deref(objects, item) for item in obj]
    if isinstance(obj, dict) and "NS.objects" in obj:
        return [_deref(objects, item) for item in obj["NS.objects"]]
    return []


def notes_from_tag_blob(blob: bytes | None) -> list[str]:
    """Human comments from the NSKeyedArchiver blob on ``ZTAGCOMMENTS``."""
    if not blob:
        return []
    try:
        payload = plistlib.loads(blob)
    except Exception:
        return []
    objects = payload.get("$objects")
    if not isinstance(objects, list):
        return []
    notes: list[str] = []
    seen: set[str] = set()
    for obj in objects:
        if not isinstance(obj, dict) or "NS.keys" not in obj:
            continue
        keys = _as_list(objects, obj.get("NS.keys"))
        values = _as_list(objects, obj.get("NS.objects"))
        mapping = {
            key: value
            for key, value in zip(keys, values)
            if isinstance(key, str)
        }
        if "comment" not in mapping and "originalComment" not in mapping:
            continue
        for field_name in ("originalComment", "comment"):
            raw = mapping.get(field_name)
            if not isinstance(raw, str):
                continue
            note = _human_note(raw)
            if note and note not in seen:
                seen.add(note)
                notes.append(note)
            if note:
                break
    return notes


def _existing_extra(existing: str) -> str:
    text = (existing or "").strip()
    if not text or HEX_COMMENT.match(text) or _HEX_BODY.match(text):
        return ""
    match = _MIK_COMMENT.match(text)
    if match:
        text = (match.group("rest") or "").strip()
    elif _BARE_ENERGY.match(text):
        return ""
    if not text or HEX_COMMENT.match(text) or _HEX_BODY.match(text):
        return ""
    return text


def build_comment(key: str, energy: int, notes: list[str], existing: str = "") -> str:
    parts: list[str] = []
    camelot = normalize_camelot(key)
    level = energy_int(energy)
    if camelot and level:
        parts.append(f"{camelot} - Energy {level}")
    elif camelot:
        parts.append(camelot)
    elif level:
        parts.append(f"Energy {level}")
    for note in notes:
        human = _human_note(note)
        if human and human not in parts:
            parts.append(human)
    extra = _existing_extra(existing)
    if extra and extra not in parts:
        parts.append(extra)
    return " - ".join(parts)


def _connect(db: Path) -> sqlite3.Connection:
    uri = db.expanduser().resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _song_ids(con: sqlite3.Connection, collection_id: int) -> list[int]:
    rows = con.execute(
        "SELECT Z_5SONGS FROM Z_1SONGS WHERE Z_1COLLECTIONS = ? ORDER BY rowid",
        (collection_id,),
    ).fetchall()
    return [int(row[0]) for row in rows]


def _tracks_for(
    con: sqlite3.Connection,
    song_ids: list[int],
) -> list[MikTrack]:
    if not song_ids:
        return []
    placeholders = ",".join("?" for _ in song_ids)
    songs = {
        int(row["Z_PK"]): row
        for row in con.execute(
            f"""
            SELECT Z_PK, ZARTIST, ZNAME, ZALBUM, ZGENRE, ZKEY, ZENERGY, ZTEMPO,
                   ZCOMMENT, ZBOOKMARKDATA, ZTAGCOMMENTS
            FROM ZSONG WHERE Z_PK IN ({placeholders})
            """,
            song_ids,
        )
    }
    cues: dict[int, list[MikCue]] = {song_id: [] for song_id in song_ids}
    for row in con.execute(
        f"""
        SELECT ZSONG, ZTIME, ZENERGYLEVEL FROM ZCUEPOINT
        WHERE ZSONG IN ({placeholders})
        ORDER BY ZTIME
        """,
        song_ids,
    ):
        song_id = int(row["ZSONG"])
        bucket = cues.get(song_id)
        if bucket is None or len(bucket) >= HOTCUE_SLOTS:
            continue
        if row["ZTIME"] is None:
            continue
        bucket.append(MikCue(seconds=float(row["ZTIME"]), energy=energy_int(row["ZENERGYLEVEL"])))
    tracks: list[MikTrack] = []
    for song_id in song_ids:
        row = songs.get(song_id)
        if row is None:
            continue
        path = bookmark_path(row["ZBOOKMARKDATA"]) or Path(f"/mik-unresolved/{song_id}")
        notes = notes_from_tag_blob(row["ZTAGCOMMENTS"])
        zcomment = _human_note(row["ZCOMMENT"] or "")
        if zcomment and zcomment not in notes:
            notes.append(zcomment)
        tempo = 0.0
        try:
            tempo = float(row["ZTEMPO"] or 0)
        except (TypeError, ValueError):
            tempo = 0.0
        if not 40 <= tempo <= 220:
            tempo = 0.0
        tracks.append(
            MikTrack(
                path=path,
                artist=(row["ZARTIST"] or "").strip(),
                title=(row["ZNAME"] or "").strip(),
                album=(row["ZALBUM"] or "").strip(),
                genre=(row["ZGENRE"] or "").strip(),
                key=normalize_camelot(row["ZKEY"] or ""),
                energy=energy_int(row["ZENERGY"]),
                tempo=tempo,
                notes=notes,
                cues=cues.get(song_id, []),
            )
        )
    return tracks


def load_playlists(
    db: Path | None = None,
    *,
    names: set[str] | None = None,
) -> tuple[list[MikPlaylist], list[SkippedPlaylist]]:
    path = (db or MIK_DB).expanduser()
    con = _connect(path)
    try:
        collections = con.execute(
            """
            SELECT Z_PK, ZNAME, ZISLIBRARY
            FROM ZCOLLECTION
            ORDER BY ZINDEX, Z_PK
            """
        ).fetchall()
        library_ids: set[int] = set()
        for row in collections:
            if int(row["ZISLIBRARY"] or 0):
                library_ids.update(_song_ids(con, int(row["Z_PK"])))
        playlists: list[MikPlaylist] = []
        skipped: list[SkippedPlaylist] = []
        for row in collections:
            name = (row["ZNAME"] or "").strip() or "Untitled"
            song_ids = _song_ids(con, int(row["Z_PK"]))
            if names is not None and name not in names:
                continue
            if int(row["ZISLIBRARY"] or 0):
                skipped.append(SkippedPlaylist(name, len(song_ids), "library"))
                continue
            explicit = names is not None and name in names
            if library_ids and set(song_ids) == library_ids and not explicit:
                skipped.append(SkippedPlaylist(name, len(song_ids), "library mirror"))
                continue
            playlists.append(MikPlaylist(name=name, tracks=_tracks_for(con, song_ids)))
        return playlists, skipped
    finally:
        con.close()


def _short(path: Path) -> str:
    try:
        return "~/" + path.resolve().relative_to(Path.home()).as_posix()
    except (OSError, ValueError):
        return str(path)


def _placement(track: MikTrack, index: PathIndex | None) -> str:
    try:
        on_disk = track.path.is_file()
    except OSError:
        on_disk = False
    if not on_disk:
        return "miss"
    if index is None:
        return "file"
    if index.lookup(track.path):
        return "match"
    return "new"


def format_plan(
    playlists: list[MikPlaylist],
    skipped: list[SkippedPlaylist],
    *,
    xml_index: PathIndex | None = None,
    nml_index: PathIndex | None = None,
) -> str:
    lines = [f"mixed-in-crate  {FOLDER_NAME}  {len(playlists)} playlist(s)"]
    for item in skipped:
        lines.append(f"  skip {item.name} ({item.reason}, {item.count} tracks)")
    for playlist in playlists:
        cues = sum(len(track.cues) for track in playlist.tracks)
        noted = sum(1 for track in playlist.tracks if track.notes)
        xml_bits = _count_line(playlist, xml_index)
        nml_bits = _count_line(playlist, nml_index)
        lines.append(
            f"  {playlist.name}: {len(playlist.tracks)} tracks  "
            f"xml {xml_bits}  nml {nml_bits}  cues {cues}  notes {noted}"
        )
        missing = [track for track in playlist.tracks if _placement(track, None) == "miss"]
        for track in missing[:8]:
            lines.append(f"    MISS  {track.label}  {_short(track.path)}")
        if len(missing) > 8:
            lines.append(f"    … {len(missing) - 8} more missing")
    return "\n".join(lines)


def _count_line(playlist: MikPlaylist, index: PathIndex | None) -> str:
    if index is None:
        return "—"
    match = new = miss = 0
    for track in playlist.tracks:
        place = _placement(track, index)
        if place == "match":
            match += 1
        elif place == "new":
            new += 1
        else:
            miss += 1
    return f"{match} match / {new} new / {miss} miss"


def stamp_xml_track(track: ET.Element, mik: MikTrack) -> None:
    if mik.key:
        track.set("Tonality", mik.key)
    comment = build_comment(mik.key, mik.energy, mik.notes, track.get("Comments") or "")
    if comment:
        track.set("Comments", comment)
    if not mik.cues:
        return
    for mark in list(track.findall("POSITION_MARK")):
        number = mark.get("Num")
        if number is not None and number.isdigit() and 0 <= int(number) <= 7:
            track.remove(mark)
    for index, cue in enumerate(mik.cues[:HOTCUE_SLOTS]):
        ET.SubElement(
            track,
            "POSITION_MARK",
            Name=cue_name(cue.energy),
            Type="0",
            Start=f"{cue.seconds:.3f}",
            Num=str(index),
        )


def stamp_nml_entry(entry: ET.Element, mik: MikTrack) -> None:
    info = entry.find("INFO")
    if info is None:
        info = ET.SubElement(entry, "INFO")
    if mik.key:
        info.set("KEY", mik.key)
    comment = build_comment(mik.key, mik.energy, mik.notes, info.get("COMMENT") or "")
    if comment:
        info.set("COMMENT", comment)
    value = musical_key_value(mik.key)
    if value is not None:
        musical = entry.find("MUSICAL_KEY")
        if musical is None:
            ET.SubElement(entry, "MUSICAL_KEY", VALUE=str(value))
        else:
            musical.set("VALUE", str(value))
    if not mik.cues:
        return
    for cue in list(entry.findall("CUE_V2")):
        hotcue = cue.get("HOTCUE")
        if hotcue is not None and hotcue.isdigit() and 0 <= int(hotcue) <= 7:
            entry.remove(cue)
    for index, cue in enumerate(mik.cues[:HOTCUE_SLOTS]):
        ET.SubElement(
            entry,
            "CUE_V2",
            NAME=cue_name(cue.energy),
            DISPL_ORDER="0",
            TYPE="0",
            START=f"{cue.seconds * 1000:.6f}",
            LEN="0.000000",
            REPEATS="-1",
            HOTCUE=str(index),
        )


def _filing_ref(mik: MikTrack) -> TrackRef:
    bpm = f"{mik.tempo:.2f}" if mik.tempo else ""
    return TrackRef(
        path=mik.path,
        artist=mik.artist,
        title=mik.title or mik.path.stem,
        album=mik.album,
        genre=mik.genre,
        bpm=bpm,
        key=mik.key,
        comments=build_comment(mik.key, mik.energy, mik.notes),
    )


def _xml_index(collection: ET.Element) -> tuple[PathIndex, dict[str, ET.Element]]:
    index = PathIndex()
    by_id: dict[str, ET.Element] = {}
    for track in collection.findall("TRACK"):
        tid = track.get("TrackID") or ""
        path = None
        loc = track.get("Location") or ""
        if loc:
            from ix_crate.crates import parse_rb_location

            path = parse_rb_location(loc)
        if tid and path is not None:
            by_id[tid] = track
            index.add(path, tid)
    return index, by_id


def _nml_index(collection: ET.Element) -> tuple[PathIndex, dict[str, ET.Element]]:
    index = PathIndex()
    by_key: dict[str, ET.Element] = {}
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
        pk_type = "STEM" if ".stem." in file_attr.lower() else "TRACK"
        key = f"{volume}{directory}{file_attr}"
        if key not in by_key:
            by_key[key] = entry
        index.add(path, key, extra=pk_type)
    return index, by_key


def _ingest_xml(collection: ET.Element, mik: MikTrack, next_id: int, used: set[int]) -> tuple[ET.Element, str, int]:
    while next_id in used:
        next_id += 1
    tid = str(next_id)
    used.add(next_id)
    suffix = mik.path.suffix.lower()
    kind = KIND.get(suffix, "WAV File")
    element = ET.SubElement(
        collection,
        "TRACK",
        **xml_track_attrs(
            _filing_ref(mik),
            tid=tid,
            kind=kind,
            size=mik.path.stat().st_size,
            location=_rb_location(mik.path),
        ),
    )
    stamp_xml_track(element, mik)
    return element, tid, next_id + 1


def _ingest_nml(collection: ET.Element, mik: MikTrack) -> tuple[ET.Element, str, str]:
    pk_type, key = _traktor_key(mik.path)
    ref = _filing_ref(mik)
    entry = ET.SubElement(collection, "ENTRY", TITLE=ref.title, ARTIST=ref.artist)
    directory, file_attr = _traktor_dir_file(mik.path.resolve())
    ET.SubElement(
        entry,
        "LOCATION",
        DIR=directory,
        FILE=file_attr,
        VOLUME="Macintosh HD",
        VOLUMEID="Macintosh HD",
    )
    append_nml_analysis(entry, ref)
    stamp_nml_entry(entry, mik)
    return entry, key, pk_type


def write_xml(playlists: list[MikPlaylist], xml: Path) -> int:
    if not playlists:
        return 0
    tree = ET.parse(xml)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        collection = ET.SubElement(root, "COLLECTION", Entries="0")
    index, by_id = _xml_index(collection)
    used: set[int] = set()
    for tid in by_id:
        if tid.isdigit():
            used.add(int(tid))
    next_id = _next_xml_id(collection)
    playlists_el = root.find("PLAYLISTS")
    if playlists_el is None:
        playlists_el = ET.SubElement(root, "PLAYLISTS")
    folder = _rb_folder_path(_rb_root(playlists_el), FOLDER_NAME, ())
    keep = {item.name for item in playlists}
    for node in list(folder.findall("NODE")):
        if node.get("Type") == "1" and node.get("Name") not in keep:
            folder.remove(node)
    written = 0
    for playlist in playlists:
        ids: list[str] = []
        seen: set[str] = set()
        for mik in playlist.tracks:
            if not ingestible(TrackRef(path=mik.path)):
                continue
            hit = index.lookup(mik.path)
            if hit is None:
                _element, tid, next_id = _ingest_xml(collection, mik, next_id, used)
                index.add(mik.path, tid)
                by_id[tid] = _element
            else:
                tid = hit[0]
                element = by_id.get(tid)
                if element is None:
                    continue
                stamp_xml_track(element, mik)
            if tid not in seen:
                seen.add(tid)
                ids.append(tid)
        _rb_set_playlist(folder, playlist.name, ids)
        written += 1
    collection.set("Entries", str(len(collection.findall("TRACK"))))
    backup = xml.with_suffix(xml.suffix + ".mik.bak")
    shutil.copy2(xml, backup)
    write_tree(tree, xml)
    return written


def _prune_nml_playlists(folder: ET.Element, keep: set[str]) -> None:
    subnodes = folder.find("SUBNODES")
    if subnodes is None:
        return
    for node in list(subnodes.findall("NODE")):
        if node.get("TYPE") == "PLAYLIST" and node.get("NAME") not in keep:
            subnodes.remove(node)
    subnodes.set("COUNT", str(len(list(subnodes))))


def write_nml(playlists: list[MikPlaylist], nml: Path) -> int:
    if not playlists:
        return 0
    tree = ET.parse(nml)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        raise RuntimeError("Traktor NML is missing COLLECTION")
    index, by_key = _nml_index(collection)
    folder = _ensure_traktor_folder(_nml_root_folder(root), FOLDER_NAME)
    _prune_nml_playlists(folder, {item.name for item in playlists})
    written = 0
    for playlist in playlists:
        node = _ensure_traktor_playlist(folder, playlist.name)
        keys: list[tuple[str, str]] = []
        seen: set[str] = set()
        for mik in playlist.tracks:
            if not ingestible(TrackRef(path=mik.path)):
                continue
            hit = index.lookup(mik.path)
            if hit is None:
                _entry, key, pk_type = _ingest_nml(collection, mik)
                index.add(mik.path, key, extra=pk_type)
                by_key[key] = _entry
            else:
                key, _via = hit
                pk_type = index.extra.get(key, "TRACK")
                entry = by_key.get(key)
                if entry is None:
                    continue
                stamp_nml_entry(entry, mik)
            if key not in seen:
                seen.add(key)
                keys.append((pk_type, key))
        for pk_type, key in keys:
            row = ET.SubElement(node, "ENTRY")
            ET.SubElement(row, "PRIMARYKEY", TYPE=pk_type, KEY=key)
        node.set("ENTRIES", str(len(keys)))
        written += 1
    collection.set("ENTRIES", str(len(collection.findall("ENTRY"))))
    backup = nml.with_suffix(nml.suffix + ".mik.bak")
    shutil.copy2(nml, backup)
    write_tree(tree, nml)
    return written


def write_report(
    playlists: list[MikPlaylist],
    skipped: list[SkippedPlaylist],
    extra: dict | None = None,
) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "folder": FOLDER_NAME,
        "playlists": [
            {
                "name": item.name,
                "tracks": len(item.tracks),
                "cues": sum(len(track.cues) for track in item.tracks),
                "notes": sum(1 for track in item.tracks if track.notes),
            }
            for item in playlists
        ],
        "skipped": [
            {"name": item.name, "count": item.count, "reason": item.reason}
            for item in skipped
        ],
        **(extra or {}),
    }
    dest = REPORTS / f"mixed-in-crate-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def _indexes(xml: Path, nml: Path) -> tuple[PathIndex | None, PathIndex | None]:
    from ix_crate.crates import nml_path_index, xml_path_index

    xml_index = xml_path_index(xml) if xml.is_file() else None
    nml_index = nml_path_index(nml) if nml.is_file() else None
    return xml_index, nml_index


def run(
    *,
    execute: bool,
    db: Path | None = None,
    nml: Path | None = None,
    xml: Path | None = None,
    playlists: list[str] | None = None,
) -> int:
    db_path = (db or MIK_DB).expanduser()
    nml_path = nml or TRAKTOR_NML
    xml_path = xml or REKORDBOX_XML
    if not db_path.is_file():
        print(f"Mixed In Key database not found: {db_path}", flush=True)
        return 0
    names = set(playlists) if playlists else None
    try:
        loaded, skipped = load_playlists(db_path, names=names)
    except sqlite3.Error as exc:
        print(f"Mixed In Key database could not be read ({exc}).", flush=True)
        return 2
    if names:
        found = {item.name for item in loaded} | {item.name for item in skipped}
        for name in playlists or []:
            if name not in found:
                print(f"Mixed In Key playlist not found: {name}", flush=True)
    xml_index, nml_index = _indexes(xml_path, nml_path)
    print(format_plan(loaded, skipped, xml_index=xml_index, nml_index=nml_index), flush=True)
    report = write_report(loaded, skipped, {"execute": execute})
    print(f"report {report}", flush=True)
    if not execute:
        print(
            "dry-run. pass --execute to write cues, energy, key, notes, "
            f"and {FOLDER_NAME} playlists into rekordbox.xml and collection.nml.",
            flush=True,
        )
        return 0
    if not loaded:
        print("no Mixed In Key playlists to write.", flush=True)
        return 0
    if rekordbox_is_running():
        print("Rekordbox is open. Quit it before --execute writes rekordbox.xml.", flush=True)
        return 2
    if traktor_is_running():
        print("Traktor is open. Quit it before --execute writes collection.nml.", flush=True)
        return 2
    if not xml_path.is_file():
        print(f"rekordbox.xml not found: {xml_path}", flush=True)
        return 2
    if not nml_path.is_file():
        print(f"collection.nml not found: {nml_path}", flush=True)
        return 2
    xml_written = write_xml(loaded, xml_path)
    nml_written = write_nml(loaded, nml_path)
    print(
        f"{FOLDER_NAME}  xml playlists {xml_written}  nml playlists {nml_written}",
        flush=True,
    )
    print("Reload rekordbox xml (<>). Don't ask again + No on tag overwrite.", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ix_crate mixed-in-crate", description=__doc__)
    parser.add_argument("--db", type=Path, default=MIK_DB)
    parser.add_argument("--nml", type=Path, default=TRAKTOR_NML)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument(
        "--playlist",
        action="append",
        default=None,
        help="Only this Mixed In Key playlist. Repeatable. Names a library mirror when you want that whole list.",
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(
        execute=args.execute,
        db=args.db,
        nml=args.nml,
        xml=args.xml,
        playlists=args.playlist,
    )


if __name__ == "__main__":
    raise SystemExit(main())
