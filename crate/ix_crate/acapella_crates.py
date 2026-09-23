"""STEMIT vocal files as ``Acapellas/<Apple Music genre>`` crates.

Called from ``favorites --playlists``. The play harvest still skips role
files. This module is the matcher for the vocal files on disk.

Match:

1. Keep ``stems_audio`` files ``classify()`` puts in Acapellas. That is a
   role file whose leftover name contains vocal, vox, acapella, acappella,
   or a cappella (``Song_vocals.m4a``, ``vocals.m4a``). A mix whose title
   says Acappella stays a mix.
2. Artist and title come from the filename with the role suffix removed,
   then the artist/album folder (``filing_from_path``).
3. Genre comes from the shared iTunes library XML
   (``itunes_library_xml()``), then ``clean_genre`` (``EDM, House`` →
   ``House``).
4. Look up artist + title. When several Music rows share that pair, a
   real genre wins over Acapella; the first real genre stays. If that
   misses, use the title alone when every Music row with that title
   shares one genre (an Acapella spelling plus one real genre counts as
   that real genre). Otherwise the playlist is Untagged.
5. Write ``MUSIC/ACAPELLAS/<Genre>`` in Traktor NML and rekordbox.xml.
   The playlist entry is the vocal file. A file already in the collection
   keeps that row. A file that is not gets a location row. Analyze stays
   in-app. Apple Music media is never written. No Untagged playlist:
   a vocal with no Apple Music row is resolved later by MusicBrainz, then
   Shazam (``library_genres``).

Quit Rekordbox before the xml write. Quit Traktor before the NML write.
"""

from __future__ import annotations

import plistlib
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ix_crate.crates import Hit, PlaylistPlan, TrackRef, itunes_library_xml
from ix_crate.identify import normalize_title
from ix_crate.music_genre import clean_genre
from ix_crate.paths import STEMS_AUDIO
from ix_crate.stems_playlists import (
    DiskFile,
    filing_from_path,
    prefer_crate_files,
    rekordbox_index,
    traktor_index,
    walk_stems,
)

ACAPELLAS_FOLDER = "ACAPELLAS"
OLD_ACAPELLAS_FOLDER = "Acapellas"
UNTAGGED = "Untagged"
# Flat playlist written before the genre folder existed.
RETIRED_PLAYLIST = "Acapella"
MUSIC_FOLDER = "MUSIC"


@dataclass
class AcapellaTrack:
    path: Path
    artist: str
    title: str
    genre: str


def _prefer(current: str | None, new: str) -> str:
    if current is None:
        return new
    if current == "Acapella" and new != "Acapella":
        return new
    return current


def _track_key(artist: str, title: str) -> str:
    return f"{normalize_title(artist)}\t{normalize_title(title)}"


