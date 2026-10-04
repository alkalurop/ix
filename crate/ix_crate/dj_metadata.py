"""Copy DJ analysis fields between Traktor NML and rekordbox.xml on ingest.

Used by sample/remix crate tools so new rows carry artist, title, album,
BPM, key, and genre from whichever app already analyzed the file.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ix_crate.crates import TrackRef, parse_rb_location
from ix_crate.stems_playlists import _loc_to_path, _traktor_dir_file


@dataclass
class NmlMeta:
    artist: str = ""
    title: str = ""
    album: str = ""
    genre: str = ""
    bpm: str = ""
    key: str = ""
    playtime: str = ""


@dataclass
class XmlMeta:
    artist: str = ""
    title: str = ""
    album: str = ""
    genre: str = ""
    bpm: str = ""
    key: str = ""
    total_time: str = ""
    comments: str = ""


def parse_nml_entry(entry: ET.Element) -> NmlMeta:
    album_el = entry.find("ALBUM")
    info = entry.find("INFO")
    tempo = entry.find("TEMPO")
    musical = entry.find("MUSICAL_KEY")
    key = ""
    if info is not None and info.get("KEY"):
        key = info.get("KEY") or ""
    return NmlMeta(
        artist=(entry.get("ARTIST") or "").strip(),
        title=(entry.get("TITLE") or "").strip(),
        album=(album_el.get("TITLE") if album_el is not None else "") or "",
        genre=(info.get("GENRE") if info is not None else "") or "",
        bpm=(tempo.get("BPM") if tempo is not None else "") or "",
        key=key,
        playtime=(info.get("PLAYTIME") if info is not None else "") or "",
    )


def nml_meta_by_path(nml: Path) -> dict[Path, NmlMeta]:
    if not nml.is_file():
        return {}
    root = ET.parse(nml).getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        return {}
    out: dict[Path, NmlMeta] = {}
    for entry in collection.findall("ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        try:
            path = _loc_to_path(location.get("DIR") or "", location.get("FILE") or "")
        except OSError:
            continue
        if not path.is_file():
            continue
        out[path.resolve()] = parse_nml_entry(entry)
    return out


def parse_xml_track(track: ET.Element) -> XmlMeta:
    return XmlMeta(
        artist=(track.get("Artist") or "").strip(),
        title=(track.get("Name") or "").strip(),
        album=(track.get("Album") or "").strip(),
        genre=(track.get("Genre") or "").strip(),
        bpm=(track.get("AverageBpm") or "").strip(),
        key=(track.get("Tonality") or "").strip(),
        total_time=(track.get("TotalTime") or "").strip(),
        comments=(track.get("Comments") or "").strip(),
    )


def xml_meta_by_path(xml: Path) -> dict[Path, XmlMeta]:
    if not xml.is_file():
        return {}
    root = ET.parse(xml).getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        return {}
    out: dict[Path, XmlMeta] = {}
    for track in collection.findall("TRACK"):
        loc = parse_rb_location(track.get("Location") or "")
        if loc is None or not loc.is_file():
            continue
        out[loc.resolve()] = parse_xml_track(track)
    return out


def enrich_ref_from_nml(ref: TrackRef, meta: NmlMeta | None) -> TrackRef:
    if meta is None:
        return ref
    return TrackRef(
        path=ref.path,
        label=ref.label or meta.title,
        artist=meta.artist or ref.artist,
        title=meta.title or ref.title,
        album=meta.album or ref.album,
        genre=meta.genre or ref.genre,
        bpm=meta.bpm or ref.bpm,
        key=meta.key or ref.key,
        total_time=meta.playtime or ref.total_time,
        comments=ref.comments,
    )


def enrich_ref_from_xml(ref: TrackRef, meta: XmlMeta | None) -> TrackRef:
    if meta is None:
        return ref
    return TrackRef(
        path=ref.path,
        label=ref.label or meta.title,
        artist=meta.artist or ref.artist,
        title=meta.title or ref.title,
        album=meta.album or ref.album,
        genre=meta.genre or ref.genre,
        bpm=meta.bpm or ref.bpm,
        key=meta.key or ref.key,
        total_time=meta.total_time or ref.total_time,
        comments=meta.comments or ref.comments,
    )


def match_xml_source_for_capture(
    capture_title: str,
    xml: Path,
    *,
    limit: int = 80000,
) -> XmlMeta | None:
    """Best-effort source row for a ``…_capture`` title (same library, not the wav)."""
    needle = capture_title.strip().lower()
    if not needle or not xml.is_file():
        return None
    best: XmlMeta | None = None
    best_len = 0
    for _event, el in ET.iterparse(xml, events=("end",)):
        if el.tag != "TRACK":
            el.clear()
            continue
        name = (el.get("Name") or "").lower()
        loc = (el.get("Location") or "").lower()
        if "sampler/saved" in loc or "sampler/capture" in loc or "_capture" in name:
            el.clear()
            continue
        if needle in name or name in needle:
            cand = parse_xml_track(el)
            score = len(name)
            if score > best_len:
                best = cand
                best_len = score
        el.clear()
    return best


def append_nml_analysis(entry: ET.Element, ref: TrackRef) -> None:
    if ref.album:
        album = entry.find("ALBUM")
        if album is None:
            ET.SubElement(entry, "ALBUM", TITLE=ref.album)
        else:
            album.set("TITLE", ref.album)
    info_attrs: dict[str, str] = {}
    if ref.genre:
        info_attrs["GENRE"] = ref.genre
    if ref.key:
        info_attrs["KEY"] = ref.key
    if ref.total_time and ref.total_time.isdigit():
        info_attrs["PLAYTIME"] = ref.total_time
    if info_attrs:
        info = entry.find("INFO")
        if info is None:
            ET.SubElement(entry, "INFO", **info_attrs)
        else:
            for key, value in info_attrs.items():
                info.set(key, value)
    if ref.bpm:
        tempo = entry.find("TEMPO")
        if tempo is None:
            ET.SubElement(entry, "TEMPO", BPM=ref.bpm, BPM_QUALITY="100.000000")
        else:
            tempo.set("BPM", ref.bpm)


def xml_track_attrs(ref: TrackRef, *, tid: str, kind: str, size: int, location: str) -> dict[str, str]:
    attrs: dict[str, str] = {
        "TrackID": tid,
        "Name": ref.title or ref.path.stem,
        "Artist": ref.artist or "",
        "Kind": kind,
        "Size": str(size),
        "Location": location,
    }
    if ref.album:
        attrs["Album"] = ref.album
    if ref.genre:
        attrs["Genre"] = ref.genre
    if ref.bpm:
        attrs["AverageBpm"] = ref.bpm
    if ref.key:
        attrs["Tonality"] = ref.key
    if ref.total_time:
        attrs["TotalTime"] = ref.total_time
    if ref.comments:
        attrs["Comments"] = ref.comments
    return attrs


def copy_nml_entry_shell(ref: TrackRef) -> ET.Element:
    directory, file_attr = _traktor_dir_file(ref.path.resolve())
    entry = ET.Element(
        "ENTRY",
        TITLE=ref.title or ref.path.stem,
        ARTIST=ref.artist or "",
    )
    ET.SubElement(
        entry,
        "LOCATION",
        DIR=directory,
        FILE=file_attr,
        VOLUME="Macintosh HD",
        VOLUMEID="Macintosh HD",
    )
    append_nml_analysis(entry, ref)
    return entry
