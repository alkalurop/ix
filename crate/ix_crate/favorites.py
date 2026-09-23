"""Record Rekordbox + Traktor plays into public JSON + daily crates.

Artist and title only — never disk paths. Mixes count; STEMIT stems /
acapellas / instrumentals are skipped. master.db is encrypted; Rekordbox
PlayCount comes from rekordbox.xml. Traktor PLAYCOUNT / LAST_PLAYED come
from collection.nml. heard_s is play_count × track length.

Also writes a compact play-patterns file (genre / BPM / energy / vibe)
for the local LLM. Played crate is the 100 most recent. Daily
``Not Played But Should`` has three subcrates: neglected genres, random,
and favorites-match. Library tracks whose genre or title says acapella
stay out of those picks. The same ``--playlists`` write adds
``MUSIC/GENRES/<genre>`` for the Apple Music library and
``MUSIC/ACAPELLAS/<genre>`` for STEMIT vocals matched to that library
(``library_genres`` / ``acapella_crates``). Skips playlist writes when
nothing new was played.

Live JSON stays off nightly git. ``--snapshot`` copies a quarterly file
into ``configs/quarterly/``. Dry-run default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ix_crate.identify import normalize_title
from ix_crate.music_genre import clean_genre
from ix_crate.stems_playlists import (
    REKORDBOX_XML,
    TRAKTOR_NML,
    classify,
    rekordbox_is_running,
)
from ix_crate.traktor_nml import traktor_is_running

REPO = Path(__file__).resolve().parents[2]
FAVORITES_JSON = REPO / "configs" / "favorites.json"
PATTERNS_JSON = REPO / "configs" / "play-patterns.json"
QUARTERLY_DIR = REPO / "configs" / "quarterly"
SKIP_CRATES = frozenset({"Stems", "Acapellas", "Instrumentals"})
TOOL_ID = "ix.crate.favorites"
PLAYED_LIMIT = 100
SUGGEST_EACH = 12
PLAYED_NAME = "Played"
NPBS_FOLDER = "Not Played But Should"
NEGLECTED = "Neglected genres"
RANDOM = "Random"
FAVORITES_MATCH = "Favorites"
ACAPELLA_NAME = "Acapella"
ACAPELLA_GENRES = frozenset(
    {"acapella", "accapella", "a cappella", "a capella", "acapela"}
)
ACAPELLA_TITLE = re.compile(r"\b(?:a\s*c+ap+ella|acapella|cappella)\b", re.I)
ENERGY_RE = re.compile(r"Energy\s+(\d{1,2})", re.I)
CAMELOT_RE = re.compile(r"\b(\d{1,2}[ABab])\b")
HEX_COMMENT = re.compile(r"^\s*[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{8}")


@dataclass
class PlayRow:
    artist: str
    title: str
    duration_s: int = 0
    plays: dict[str, int] = field(default_factory=dict)
    last_played: str = ""
    first_seen: str = ""
    rating: int = 0
    genre: str = ""
    bpm: float = 0.0
    energy: int = 0
    key: str = ""
    xml_id: str = ""
    nml_key: str = ""
    nml_type: str = ""

    @property
    def play_count(self) -> int:
        return sum(self.plays.values())

    @property
    def favorite(self) -> bool:
        return self.rating >= 1

    @property
    def vibe(self) -> str:
        return vibe_of(self)


@dataclass
class RecordResult:
    payload: dict
    rows: dict[str, PlayRow]
    fingerprint: str
    patterns: dict


def track_key(artist: str, title: str) -> str:
    return f"{normalize_title(artist)}\t{normalize_title(title)}"


def skip_role(name: str) -> bool:
    if not name:
        return False
    crate = classify(Path(name))
    return crate in SKIP_CRATES


def stars(raw: str | int | None) -> int:
    try:
        value = int(float(str(raw or "0")))
    except ValueError:
        return 0
    if value <= 0:
        return 0
    if value <= 5:
        return value
    return min(5, value // 51)


def iso_date(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "-" in text and len(text) >= 10 and text[4] == "-":
        return text[:10]
    parts = text.replace("-", "/").split("/")
    if len(parts) != 3:
        return ""
    try:
        year, month, day = (int(p) for p in parts)
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return ""


def parse_energy(comment: str) -> int:
    if not comment or HEX_COMMENT.match(comment):
        return 0
    hit = ENERGY_RE.search(comment)
    if not hit:
        return 0
    value = int(hit.group(1))
    return value if 1 <= value <= 10 else 0


def parse_key(raw: str, comment: str = "") -> str:
    text = (raw or "").strip()
    if text:
        return text
    if comment and not HEX_COMMENT.match(comment):
        hit = CAMELOT_RE.search(comment)
        if hit:
            return hit.group(1).upper()
    return ""


def parse_bpm(raw: str | float | None) -> float:
    try:
        value = float(raw or 0)
    except ValueError:
        return 0.0
    return value if 40 <= value <= 220 else 0.0


def bpm_band(bpm: float) -> str:
    if bpm < 40:
        return "?"
    if bpm < 115:
        return "<115"
    if bpm < 122:
        return "115-122"
    if bpm < 128:
        return "122-128"
    if bpm < 135:
        return "128-135"
    return "135+"


def vibe_of(row: PlayRow) -> str:
    genre = row.genre or "untagged"
    energy = f"e{row.energy}" if row.energy else "e?"
    key = (row.key or "?").upper()
    return f"{genre}|{bpm_band(row.bpm)}|{energy}|{key}"


def newer_date(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return max(left, right)


def older_date(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return min(left, right)


def _fill_text(into: str, incoming: str) -> str:
    return incoming if incoming and not into else into


def merge_row(into: PlayRow, incoming: PlayRow) -> None:
    if incoming.duration_s and not into.duration_s:
        into.duration_s = incoming.duration_s
    elif incoming.duration_s:
        into.duration_s = max(into.duration_s, incoming.duration_s)
    for source, count in incoming.plays.items():
        into.plays[source] = max(into.plays.get(source, 0), count)
    into.last_played = newer_date(into.last_played, incoming.last_played)
    into.first_seen = older_date(into.first_seen, incoming.first_seen)
    into.rating = max(into.rating, incoming.rating)
    into.genre = _fill_text(into.genre, incoming.genre)
    if incoming.bpm and not into.bpm:
        into.bpm = incoming.bpm
    into.energy = into.energy or incoming.energy
    into.key = _fill_text(into.key, incoming.key)
    into.xml_id = _fill_text(into.xml_id, incoming.xml_id)
    into.nml_key = _fill_text(into.nml_key, incoming.nml_key)
    into.nml_type = _fill_text(into.nml_type, incoming.nml_type)
    if incoming.artist and (not into.artist or len(incoming.artist) > len(into.artist)):
        into.artist = incoming.artist
    if incoming.title and (not into.title or len(incoming.title) > len(into.title)):
        into.title = incoming.title


def public_row(row: PlayRow, *, played: bool) -> dict:
    payload = {
        "artist": row.artist,
        "title": row.title,
        "play_count": row.play_count if played else 0,
        "duration_s": row.duration_s,
        "favorite": row.favorite,
    }
    if row.genre:
        payload["genre"] = row.genre
    if row.bpm:
        payload["bpm"] = round(row.bpm, 2)
    if row.energy:
        payload["energy"] = row.energy
    if row.key:
        payload["key"] = row.key
    if row.genre or row.bpm or row.energy or row.key:
        payload["vibe"] = row.vibe
    if played:
        payload["plays"] = {key: value for key, value in sorted(row.plays.items()) if value}
        payload["heard_s"] = row.play_count * row.duration_s if row.duration_s else 0
        if row.last_played:
            payload["last_played"] = row.last_played
    if row.first_seen:
        payload["first_seen"] = row.first_seen
    if row.rating:
        payload["rating"] = row.rating
    return payload


def assert_public(payload: dict) -> None:
    blob = json.dumps(payload, ensure_ascii=False)
    for needle in ("/Users/", "file://", "file:\\\\", "\\\\Users\\"):
        if needle in blob:
            raise ValueError(f"public favorites JSON must not contain {needle!r}")


def harvest_nml(nml: Path) -> dict[str, PlayRow]:
    found: dict[str, PlayRow] = {}
    if not nml.is_file():
        return found
    for _event, el in ET.iterparse(nml, events=("end",)):
        if el.tag != "ENTRY":
            continue
        location = el.find("LOCATION")
        filename = (location.get("FILE") if location is not None else "") or ""
        if skip_role(filename):
            el.clear()
            continue
        title = (el.get("TITLE") or "").strip()
        artist = (el.get("ARTIST") or "").strip()
        if not normalize_title(title):
            el.clear()
            continue
        info = el.find("INFO")
        attrib = info.attrib if info is not None else {}
        comment = attrib.get("COMMENT") or ""
        tempo = el.find("TEMPO")
        bpm = parse_bpm(tempo.get("BPM") if tempo is not None else 0)
        try:
            playcount = int(attrib.get("PLAYCOUNT") or "0")
        except ValueError:
            playcount = 0
        try:
            duration = int(float(attrib.get("PLAYTIME") or attrib.get("PLAYTIME_FLOAT") or "0"))
        except ValueError:
            duration = 0
        volume = (location.get("VOLUME") if location is not None else "") or "Macintosh HD"
        directory = (location.get("DIR") if location is not None else "") or ""
        nml_key = f"{volume}{directory}{filename}" if filename else ""
        row = PlayRow(
            artist=artist,
            title=title,
            duration_s=duration,
            plays={"traktor": max(playcount, 0)},
            last_played=iso_date(attrib.get("LAST_PLAYED") or ""),
            first_seen=iso_date(attrib.get("IMPORT_DATE") or ""),
            rating=stars(attrib.get("RANKING")),
            genre=clean_genre(attrib.get("GENRE") or ""),
            bpm=bpm,
            energy=parse_energy(comment),
            key=parse_key(attrib.get("KEY") or "", comment),
            nml_key=nml_key,
            nml_type="STEM" if ".stem." in filename.lower() else "TRACK",
        )
        key = track_key(artist, title)
        if key in found:
            merge_row(found[key], row)
        else:
            found[key] = row
        el.clear()
    return found


def harvest_xml(xml: Path) -> dict[str, PlayRow]:
    found: dict[str, PlayRow] = {}
    if not xml.is_file():
        return found
    for _event, el in ET.iterparse(xml, events=("end",)):
        if el.tag != "TRACK" or not el.get("TrackID"):
            continue
        location = el.get("Location") or ""
        name = Path(location.split("/")[-1] if location else "").name
        if skip_role(name):
            el.clear()
            continue
        title = (el.get("Name") or "").strip()
        artist = (el.get("Artist") or "").strip()
        if not normalize_title(title):
            el.clear()
            continue
        try:
            playcount = int(el.get("PlayCount") or "0")
        except ValueError:
            playcount = 0
        try:
            duration = int(float(el.get("TotalTime") or "0"))
        except ValueError:
            duration = 0
        comment = el.get("Comments") or ""
        row = PlayRow(
            artist=artist,
            title=title,
            duration_s=duration,
            plays={"rekordbox": max(playcount, 0)},
            first_seen=iso_date(el.get("DateAdded") or ""),
            rating=stars(el.get("Rating")),
            genre=clean_genre(el.get("Genre") or ""),
            bpm=parse_bpm(el.get("AverageBpm")),
            energy=parse_energy(comment),
            key=parse_key(el.get("Tonality") or "", comment),
            xml_id=el.get("TrackID") or "",
        )
        key = track_key(artist, title)
        if key in found:
            merge_row(found[key], row)
        else:
            found[key] = row
        el.clear()
    return found


def combine(*harvests: dict[str, PlayRow]) -> dict[str, PlayRow]:
    combined: dict[str, PlayRow] = {}
    for harvest in harvests:
        for key, row in harvest.items():
            if key in combined:
                merge_row(combined[key], row)
            else:
                combined[key] = row
    return combined


def merge_saved(current: dict[str, PlayRow], saved: dict) -> dict[str, PlayRow]:
    for bucket in ("played", "not_played"):
        for item in saved.get(bucket) or []:
            artist = str(item.get("artist") or "")
            title = str(item.get("title") or "")
            if not normalize_title(title):
                continue
            plays = item.get("plays") or {}
            if not isinstance(plays, dict):
                plays = {}
            count = int(item.get("play_count") or 0)
            if not plays and count:
                plays = {"saved": count}
            row = PlayRow(
                artist=artist,
                title=title,
                duration_s=int(item.get("duration_s") or 0),
                plays={str(k): int(v) for k, v in plays.items() if int(v) > 0},
                last_played=str(item.get("last_played") or ""),
                first_seen=str(item.get("first_seen") or ""),
                rating=int(item.get("rating") or (1 if item.get("favorite") else 0)),
                genre=str(item.get("genre") or ""),
                bpm=parse_bpm(item.get("bpm")),
                energy=int(item.get("energy") or 0),
                key=str(item.get("key") or ""),
            )
            key = track_key(artist, title)
            if key in current:
                merge_row(current[key], row)
            else:
                current[key] = row
    return current


def split_rows(rows: dict[str, PlayRow]) -> tuple[list[PlayRow], list[PlayRow]]:
    played = [row for row in rows.values() if row.play_count > 0]
    not_played = [row for row in rows.values() if row.play_count <= 0]
    played.sort(key=lambda row: (-row.play_count, row.artist.lower(), row.title.lower()))
    not_played.sort(key=lambda row: (row.artist.lower(), row.title.lower()))
    return played, not_played


def recent_played(played: list[PlayRow], limit: int = PLAYED_LIMIT) -> list[PlayRow]:
    dated = [row for row in played if row.last_played]
    dated.sort(key=lambda row: row.last_played, reverse=True)
    rest = [row for row in played if not row.last_played]
    rest.sort(key=lambda row: -row.play_count)
    return (dated + rest)[:limit]


def play_fingerprint(played: list[PlayRow]) -> str:
    blob = json.dumps(
        [
            [track_key(row.artist, row.title), row.play_count, row.last_played]
            for row in sorted(played, key=lambda row: track_key(row.artist, row.title))
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_patterns(played: list[PlayRow], fingerprint: str) -> dict:
    genres: Counter[str] = Counter()
    bands: Counter[str] = Counter()
    energies: Counter[str] = Counter()
    keys: Counter[str] = Counter()
    vibes: Counter[str] = Counter()
    for row in played:
        if row.genre:
            genres[row.genre] += row.play_count or 1
        if row.bpm:
            bands[bpm_band(row.bpm)] += row.play_count or 1
        if row.energy:
            energies[str(row.energy)] += row.play_count or 1
        if row.key:
            keys[row.key.upper()] += row.play_count or 1
        if row.genre or row.bpm or row.energy:
            vibes[row.vibe] += row.play_count or 1
    top = recent_played(played, 20)
    payload = {
        "schema": 1,
        "tool": TOOL_ID,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fingerprint": fingerprint,
        "played": len(played),
        "note": (
            "Local LLM food. Genre/BPM/energy/vibe from Traktor + Rekordbox tags. "
            "Do not invent genres. Keep Ollama on 127.0.0.1. Own-repo when this "
            "corpus or a fine-tune outgrows crate — review quarterly."
        ),
        "genres": dict(genres.most_common(40)),
        "bpm_bands": dict(bands.most_common()),
        "energy": dict(energies.most_common()),
        "keys": dict(keys.most_common(24)),
        "vibes": dict(vibes.most_common(40)),
        "recent": [
            {
                "artist": row.artist,
                "title": row.title,
                "play_count": row.play_count,
                "genre": row.genre,
                "bpm": round(row.bpm, 2) if row.bpm else 0,
                "energy": row.energy,
                "vibe": row.vibe,
                "last_played": row.last_played,
            }
            for row in top
        ],
    }
    assert_public(payload)
    return payload


def _take(rows: list[PlayRow], used: set[str], limit: int) -> list[PlayRow]:
    picked: list[PlayRow] = []
    for row in rows:
        key = track_key(row.artist, row.title)
        if key in used:
            continue
        used.add(key)
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


def neglected_rows(played: list[PlayRow], not_played: list[PlayRow], used: set[str]) -> list[PlayRow]:
    counts = Counter(row.genre for row in played if row.genre)
    top = {genre for genre, _count in counts.most_common(8)}
    if not top:
        return []
    pool = [row for row in not_played if row.genre in top]
    pool.sort(key=lambda row: (row.first_seen or "9999", row.artist.lower(), row.title.lower()))
    return _take(pool, used, SUGGEST_EACH)


def random_rows(not_played: list[PlayRow], used: set[str], seed: str) -> list[PlayRow]:
    pool = [row for row in not_played if track_key(row.artist, row.title) not in used]
    rng = random.Random(seed)
    rng.shuffle(pool)
    return _take(pool, used, SUGGEST_EACH)


def favorites_match_rows(
    played: list[PlayRow], not_played: list[PlayRow], used: set[str]
) -> list[PlayRow]:
    anchors = [row for row in played if row.favorite] or played[:40]
    genres = {row.genre for row in anchors if row.genre}
    bpms = [row.bpm for row in anchors if row.bpm]
    energies = [row.energy for row in anchors if row.energy]
    mid_bpm = sorted(bpms)[len(bpms) // 2] if bpms else 0
    mid_energy = sorted(energies)[len(energies) // 2] if energies else 0

    def score(row: PlayRow) -> tuple:
        genre_hit = 1 if row.genre and row.genre in genres else 0
        bpm_hit = 1 if mid_bpm and row.bpm and abs(row.bpm - mid_bpm) <= 6 else 0
        energy_hit = 1 if mid_energy and row.energy and abs(row.energy - mid_energy) <= 1 else 0
        return (genre_hit + bpm_hit + energy_hit, genre_hit, -abs((row.bpm or 0) - mid_bpm))

    pool = [row for row in not_played if track_key(row.artist, row.title) not in used]
    pool.sort(key=score, reverse=True)
    return _take(pool, used, SUGGEST_EACH)


def is_acapella_track(row: PlayRow) -> bool:
    if (row.genre or "").strip().lower() in ACAPELLA_GENRES:
        return True
    return bool(ACAPELLA_TITLE.search(row.title or ""))


def acapella_rows(rows: dict[str, PlayRow]) -> list[PlayRow]:
    found = [row for row in rows.values() if is_acapella_track(row)]
    found.sort(key=lambda row: (row.artist.lower(), row.title.lower()))
    return found


def suggest_playlists(rows: dict[str, PlayRow], fingerprint: str) -> dict[str, list[PlayRow]]:
    played, not_played = split_rows(rows)
    acapella_keys = {
        track_key(row.artist, row.title) for row in rows.values() if is_acapella_track(row)
    }
    not_played = [
        row for row in not_played if track_key(row.artist, row.title) not in acapella_keys
    ]
    used: set[str] = set()
    return {
        PLAYED_NAME: recent_played(played, PLAYED_LIMIT),
        NEGLECTED: neglected_rows(played, not_played, used),
        FAVORITES_MATCH: favorites_match_rows(played, not_played, used),
        RANDOM: random_rows(not_played, used, fingerprint),
        ACAPELLA_NAME: acapella_rows(rows),
    }


def _hits_for(rows: list[PlayRow], dest: str) -> list:
    from ix_crate.crates import Hit

    hits = []
    for row in rows:
        if dest == "xml" and row.xml_id:
            hits.append(Hit(path=Path("."), dest_key=row.xml_id, via="id"))
        elif dest == "nml" and row.nml_key:
            hits.append(Hit(path=Path("."), dest_key=row.nml_key, via="id", extra=row.nml_type or "TRACK"))
    return hits


def crates_plan(suggestions: dict[str, list[PlayRow]], dest: str):
    from ix_crate.crates import PlaylistPlan, SyncPlan

    playlists = [
        PlaylistPlan(name=PLAYED_NAME, folder=(), matched=_hits_for(suggestions[PLAYED_NAME], dest))
    ]
    for name in (NEGLECTED, FAVORITES_MATCH, RANDOM):
        playlists.append(
            PlaylistPlan(
                name=name,
                folder=(NPBS_FOLDER,),
                matched=_hits_for(suggestions[name], dest),
            )
        )
    return SyncPlan(source="music", dest=dest, dest_folder="MUSIC", playlists=playlists)


def write_app_playlists(suggestions: dict[str, list[PlayRow]], *, nml: Path, xml: Path) -> list[str]:
    import plistlib

    from ix_crate.crates import (
        apply_nml,
        apply_xml,
        itunes_library_xml,
        nml_path_index,
        set_music_playlist,
        xml_path_index,
    )
    from ix_crate.music_dupes import music_running

    from ix_crate.acapella_crates import (
        clear_acapella_playlists,
        format_groups,
        group_acapellas,
        playlist_plans,
    )
    from ix_crate.library_genres import (
        build_catalog,
        format_genre_plans,
        library_genre_plans,
        load_library,
    )

    catalog = build_catalog(load_library())
    groups = group_acapellas(catalog=catalog)
    print(format_groups(groups), flush=True)
    written: list[str] = []
    if xml.is_file() and not rekordbox_is_running():
        clear_acapella_playlists(xml, kind="xml")
        genre_plans = library_genre_plans(catalog, dest="xml", index=xml_path_index(xml))
        print("xml\n" + format_genre_plans(genre_plans), flush=True)
        plan = crates_plan(suggestions, "xml")
        plan.playlists.extend(genre_plans)
        plan.playlists.extend(playlist_plans(groups, dest="xml", xml=xml))
        apply_xml(plan, xml)
        written.append("xml")
    elif rekordbox_is_running():
        written.append("xml-skipped-open")
    if nml.is_file() and not traktor_is_running():
        clear_acapella_playlists(nml, kind="nml")
        genre_plans = library_genre_plans(catalog, dest="nml", index=nml_path_index(nml))
        print("nml\n" + format_genre_plans(genre_plans), flush=True)
        plan = crates_plan(suggestions, "nml")
        plan.playlists.extend(genre_plans)
        plan.playlists.extend(playlist_plans(groups, dest="nml", nml=nml))
        apply_nml(plan, nml)
        written.append("nml")
    elif traktor_is_running():
        written.append("nml-skipped-open")
    if music_running():
        index: dict[str, str] = {}
        lib = itunes_library_xml()
        if lib.is_file():
            with lib.open("rb") as handle:
                payload = plistlib.load(handle)
            for row in (payload.get("Tracks") or {}).values():
                if not isinstance(row, dict):
                    continue
                pid = str(row.get("Persistent ID") or "").strip()
                artist = str(row.get("Artist") or "")
                title = str(row.get("Name") or "")
                if pid and normalize_title(title):
                    index.setdefault(track_key(artist, title), pid)
        for name in (PLAYED_NAME, NEGLECTED, RANDOM, FAVORITES_MATCH):
            label = name if name == PLAYED_NAME else f"NPBS {name}"
            pids = [
                index[track_key(row.artist, row.title)]
                for row in suggestions[name]
                if track_key(row.artist, row.title) in index
            ]
            set_music_playlist(label, pids)
        written.append("music")
    else:
        written.append("music-skipped")
    return written


def build_payload(
    rows: dict[str, PlayRow],
    *,
    traktor_scanned: int,
    rekordbox_scanned: int,
    fingerprint: str,
) -> dict:
    played, not_played = split_rows(rows)
    payload = {
        "schema": 1,
        "tool": TOOL_ID,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fingerprint": fingerprint,
        "note": "artist/title only — no disk paths. heard_s is play_count times track length.",
        "stats": {
            "played": len(played),
            "not_played": len(not_played),
            "favorites": sum(1 for row in played if row.favorite),
            "traktor_scanned": traktor_scanned,
            "rekordbox_scanned": rekordbox_scanned,
            "with_genre": sum(1 for row in rows.values() if row.genre),
            "with_energy": sum(1 for row in rows.values() if row.energy),
            "with_bpm": sum(1 for row in rows.values() if row.bpm),
        },
        "played": [public_row(row, played=True) for row in played],
        "not_played": [public_row(row, played=False) for row in not_played],
    }
    assert_public(payload)
    return payload


def load_saved(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(payload: dict, path: Path) -> Path:
    assert_public(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


write_favorites = write_json


def quarter_stamp(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"


def slim_for_git(payload: dict) -> dict:
    """Quarterly copy: played + stats. 22k sitting tracks stay local."""
    slim = {key: value for key, value in payload.items() if key != "not_played"}
    slim["not_played"] = []
    slim["note"] = (
        "Quarterly git snapshot. Played + stats only; full not_played stays in the "
        "local gitignored file. play-patterns.json is the LLM corpus."
    )
    return slim


def snapshot_quarterly(favorites: Path, patterns: Path, dest_dir: Path | None = None) -> list[Path]:
    folder = dest_dir or QUARTERLY_DIR
    folder.mkdir(parents=True, exist_ok=True)
    stamp = quarter_stamp()
    written: list[Path] = []
    if favorites.is_file():
        dest = folder / f"favorites-{stamp}.json"
        write_json(slim_for_git(json.loads(favorites.read_text(encoding="utf-8"))), dest)
        written.append(dest)
    if patterns.is_file():
        dest = folder / f"play-patterns-{stamp}.json"
        dest.write_text(patterns.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(dest)
    return written


def format_plan(payload: dict, suggestions: dict[str, list[PlayRow]] | None = None) -> str:
    stats = payload["stats"]
    lines = [
        f"favorites  played {stats['played']}  not played {stats['not_played']}  "
        f"favorites {stats['favorites']}",
        f"  scanned  traktor {stats['traktor_scanned']}  rekordbox {stats['rekordbox_scanned']}",
        f"  tags  genre {stats.get('with_genre', 0)}  bpm {stats.get('with_bpm', 0)}  "
        f"energy {stats.get('with_energy', 0)}",
    ]
    for row in payload["played"][:8]:
        lines.append(
            f"  {row['play_count']:4}  {row.get('last_played', '          ')}  "
            f"{row['artist']} — {row['title']}"
        )
    if stats["played"] > 8:
        lines.append(f"  … {stats['played'] - 8} more played")
    if suggestions:
        lines.append(
            f"  crates  {PLAYED_NAME} {len(suggestions[PLAYED_NAME])}  "
            f"{NPBS_FOLDER}/ {NEGLECTED} {len(suggestions[NEGLECTED])}  "
            f"{RANDOM} {len(suggestions[RANDOM])}  "
            f"{FAVORITES_MATCH} {len(suggestions[FAVORITES_MATCH])}  "
            f"held out of random {len(suggestions[ACAPELLA_NAME])}"
        )
    return "\n".join(lines)


def record_result(
    *,
    nml: Path | None = None,
    xml: Path | None = None,
    dest: Path | None = None,
    merge: bool = True,
) -> RecordResult:
    nml_path = nml or TRAKTOR_NML
    xml_path = xml or REKORDBOX_XML
    dest_path = dest or FAVORITES_JSON
    trakt = harvest_nml(nml_path)
    rekord = harvest_xml(xml_path)
    rows = combine(trakt, rekord)
    if merge:
        rows = merge_saved(rows, load_saved(dest_path))
    played, _not_played = split_rows(rows)
    fingerprint = play_fingerprint(played)
    payload = build_payload(
        rows,
        traktor_scanned=len(trakt),
        rekordbox_scanned=len(rekord),
        fingerprint=fingerprint,
    )
    patterns = build_patterns(played, fingerprint)
    return RecordResult(payload=payload, rows=rows, fingerprint=fingerprint, patterns=patterns)


def record(
    *,
    nml: Path | None = None,
    xml: Path | None = None,
    dest: Path | None = None,
    merge: bool = True,
) -> dict:
    return record_result(nml=nml, xml=xml, dest=dest, merge=merge).payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ix_crate favorites", description=__doc__)
    parser.add_argument("--nml", type=Path, default=TRAKTOR_NML)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument("--out", type=Path, default=FAVORITES_JSON)
    parser.add_argument("--patterns", type=Path, default=PATTERNS_JSON)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Do not merge with the existing JSON (full snapshot from NML + xml).",
    )
    parser.add_argument(
        "--playlists",
        action="store_true",
        help=(
            "Write Played, Not Played But Should, MUSIC/GENRES, and "
            "MUSIC/ACAPELLAS into NML / xml when plays changed."
        ),
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="Copy live JSON into configs/quarterly/ for the current quarter (git this, not nightly).",
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = record_result(nml=args.nml, xml=args.xml, dest=args.out, merge=not args.replace)
    suggestions = suggest_playlists(result.rows, result.fingerprint)
    previous = load_saved(args.patterns)
    unchanged = previous.get("fingerprint") == result.fingerprint
    print(format_plan(result.payload, suggestions), flush=True)
    if unchanged:
        print("no new plays since last patterns file. playlist crates stay.", flush=True)
    if not args.execute:
        print(
            f"dry-run. pass --execute to write {args.out} and {args.patterns}. "
            "artist/title only; no disk paths. --playlists writes crates if plays changed.",
            flush=True,
        )
        return 0
    dest = write_json(result.payload, args.out)
    patterns = write_json(result.patterns, args.patterns)
    print(f"wrote {dest}", flush=True)
    print(f"wrote {patterns}", flush=True)
    if args.snapshot:
        for path in snapshot_quarterly(args.out, args.patterns):
            print(f"quarterly {path}", flush=True)
    if args.playlists and unchanged and previous.get("crates"):
        return 0
    if args.playlists:
        written = write_app_playlists(suggestions, nml=args.nml, xml=args.xml)
        result.patterns["crates"] = True
        write_json(result.patterns, args.patterns)
        print(f"playlists {', '.join(written)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