def index_music_genres(rows: Iterable[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """``(artist-title → genre, title → genre)``.

    Title map only keeps a title whose Music rows agree on one genre.
    """
    pair: dict[str, str] = {}
    titles: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not isinstance(row, dict):
            continue
        genre = clean_genre(str(row.get("Genre") or ""))
        title = str(row.get("Name") or "")
        artist = str(row.get("Artist") or "") or str(row.get("Album Artist") or "")
        if not genre or not normalize_title(title):
            continue
        if normalize_title(artist):
            key = _track_key(artist, title)
            pair[key] = _prefer(pair.get(key), genre)
        titles[normalize_title(title)].add(genre)
    by_title: dict[str, str] = {}
    for title, genres in titles.items():
        real = {item for item in genres if item != "Acapella"}
        if len(real) == 1:
            by_title[title] = next(iter(real))
        elif len(genres) == 1:
            by_title[title] = next(iter(genres))
    return pair, by_title


def load_music_genre_index(path: Path | None = None) -> tuple[dict[str, str], dict[str, str]]:
    library = path or itunes_library_xml()
    if not library.is_file():
        return {}, {}
    with library.open("rb") as handle:
        payload = plistlib.load(handle)
    tracks = payload.get("Tracks") or {}
    values = tracks.values() if isinstance(tracks, dict) else tracks
    return index_music_genres(values)


def genre_of(
    artist: str,
    title: str,
    by_pair: dict[str, str],
    by_title: dict[str, str],
) -> str:
    found = by_pair.get(_track_key(artist, title))
    if found:
        return found
    found = by_title.get(normalize_title(title))
    if found:
        return found
    return UNTAGGED


def group_acapellas(
    root: Path | None = None,
    library: Path | None = None,
    files: list[DiskFile] | None = None,
    genre_index: tuple[dict[str, str], dict[str, str]] | None = None,
    catalog=None,
) -> dict[str, list[AcapellaTrack]]:
    """Genre name → vocal files, using the Apple Music genre of the song."""
    base = (root or STEMS_AUDIO).expanduser()
    if files is None:
        selected = [item for item in walk_stems(base) if item.crate == "Acapellas"]
        selected = prefer_crate_files(selected, base)
    else:
        selected = [item for item in files if item.crate == "Acapellas"]
    if genre_index is None and catalog is None:
        from ix_crate.library_genres import build_catalog, load_library

        catalog = build_catalog(load_library(library))
    grouped: dict[str, list[AcapellaTrack]] = defaultdict(list)
    for item in selected:
        artist, _album, title = filing_from_path(item.path, base)
        if genre_index is not None:
            genre = genre_of(artist, title, genre_index[0], genre_index[1])
        else:
            from ix_crate.library_genres import match_library_genre

            genre = match_library_genre(artist, title, catalog)
        grouped[genre].append(
            AcapellaTrack(path=item.path, artist=artist, title=title or item.path.stem, genre=genre)
        )
    for rows in grouped.values():
        rows.sort(key=lambda row: (row.artist.lower(), row.title.lower(), row.path.name.lower()))
    return dict(grouped)


def playlist_plans(
    groups: dict[str, list[AcapellaTrack]],
    *,
    dest: str,
    nml: Path | None = None,
    xml: Path | None = None,
    nml_index: dict[Path, tuple[str, str]] | None = None,
    xml_index: dict[Path, str] | None = None,
) -> list[PlaylistPlan]:
    """One playlist per genre under ``Acapellas``."""
    if dest == "nml" and nml_index is None and nml is not None and nml.is_file():
        nml_index = traktor_index(nml)
    if dest == "xml" and xml_index is None and xml is not None and xml.is_file():
        xml_index = rekordbox_index(xml)
    nml_index = nml_index or {}
    xml_index = xml_index or {}
    plans: list[PlaylistPlan] = []
    for genre in sorted(groups, key=str.casefold):
        if not genre or genre == UNTAGGED:
            continue
        matched: list[Hit] = []
        missing: list[TrackRef] = []
        for track in groups[genre]:
            path = track.path.resolve()
            if dest == "nml" and path in nml_index:
                pk_type, key = nml_index[path]
                matched.append(Hit(path=path, dest_key=key, via="path", extra=pk_type))
            elif dest == "xml" and path in xml_index:
                matched.append(Hit(path=path, dest_key=xml_index[path], via="path"))
            else:
                missing.append(
                    TrackRef(path=path, artist=track.artist, title=track.title)
                )
        plans.append(
            PlaylistPlan(
                name=genre,
                folder=(ACAPELLAS_FOLDER,),
                matched=matched,
                missing=missing,
            )
        )
    return plans


def format_groups(groups: dict[str, list[AcapellaTrack]]) -> str:
    named = {genre: rows for genre, rows in groups.items() if genre and genre != UNTAGGED}
    unmatched = sum(len(rows) for genre, rows in groups.items() if genre not in named)
    total = sum(len(rows) for rows in named.values())
    lines = [f"ACAPELLAS  {total} vocals  {len(named)} genres  unmatched {unmatched}"]
    for genre in sorted(named, key=str.casefold):
        lines.append(f"  {genre}  {len(named[genre])}")
    return "\n".join(lines)


def _nml_child_folder(parent: ET.Element, name: str) -> ET.Element | None:
    subnodes = parent.find("SUBNODES")
    if subnodes is None:
        return None
    for node in subnodes.findall("NODE"):
        if node.get("TYPE") == "FOLDER" and node.get("NAME") == name:
            return node
    return None


def _drop_nml_playlists(folder: ET.Element, names: set[str] | None) -> None:
    subnodes = folder.find("SUBNODES")
    if subnodes is None:
        return
    for node in list(subnodes.findall("NODE")):
        if node.get("TYPE") != "PLAYLIST":
            continue
        if names is not None and node.get("NAME") not in names:
            continue
        subnodes.remove(node)
    subnodes.set("COUNT", str(len(list(subnodes))))


def _xml_child_folder(parent: ET.Element, name: str) -> ET.Element | None:
    for node in parent.findall("NODE"):
        if node.get("Name") == name and node.get("Type") == "0":
            return node
    return None


def _drop_xml_playlists(folder: ET.Element, names: set[str] | None) -> None:
    for node in list(folder.findall("NODE")):
        if node.get("Type") != "1":
            continue
        if names is not None and node.get("Name") not in names:
            continue
        folder.remove(node)
    folder.set("Count", str(len(folder.findall("NODE"))))


def clear_music_folders(
    path: Path,
    *,
    kind: str,
    folders: tuple[str, ...] = (ACAPELLAS_FOLDER, OLD_ACAPELLAS_FOLDER),
    retired: bool = True,
) -> None:
    """Drop playlist nodes inside ``MUSIC/<folder>`` so the next apply can refill them."""
    tree = ET.parse(path)
    if kind == "nml":
        playlists = tree.getroot().find("PLAYLISTS")
        root = playlists.find("NODE") if playlists is not None else None
        if root is None:
            return
        music = _nml_child_folder(root, MUSIC_FOLDER)
        if music is None:
            return
        if retired:
            _drop_nml_playlists(music, {RETIRED_PLAYLIST})
        for name in folders:
            folder = _nml_child_folder(music, name)
            if folder is not None:
                _drop_nml_playlists(folder, None)
    elif kind == "xml":
        playlists = tree.getroot().find("PLAYLISTS")
        root = playlists.find("NODE") if playlists is not None else None
        if root is None:
            return
        music = _xml_child_folder(root, MUSIC_FOLDER)
        if music is None:
            return
        if retired:
            _drop_xml_playlists(music, {RETIRED_PLAYLIST})
        for name in folders:
            folder = _xml_child_folder(music, name)
            if folder is not None:
                _drop_xml_playlists(folder, None)
    else:
        raise ValueError(f"unknown library kind {kind}")
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def clear_acapella_playlists(path: Path, *, kind: str) -> None:
    """Drop the retired flat list plus ``ACAPELLAS`` and the older ``Acapellas`` folder."""
    from ix_crate.library_genres import GENRES_FOLDER

    clear_music_folders(
        path,
        kind=kind,
        folders=(ACAPELLAS_FOLDER, OLD_ACAPELLAS_FOLDER, GENRES_FOLDER),
    )
