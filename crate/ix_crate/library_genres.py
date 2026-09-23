"""Apple Music genres for ``MUSIC/GENRES`` and stem-vocal matching.

``favorites --playlists`` writes one Traktor and Rekordbox playlist per
genre in the shared iTunes library XML. Stem vocals
(``acapella_crates``) take the genre of the Apple Music row with the
same song. Match order:

1. Artist + title.
2. Title with mix markup removed (``Example (Original Mix)`` and
   ``Example``). When several library rows share that title, the folder
   artist picks the row. When every remaining row shares one genre, that
   genre is used.
3. No Apple Music row: MusicBrainz identifies the recording and the
   match is tried again. Shazam listens to the vocal file and the match
   is tried again. A Shazam or MusicBrainz genre is used only when the
   song is still absent from Apple Music. Nothing is filed as Untagged.

Apple Music media is never written. Quit Rekordbox before xml. Quit
Traktor before NML.
"""

from __future__ import annotations

import plistlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ix_crate.crates import Hit, PlaylistPlan, TrackRef, itunes_library_xml, parse_rb_location
from ix_crate.identify import normalize_title
from ix_crate.lookup import artists_match
from ix_crate.music_genre import clean_genre

GENRES_FOLDER = "GENRES"
DROP_WORDS = {
    "mix",
    "remix",
    "extended",
    "radio",
    "club",
    "original",
    "edit",
    "version",
    "dub",
    "vocal",
    "vocals",
    "instrumental",
    "rework",
    "bootleg",
    "vip",
}
FEAT_WORDS = {"feat", "featuring", "ft"}
SKIP_SUFFIX = {".m4p"}


@dataclass
class LibraryTrack:
    artist: str
    title: str
    genre: str
    path: Path | None = None


@dataclass
class Catalog:
    tracks: list[LibraryTrack] = field(default_factory=list)
    by_pair: dict[str, str] = field(default_factory=dict)
    by_base: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    spellings: dict[str, str] = field(default_factory=dict)


def _track_key(artist: str, title: str) -> str:
    return f"{normalize_title(artist)}\t{normalize_title(title)}"


def _prefer(current: str | None, new: str) -> str:
    if current is None:
        return new
    if current == "Acapella" and new != "Acapella":
        return new
    return current


def base_title(title: str) -> str:
    """Library and stem titles compared after mix and feat tails are gone."""
    words = normalize_title(title).split()
    for index, word in enumerate(words):
        if word in FEAT_WORDS:
            words = words[:index]
            break
    while len(words) > 1 and words[-1] in DROP_WORDS:
        words.pop()
    return " ".join(words).strip()


def load_library(path: Path | None = None) -> list[LibraryTrack]:
    """Every Apple Music row that has a genre. ``path`` is set when the file is here."""
    library = path or itunes_library_xml()
    if not library.is_file():
        return []
    with library.open("rb") as handle:
        payload = plistlib.load(handle)
    tracks = payload.get("Tracks") or {}
    rows = tracks.values() if isinstance(tracks, dict) else tracks
    found: list[LibraryTrack] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        genre = clean_genre(str(row.get("Genre") or ""))
        title = str(row.get("Name") or "")
        artist = str(row.get("Artist") or "") or str(row.get("Album Artist") or "")
        if not genre or not normalize_title(title):
            continue
        location = parse_rb_location(str(row.get("Location") or ""))
        file_path = None
        if location is not None and location.suffix.lower() not in SKIP_SUFFIX:
            try:
                if location.is_file():
                    file_path = location.resolve()
            except OSError:
                file_path = None
        found.append(LibraryTrack(artist=artist, title=title, genre=genre, path=file_path))
    return found


def build_catalog(tracks: list[LibraryTrack]) -> Catalog:
    catalog = Catalog(tracks=tracks)
    by_base: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for track in tracks:
        catalog.spellings.setdefault(track.genre.casefold(), track.genre)
        if normalize_title(track.artist) and normalize_title(track.title):
            key = _track_key(track.artist, track.title)
            catalog.by_pair[key] = _prefer(catalog.by_pair.get(key), track.genre)
        base = base_title(track.title)
        if base:
            by_base[base].append((track.artist, track.genre))
    catalog.by_base = dict(by_base)
    return catalog


def _pick(artist: str, hits: list[tuple[str, str]]) -> str:
    if not hits:
        return ""
    if artist:
        own = [item for item in hits if artists_match(artist, item[0])]
        if own:
            hits = own
    genres = [genre for _artist, genre in hits if genre and genre != "Acapella"]
    if not genres:
        genres = [genre for _artist, genre in hits if genre]
    unique = set(genres)
    if len(unique) == 1:
        return next(iter(unique))
    return ""


