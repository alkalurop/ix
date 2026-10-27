"""Fill role-file titles (vocals / instrumental) from the mix sibling and folder.

Traktor shows NML TITLE, not the filename. Factory pairs named ``vocals.m4a``
or ``Everyday_vocals.m4a`` land as Title = vocals. This pass writes a real
title onto owned ``.mp3`` / ``.m4a`` (never ``.wav``, never ``.stem.m4a``)
and patches Traktor NML TITLE/ARTIST. Rekordbox folders follow
``stemit --genres``. This pass does not rewrite rekordbox.xml.

Discogs is not used. Sibling mix and
folder name are the catalog. MusicBrainz is not farmed: the title is
already in the filename or the IndustryStems folder.
"""

from __future__ import annotations

import json
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from ix_crate.xml_io import write_tree
from ix_crate.families import (
    ROLE_NAMES,
    STEM_SUFFIXES,
    discover_families,
    is_audio,
    is_role_file,
    strip_role_markup,
)
from ix_crate.identify import (
    is_beatport_title,
    is_placeholder_album_folder,
    is_placeholder_artist,
    is_placeholder_title,
    parse_filename,
    pretty_beatport_title,
    strip_track_number,
)
from ix_crate.music_repair import SKIP_SUFFIX, write_file_tags
from ix_crate.paths import REPORTS, STEMS_AUDIO

TAGGABLE = {".mp3", ".m4a"}


@dataclass
class RoleFix:
    path: str
    artist: str
    album: str
    title: str
    source: str
    write_tags: bool


def traktor_is_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-if", "Traktor"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _folder_artist_album(path: Path, root: Path) -> tuple[str, str]:
    try:
        rel = path.resolve().parent.relative_to(root.expanduser().resolve())
    except ValueError:
        return "", ""
    parts = list(rel.parts)
    artist = parts[0] if parts else ""
    album = parts[1] if len(parts) > 1 else ""
    if is_placeholder_artist(artist):
        artist = ""
    if is_placeholder_album_folder(album):
        album = ""
    return artist, album


def _title_from_stem(stem: str) -> tuple[str, str, str]:
    stripped = strip_role_markup(stem)
    if not stripped or stripped.lower() in ROLE_NAMES:
        return "", "", ""
    artist, album, title = parse_filename(stripped)
    if is_placeholder_title(title):
        title = ""
    if is_placeholder_artist(artist):
        artist = ""
    return artist, album, title or stripped


def _title_from_mix(directory: Path, role_path: Path) -> tuple[str, str, str]:
    if not directory.is_dir():
        return "", "", ""
    role_res = role_path.resolve()
    for family in discover_families(directory):
        if role_res not in {item.resolve() for item in family.files}:
            continue
        mix = family.mix_file()
        if mix is None or is_role_file(mix):
            continue
        return _title_from_stem(mix.stem)
    mixes = [
        item
        for item in directory.iterdir()
        if is_audio(item)
        and not is_role_file(item)
        and not any(item.name.lower().endswith(suffix) for suffix in STEM_SUFFIXES)
    ]
    if len(mixes) == 1:
        return _title_from_stem(mixes[0].stem)
    return "", "", ""


def _title_from_album_folder(album: str) -> str:
    if not album:
        return ""
    text = strip_track_number(album.replace("_", " "))
    return text if text and not is_placeholder_title(text) else ""


def _tag_fields(path: Path) -> tuple[str, str]:
    if path.suffix.lower() not in TAGGABLE:
        return "", ""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=True)
    except Exception:
        return "", ""
    if audio is None or audio.tags is None:
        return "", ""

    def first(key: str) -> str:
        values = audio.tags.get(key)
        return str(values[0]).strip() if values else ""

    return first("artist"), first("title")