def match_library_genre(artist: str, title: str, catalog: Catalog) -> str:
    """Genre of the Apple Music equivalent, or empty when the song is not there."""
    found = catalog.by_pair.get(_track_key(artist, title))
    if found:
        return found
    hits = list(catalog.by_base.get(base_title(title)) or [])
    exact = normalize_title(title)
    base = base_title(title)
    if exact and exact != base:
        hits.extend(catalog.by_base.get(exact) or [])
    return _pick(artist, hits)


def library_spelling(genre: str, catalog: Catalog) -> str:
    """Use the Apple Music spelling when this genre is already in the library."""
    cleaned = clean_genre(genre)
    if not cleaned:
        return ""
    hit = catalog.spellings.get(cleaned.casefold())
    if hit:
        return hit
    titled = " ".join(part[:1].upper() + part[1:] if part else part for part in cleaned.split(" "))
    return catalog.spellings.get(titled.casefold()) or titled


def library_genre_plans(catalog: Catalog, *, dest: str, index) -> list[PlaylistPlan]:
    """``MUSIC/GENRES/<Genre>`` for library files that are on disk."""
    grouped: dict[str, list[LibraryTrack]] = defaultdict(list)
    seen: dict[str, set[Path]] = defaultdict(set)
    for track in catalog.tracks:
        if track.path is None or not track.genre:
            continue
        if track.path in seen[track.genre]:
            continue
        seen[track.genre].add(track.path)
        grouped[track.genre].append(track)
    plans: list[PlaylistPlan] = []
    for genre in sorted(grouped, key=str.casefold):
        matched: list[Hit] = []
        missing: list[TrackRef] = []
        for track in grouped[genre]:
            path = track.path
            if path is None:
                continue
            found = index.lookup(path) if index is not None else None
            if found and dest == "nml":
                key, via = found
                extra = index.extra.get(key, "TRACK")
                matched.append(Hit(path=path, dest_key=key, via=via, extra=extra))
            elif found and dest == "xml":
                key, via = found
                matched.append(Hit(path=path, dest_key=key, via=via))
            else:
                missing.append(TrackRef(path=path, artist=track.artist, title=track.title))
        plans.append(
            PlaylistPlan(name=genre, folder=(GENRES_FOLDER,), matched=matched, missing=missing)
        )
    return plans


def format_genre_plans(plans: list[PlaylistPlan]) -> str:
    files = sum(len(item.matched) + len(item.missing) for item in plans)
    lines = [f"GENRES  {files} files  {len(plans)} playlists"]
    for item in plans:
        lines.append(f"  {item.name}  {len(item.matched) + len(item.missing)}")
    return "\n".join(lines)


def musicbrainz_identity(artist: str, title: str, cache: dict) -> tuple[str, str, str]:
    """``(genre, artist, title)`` from MusicBrainz. Genre may be empty. Cached."""
    import urllib.parse

    from ix_crate.identify import clean_text, is_placeholder_artist
    from ix_crate.lookup import MB_GAP, MB_URL, _http_json

    artist = clean_text(artist)
    title = clean_text(title)
    if not title:
        return "", artist, title
    key = f"mb-genre::v1::{artist.lower()}::{title.lower()}"
    if key in cache:
        cached = cache[key] or {}
        return (
            str(cached.get("genre") or ""),
            str(cached.get("artist") or artist),
            str(cached.get("title") or title),
        )
    parts = [f'recording:"{title}"']
    if artist and not is_placeholder_artist(artist):
        parts.append(f'artist:"{artist}"')
    query = " AND ".join(parts)
    url = MB_URL + "?" + urllib.parse.urlencode(
        {"query": query, "fmt": "json", "limit": "1"}
    )
    payload = _http_json(url, cache, f"mb-genre-search::{key}", gap=MB_GAP)
    genre = ""
    found_artist = artist
    found_title = title
    if isinstance(payload, dict):
        recordings = payload.get("recordings") or []
        if recordings:
            rec = recordings[0]
            credit = rec.get("artist-credit") or [{}]
            if credit:
                found_artist = clean_text(
                    str(credit[0].get("name") or credit[0].get("artist", {}).get("name") or artist)
                )
            found_title = clean_text(str(rec.get("title") or title))
            mbid = str(rec.get("id") or "")
            if mbid:
                genre_url = (
                    f"https://musicbrainz.org/ws/2/recording/{mbid}?inc=genres&fmt=json"
                )
                detail = _http_json(genre_url, cache, f"mb-genre-rec::{mbid}", gap=MB_GAP)
                if isinstance(detail, dict):
                    genres = detail.get("genres") or []
                    if genres:
                        genres = sorted(genres, key=lambda item: int(item.get("count") or 0), reverse=True)
                        genre = clean_text(str(genres[0].get("name") or ""))
    cache[key] = {"genre": genre, "artist": found_artist, "title": found_title}
    from ix_crate.lookup import _save_cache

    _save_cache(cache)
    return genre, found_artist, found_title


def resolve_remote_genre(
    artist: str,
    title: str,
    path: Path | None,
    catalog: Catalog,
    cache: dict,
) -> str:
    """MusicBrainz, then Shazam. Apple Music spelling wins when the song is in the library."""
    mb_genre, mb_artist, mb_title = musicbrainz_identity(artist, title, cache)
    found = match_library_genre(mb_artist, mb_title, catalog)
    if found:
        return found
    fresh = False
    if path is not None and path.is_file():
        try:
            fresh = (path.stat().st_mtime + 120) > time.time()
        except OSError:
            fresh = True
    if path is not None and path.is_file() and not fresh:
        from ix_crate.shazam import shazam_identify

        hit = shazam_identify(path, cache) or {}
        sh_artist = str(hit.get("artist") or "")
        sh_title = str(hit.get("title") or "")
        if sh_artist or sh_title:
            found = match_library_genre(sh_artist or artist, sh_title or title, catalog)
            if found:
                return found
        sh_genre = library_spelling(str(hit.get("genre") or ""), catalog)
        if sh_genre:
            return sh_genre
    return library_spelling(mb_genre, catalog)


def follow_unmatched() -> int:
    """MusicBrainz then Shazam for vocals the Apple Music library did not name.

    Rewrites only ``MUSIC/ACAPELLAS`` when Traktor and Rekordbox are closed.
    """
    from ix_crate.acapella_crates import (
        ACAPELLAS_FOLDER,
        clear_music_folders,
        group_acapellas,
        playlist_plans,
    )
    from ix_crate.crates import SyncPlan, apply_nml, apply_xml
    from ix_crate.lookup import _load_cache
    from ix_crate.stems_playlists import REKORDBOX_XML, TRAKTOR_NML, rekordbox_is_running
    from ix_crate.traktor_nml import traktor_is_running

    catalog = build_catalog(load_library())
    groups = group_acapellas(catalog=catalog)
    pending = list(groups.get("") or [])
    print(f"follow  {len(pending)} unmatched vocals", flush=True)
    if not pending:
        return 0
    cache = _load_cache()
    resolved: dict[str, list] = {
        genre: list(rows) for genre, rows in groups.items() if genre
    }
    found = 0
    for index, track in enumerate(pending, start=1):
        genre = resolve_remote_genre(track.artist, track.title, track.path, catalog, cache)
        if not genre:
            print(f"  {index}/{len(pending)}  open  {track.artist} — {track.title}", flush=True)
            continue
        track.genre = genre
        resolved.setdefault(genre, []).append(track)
        found += 1
        print(f"  {index}/{len(pending)}  {genre}  {track.artist} — {track.title}", flush=True)
    print(f"follow resolved {found}  still open {len(pending) - found}", flush=True)
    if rekordbox_is_running():
        print("xml skipped, Rekordbox is open", flush=True)
    elif REKORDBOX_XML.is_file():
        clear_music_folders(REKORDBOX_XML, kind="xml", folders=(ACAPELLAS_FOLDER,), retired=False)
        plan = SyncPlan(
            source="music",
            dest="xml",
            dest_folder="MUSIC",
            playlists=playlist_plans(resolved, dest="xml", xml=REKORDBOX_XML),
        )
        apply_xml(plan, REKORDBOX_XML)
        print("wrote xml ACAPELLAS", flush=True)
    if traktor_is_running():
        print("nml skipped, Traktor is open", flush=True)
    elif TRAKTOR_NML.is_file():
        clear_music_folders(TRAKTOR_NML, kind="nml", folders=(ACAPELLAS_FOLDER,), retired=False)
        plan = SyncPlan(
            source="music",
            dest="nml",
            dest_folder="MUSIC",
            playlists=playlist_plans(resolved, dest="nml", nml=TRAKTOR_NML),
        )
        apply_nml(plan, TRAKTOR_NML)
        print("wrote nml ACAPELLAS", flush=True)
    return found