def identity_for_role(path: Path, *, root: Path | None = None) -> RoleFix:
    """Artist / album / title a role file should show in Traktor."""
    base = (root or STEMS_AUDIO).expanduser()
    folder_artist, folder_album = _folder_artist_album(path, base)
    parsed_a, parsed_al, parsed_t = _title_from_stem(path.stem)
    source = "filename"
    artist, album, title = parsed_a, parsed_al, parsed_t
    if not title:
        mix_a, mix_al, mix_t = _title_from_mix(path.parent, path)
        if mix_t:
            artist = artist or mix_a
            album = album or mix_al
            title = mix_t
            source = "mix-sibling"
    if not title:
        title = _title_from_album_folder(folder_album)
        if title:
            source = "album-folder"
    artist = artist or folder_artist
    if is_placeholder_artist(artist):
        artist = ""
    album = album or folder_album or "Singles"
    if title and is_beatport_title(title):
        title = pretty_beatport_title(title)
        source = "beatport-filename"
    if not title:
        source = "unresolved"
    current_artist, current_title = _tag_fields(path)
    writable = path.suffix.lower() in TAGGABLE and not any(
        path.name.lower().endswith(suffix) for suffix in SKIP_SUFFIX
    )
    stripped_tag = strip_role_markup(current_title) if current_title else ""
    needs_tags = writable and bool(title) and (
        not current_title
        or is_placeholder_title(current_title)
        or is_beatport_title(current_title)
        or current_title.lower() in ROLE_NAMES
        or (stripped_tag != current_title)
        or (is_placeholder_artist(current_artist) and bool(artist))
    )
    return RoleFix(
        path=str(path.resolve()),
        artist=artist or "",
        album=album or "Singles",
        title=title or "",
        source=source,
        write_tags=needs_tags,
    )


def plan_role_titles(*, stems_root: Path | None = None) -> list[RoleFix]:
    root = (stems_root or STEMS_AUDIO).expanduser()
    fixes: list[RoleFix] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        if not is_role_file(path) and path.stem.lower() not in ROLE_NAMES:
            continue
        if any(path.name.lower().endswith(suffix) for suffix in SKIP_SUFFIX):
            continue
        item = identity_for_role(path, root=root)
        if item.title:
            fixes.append(item)
    return fixes


def apply_role_tags(fixes: list[RoleFix]) -> int:
    written = 0
    for item in fixes:
        if not item.write_tags or not item.title:
            continue
        write_file_tags(
            Path(item.path),
            artist=item.artist,
            album=item.album,
            title=item.title,
            genre="",
            album_artist=item.artist,
        )
        written += 1
    return written


def _loc_to_path(directory: str, file_attr: str) -> Path:
    from urllib.parse import unquote

    decoded = unquote(file_attr or "")
    parts = [part for part in (directory or "").split("/:") if part]
    path = Path("/")
    for part in parts:
        path = path / part
    return (path / decoded).resolve() if decoded else path


def patch_nml_titles(
    fixes: list[RoleFix],
    nml: Path | None = None,
    *,
    execute: bool,
) -> int:
    """Set ENTRY TITLE/ARTIST from the role fix. Does not rewrite playlists."""
    from ix_crate.stems_playlists import TRAKTOR_NML

    nml_path = nml or TRAKTOR_NML
    by_path = {Path(item.path).resolve(): item for item in fixes if item.title}
    tree = ET.parse(nml_path)
    collection = tree.getroot().find("COLLECTION")
    if collection is None:
        return 0
    patched = 0
    for entry in collection.findall("ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        directory = location.get("DIR") or ""
        path = _loc_to_path(directory, location.get("FILE") or "")
        item = by_path.get(path)
        if item is not None:
            current = entry.get("TITLE") or ""
            if current == item.title and (not item.artist or entry.get("ARTIST") == item.artist):
                continue
            if execute:
                entry.set("TITLE", item.title)
                if item.artist:
                    entry.set("ARTIST", item.artist)
                album_el = entry.find("ALBUM")
                if album_el is not None and item.album:
                    album_el.set("TITLE", item.album)
            patched += 1
            continue
        if "stems_audio" not in directory:
            continue
        stripped = strip_role_markup(entry.get("TITLE") or "")
        if stripped and stripped != (entry.get("TITLE") or "") and not is_placeholder_title(stripped):
            if execute:
                entry.set("TITLE", stripped)
            patched += 1
    if execute and patched:
        write_tree(tree, nml_path)
    return patched


@dataclass
class StoreTitleFix:
    path: str
    old: str
    new: str
    cloud: bool = False


def plan_nml_store_titles(nml: Path | None = None) -> list[StoreTitleFix]:
    """Beatport catalog titles + Google Drive shortcut rows in collection.nml."""
    from ix_crate.stems_playlists import TRAKTOR_NML, is_cloud_path

    nml_path = nml or TRAKTOR_NML
    tree = ET.parse(nml_path)
    collection = tree.getroot().find("COLLECTION")
    if collection is None:
        return []
    fixes: list[StoreTitleFix] = []
    for entry in collection.findall("ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        directory = location.get("DIR") or ""
        if "stems_audio" not in directory:
            continue
        path = _loc_to_path(directory, location.get("FILE") or "")
        title = entry.get("TITLE") or ""
        if is_cloud_path(path):
            fixes.append(StoreTitleFix(path=str(path), old=title, new="", cloud=True))
            continue
        if not is_beatport_title(title):
            continue
        pretty = pretty_beatport_title(title)
        if pretty and pretty != title:
            fixes.append(StoreTitleFix(path=str(path), old=title, new=pretty))
    return fixes


def apply_nml_store_titles(
    fixes: list[StoreTitleFix],
    nml: Path | None = None,
    *,
    execute: bool,
) -> tuple[int, int]:
    """Pretty Beatport TITLEs and drop CloudStorage collection rows."""
    from ix_crate.stems_playlists import TRAKTOR_NML, is_cloud_path

    nml_path = nml or TRAKTOR_NML
    tree = ET.parse(nml_path)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        return 0, 0
    by_path = {
        Path(item.path).resolve(): item
        for item in fixes
        if item.new and not item.cloud
    }
    cloud_keys: set[str] = set()
    titled = 0
    dropped = 0
    for entry in list(collection.findall("ENTRY")):
        location = entry.find("LOCATION")
        if location is None:
            continue
        path = _loc_to_path(location.get("DIR") or "", location.get("FILE") or "")
        if is_cloud_path(path):
            key = f"{location.get('VOLUME') or 'Macintosh HD'}{location.get('DIR') or ''}{location.get('FILE') or ''}"
            cloud_keys.add(key)
            if execute:
                collection.remove(entry)
            dropped += 1
            continue
        item = by_path.get(path)
        if item is None:
            continue
        if execute:
            entry.set("TITLE", item.new)
        titled += 1
    if execute and cloud_keys:
        playlists = root.find("PLAYLISTS")
        if playlists is not None:
            for playlist in playlists.iter("PLAYLIST"):
                for entry in list(playlist.findall("ENTRY")):
                    pk = entry.find("PRIMARYKEY")
                    if pk is not None and (pk.get("KEY") or "") in cloud_keys:
                        playlist.remove(entry)
                playlist.set("ENTRIES", str(len(playlist.findall("ENTRY"))))
    if execute:
        collection.set("ENTRIES", str(len(collection.findall("ENTRY"))))
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = nml_path.with_suffix(nml_path.suffix + f".pre-titles-{stamp}")
        if not backup.exists():
            import shutil

            shutil.copy2(nml_path, backup)
        write_tree(tree, nml_path)
    return titled, dropped


def format_store_title_plan(fixes: list[StoreTitleFix]) -> str:
    cloud = sum(1 for item in fixes if item.cloud)
    titled = len(fixes) - cloud
    lines = [f"store titles: {titled} beatport  cloud-rows {cloud}"]
    for item in fixes[:12]:
        if item.cloud:
            lines.append(f"  drop cloud  {Path(item.path).name}")
        else:
            lines.append(f"  {item.old}  →  {item.new}")
    if len(fixes) > 12:
        lines.append(f"  … {len(fixes) - 12} more")
    return "\n".join(lines)


def write_role_report(fixes: list[RoleFix], extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {"fixes": [asdict(item) for item in fixes], **(extra or {})}
    dest = REPORTS / f"stemit-role-titles-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def format_role_plan(fixes: list[RoleFix]) -> str:
    taggable = sum(1 for item in fixes if item.write_tags)
    wav = sum(1 for item in fixes if Path(item.path).suffix.lower() in {".wav", ".aiff", ".aif"})
    unresolved = sum(1 for item in fixes if not item.title)
    lines = [
        f"role titles: {len(fixes)} resolved  tags {taggable}  wav/nml-only {wav}  unresolved {unresolved}"
    ]
    sources: dict[str, int] = {}
    for item in fixes:
        sources[item.source] = sources.get(item.source, 0) + 1
    if sources:
        lines.append("  sources " + " ".join(f"{key}={count}" for key, count in sorted(sources.items())))
    for item in fixes[:12]:
        mark = "tag" if item.write_tags else "nml"
        lines.append(f"  {mark}  {item.artist} — {item.title}  ({item.source})")
    if len(fixes) > 12:
        lines.append(f"  … {len(fixes) - 12} more")
    return "\n".join(lines)
