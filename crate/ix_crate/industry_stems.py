"""Fill real artists on Industry Stems packs, then keep one row per STEMIT crate.

Industry Stems dumps land as ``stems_audio/IndustryStems/NN_Title/{drums,bass,
other,vocals}.wav``. Traktor files them as artist IndustryStems. The title is
the folder. The artist is already in the crate (NIN, FLA, Queen, …) or in
the iTunes/Deezer/MusicBrainz cascade. Never mutagen-write the WAVs. Never
Discogs. Music.app does not re-read tags — AppleScript specimen lives in
``docs/examples/music-set-industry-artist.applescript``.

STEMIT Stems dupes are the same cut under Artist/Album *and* Mashups / Spring
Blossoms. Mix / stem / vocals / instrumental stay four files. This pass
keeps one playlist row per crate identity; files stay on disk.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ix_crate.xml_io import write_tree
from ix_crate.identify import (
    is_placeholder_artist,
    is_placeholder_title,
    normalize_title,
    parse_filename,
    titles_match,
)
from ix_crate.lookup import catalog_identify, itunes_search, pick_catalog_hit
from ix_crate.paths import REPORTS, STEMS_AUDIO
from ix_crate.role_titles import _title_from_album_folder, traktor_is_running
from ix_crate.stems_playlists import (
    DiskFile,
    TRAKTOR_NML,
    _loc_to_path,
    crate_identity,
    prefer_crate_files,
    walk_stems,
    write_traktor,
)

INDUSTRY_DIR_NAMES = {
    "industrystems",
    "industry stems",
    "industry-stems",
}
PACK_PREFIX = re.compile(r"^\d{1,3}[_ ]+")
TOOL_ID = "ix.crate.stemit-industry"
WEAK_ARTISTS = {"compilations", "unknown artist", "unknown"}
CATALOG_MIN_TITLE = 12


def fold_title(value: str) -> str:
    """Strip diacritics and folder censorship so Naive matches Naïve."""
    import unicodedata

    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("'", "").replace("'", "").replace("'", "")
    text = re.sub(r"\bi\s+m\b", "im", text, flags=re.I)
    text = re.sub(r"\bf[\W_]*k\b", "fuck", text, flags=re.I)
    return normalize_title(text)


@dataclass
class IndustryFix:
    folder: str
    title: str
    artist: str
    album: str
    source: str
    files: list[str] = field(default_factory=list)


@dataclass
class CrateKeeper:
    crate: str
    artist: str
    title: str
    keep: str
    dropped: list[str] = field(default_factory=list)


@dataclass
class IndustryPlan:
    packs: int = 0
    resolved: int = 0
    unresolved: int = 0
    files: int = 0
    nml_patched: int = 0
    crate_dropped: int = 0
    xml_patched: int = 0
    music_patched: int = 0
    fixes: list[IndustryFix] = field(default_factory=list)
    keepers: list[CrateKeeper] = field(default_factory=list)


def is_industry_name(value: str) -> bool:
    compact = re.sub(r"[\s_\-]+", " ", (value or "").strip().lower())
    return compact in INDUSTRY_DIR_NAMES or compact.replace(" ", "") == "industrystems"


def industry_folder_title(name: str) -> str:
    """``101_Wish`` / ``03_God_is_God`` → the track title."""
    text = PACK_PREFIX.sub("", (name or "").replace("_", " ").strip())
    text = re.sub(r"\s+", " ", text).strip()
    titled = _title_from_album_folder(text) or text
    return titled


def industry_root(stems_root: Path) -> Path | None:
    base = stems_root.expanduser()
    if not base.is_dir():
        return None
    for child in sorted(base.iterdir()):
        if child.is_dir() and is_industry_name(child.name):
            return child
    return None


def _pick_artist(counts: Counter[str]) -> str | None:
    if not counts:
        return None
    ranked = Counter(
        {
            artist: n
            for artist, n in counts.items()
            if artist and artist.lower() not in WEAK_ARTISTS and not is_placeholder_artist(artist)
        }
    )
    if not ranked:
        return None
    if len(ranked) == 1:
        return next(iter(ranked))
    top, second = ranked.most_common(2)
    if second[1] < top[1]:
        return top[0]
    return None


def crate_title_index(stems_root: Path) -> dict[str, Counter[str]]:
    """normalize_title → artist counts from stems_audio (skip Industry Stems)."""
    index: dict[str, Counter[str]] = defaultdict(Counter)
    root = stems_root.expanduser()
    if not root.is_dir():
        return index
    for artist_dir in root.iterdir():
        if not artist_dir.is_dir() or is_industry_name(artist_dir.name):
            continue
        artist = artist_dir.name
        if is_placeholder_artist(artist) or artist.startswith("_"):
            continue
        for path in artist_dir.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            stem = path.stem
            if stem.lower() in {
                "vocals",
                "drums",
                "bass",
                "other",
                "instrumental",
            }:
                title = industry_folder_title(path.parent.name)
            else:
                _a, _al, parsed = parse_filename(stem)
                title = parsed or stem
            key = normalize_title(title)
            if key:
                index[key][artist] += 1
    return index


def match_crate_artist(title: str, index: dict[str, Counter[str]]) -> tuple[str, str]:
    key = fold_title(title)
    if not key:
        return "", ""
    folded_index: dict[str, Counter[str]] = defaultdict(Counter)
    for other, counts in index.items():
        folded_index[fold_title(other)].update(counts)
    hit = _pick_artist(folded_index.get(key, Counter()))
    if hit:
        return hit, "crate-exact"
    compact = key.replace(" ", "")
    squeezed: Counter[str] = Counter()
    for other, counts in folded_index.items():
        if other.replace(" ", "") == compact:
            squeezed.update(counts)
    hit = _pick_artist(squeezed)
    if hit:
        return hit, "crate-exact"
    fuzzy: Counter[str] = Counter()
    matches = 0
    for other, counts in folded_index.items():
        if titles_match(key, other) or titles_match(other, key):
            fuzzy.update(counts)
            matches += 1
            if matches > 8:
                break
    artist = _pick_artist(fuzzy)
    if artist and matches <= 8:
        return artist, "crate-fuzzy"
    prefix: Counter[str] = Counter()
    prefix_hits = 0
    for other, counts in folded_index.items():
        if len(other) < 12:
            continue
        if key.startswith(other) or other.startswith(key):
            prefix.update(counts)
            prefix_hits += 1
    artist = _pick_artist(prefix)
    if artist and prefix_hits <= 6:
        return artist, "crate-prefix"
    words: Counter[str] = Counter()
    word_hits = 0
    industry_words = key.split()
    for other, counts in folded_index.items():
        crate_words = other.split()
        shared = 0
        for left, right in zip(industry_words, crate_words):
            if left != right:
                break
            shared += 1
        if shared >= 3:
            words.update(counts)
            word_hits += 1
    artist = _pick_artist(words)
    if artist and word_hits <= 6:
        return artist, "crate-prefix"
    longest = ""
    longest_artist = ""
    for other, counts in folded_index.items():
        if len(other.split()) < 3:
            continue
        if key.startswith(other + " ") and len(other) > len(longest):
            pick = _pick_artist(counts)
            if pick:
                longest = other
                longest_artist = pick
    if longest_artist:
        return longest_artist, "crate-prefix"
    return "", ""


def _catalog_artist(title: str, path: Path | None) -> tuple[str, str, str]:
    if len(fold_title(title)) < CATALOG_MIN_TITLE:
        return "", "", ""
    duration = None
    if path is not None and path.is_file():
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(path)
            if audio is not None and audio.info is not None:
                duration = float(audio.info.length or 0) or None
        except Exception:
            duration = None
    cache: dict = {}
    try:
        from ix_crate.lookup import _load_cache

        cache = _load_cache()
    except Exception:
        cache = {}
    hit = catalog_identify(title, "", duration, cache, aggressive=True)
    if hit and hit.get("artist") and not is_placeholder_artist(str(hit["artist"])):
        return (
            str(hit["artist"]),
            str(hit.get("album") or "Industry Stems"),
            str(hit.get("source") or "catalog"),
        )
    titled = pick_catalog_hit(itunes_search(title, cache), title, duration)
    if titled and titled.get("artist") and not is_placeholder_artist(str(titled["artist"])):
        return str(titled["artist"]), str(titled.get("album") or "Industry Stems"), "itunes"
    return "", "", ""


def _duration_s(path: Path | None) -> float | None:
    if path is None or not path.is_file():
        return None
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
        if audio is not None and audio.info is not None:
            return float(audio.info.length or 0) or None
    except Exception:
        return None
    return None


def _listen_file(files: list[str]) -> Path | None:
    paths = [Path(item) for item in files]
    for stem in ("vocals", "other", "drums", "bass"):
        hit = next((path for path in paths if path.stem.lower() == stem), None)
        if hit is not None:
            return hit
    return next((path for path in paths if path.is_file()), None)


def _listen_artist(title: str, path: Path | None) -> tuple[str, str, str]:
    """STEMIT leftover cascade: AcoustID → MusicBrainz duration → Shazam."""
    if path is None or not path.is_file():
        return "", "", ""
    cache: dict = {}
    try:
        from ix_crate.lookup import _load_cache

        cache = _load_cache()
    except Exception:
        cache = {}
    duration = _duration_s(path)

    def _ok(hit: dict | None, fallback: str) -> tuple[str, str, str]:
        if not hit or not hit.get("artist"):
            return "", "", ""
        artist = str(hit["artist"])
        if is_placeholder_artist(artist):
            return "", "", ""
        album = str(hit.get("album") or "Industry Stems")
        source = str(hit.get("source") or fallback)
        return artist, album, source

    try:
        from ix_crate.acoustid import acoustid_identify

        artist, album, source = _ok(acoustid_identify(path, cache, duration), "acoustid")
        if artist:
            return artist, album, source
    except Exception:
        pass
    if title and duration:
        try:
            from ix_crate.lookup import musicbrainz_duration_search

            artist, album, source = _ok(
                musicbrainz_duration_search(title, duration, cache), "musicbrainz"
            )
            if artist:
                return artist, album, source
        except Exception:
            pass
    try:
        from ix_crate.shazam import shazam_identify

        artist, album, source = _ok(shazam_identify(path, cache), "shazam")
        if artist:
            return artist, album, source
    except Exception:
        pass
    return "", "", ""


def resolve_pack(
    folder: Path,
    index: dict[str, Counter[str]],
    *,
    lookup: bool,
    on_progress=None,
) -> IndustryFix:
    title = industry_folder_title(folder.name)
    files = sorted(
        str(path.resolve())
        for path in folder.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
    artist, source = match_crate_artist(title, index)
    album = "Industry Stems"
    if not artist:
        parsed_a, parsed_al, parsed_t = parse_filename(title)
        if parsed_a and not is_placeholder_artist(parsed_a) and parsed_t:
            artist, album, source = parsed_a, parsed_al or album, "filename"
            title = parsed_t
    if not artist and lookup and title and not is_placeholder_title(title):
        vocals = next((Path(item) for item in files if Path(item).stem.lower() == "vocals"), None)
        cat_a, cat_al, cat_src = _catalog_artist(title, vocals)
        if cat_a:
            artist, album, source = cat_a, cat_al or album, cat_src
    if not artist and lookup:
        listen = _listen_file(files)
        listen_a, listen_al, listen_src = _listen_artist(title, listen)
        if listen_a:
            artist, album, source = listen_a, listen_al or album, listen_src
    if on_progress:
        on_progress(folder.name, artist or "unresolved", source or "unresolved")
    return IndustryFix(
        folder=str(folder),
        title=title,
        artist=artist or "",
        album=album,
        source=source or "unresolved",
        files=files,
    )


def plan_industry_artists(
    *,
    stems_root: Path | None = None,
    lookup: bool = True,
    on_progress=None,
) -> list[IndustryFix]:
    root = (stems_root or STEMS_AUDIO).expanduser()
    pack_root = industry_root(root)
    if pack_root is None:
        return []
    albums = sorted(path for path in pack_root.iterdir() if path.is_dir())
    index = crate_title_index(root)
    fixes: list[IndustryFix] = []
    total = len(albums)
    for i, folder in enumerate(albums, start=1):
        def tick(name: str, artist: str, source: str, i=i, total=total) -> None:
            if on_progress:
                on_progress(i, total, name, artist, source)

        fixes.append(resolve_pack(folder, index, lookup=lookup, on_progress=tick))
    return fixes


def artist_map(fixes: list[IndustryFix]) -> dict[Path, IndustryFix]:
    by_path: dict[Path, IndustryFix] = {}
    for item in fixes:
        if not item.artist:
            continue
        for raw in item.files:
            by_path[Path(raw).resolve()] = item
    return by_path


def plan_crate_keepers(
    *,
    stems_root: Path | None = None,
    fixes: list[IndustryFix] | None = None,
) -> list[CrateKeeper]:
    root = (stems_root or STEMS_AUDIO).expanduser()
    resolved = artist_map(fixes or [])
    files = walk_stems(root)
    keepers = prefer_crate_files(files, root, resolved=resolved)
    keep_set = {item.path.resolve() for item in keepers}
    groups: dict[tuple[str, str, str], list[DiskFile]] = defaultdict(list)
    for item in files:
        groups[crate_identity(item, root, resolved)].append(item)
    report: list[CrateKeeper] = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        kept = next((row for row in rows if row.path.resolve() in keep_set), rows[0])
        dropped = [str(row.path) for row in rows if row.path.resolve() != kept.path.resolve()]
        if not dropped:
            continue
        crate, artist, title = crate_identity(kept, root, resolved)
        hit = resolved.get(kept.path.resolve())
        report.append(
            CrateKeeper(
                crate=kept.crate,
                artist=(getattr(hit, "artist", None) or artist),
                title=(getattr(hit, "title", None) or title),
                keep=str(kept.path),
                dropped=dropped,
            )
        )
    report.sort(key=lambda item: (item.crate, item.artist.lower(), item.title.lower()))
    return report


def patch_nml_industry(
    fixes: list[IndustryFix],
    nml: Path | None = None,
    *,
    execute: bool,
) -> int:
    nml_path = nml or TRAKTOR_NML
    by_path = artist_map(fixes)
    if not by_path or not nml_path.is_file():
        return 0
    tree = ET.parse(nml_path)
    collection = tree.getroot().find("COLLECTION")
    if collection is None:
        return 0
    patched = 0
    for entry in collection.findall("ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        path = _loc_to_path(location.get("DIR") or "", location.get("FILE") or "")
        item = by_path.get(path)
        if item is None:
            continue
        changed = False
        if item.title and entry.get("TITLE") != item.title:
            if execute:
                entry.set("TITLE", item.title)
            changed = True
        if item.artist and entry.get("ARTIST") != item.artist:
            if execute:
                entry.set("ARTIST", item.artist)
            changed = True
        album_el = entry.find("ALBUM")
        if item.album:
            if album_el is None:
                if execute:
                    ET.SubElement(entry, "ALBUM", TITLE=item.album)
                changed = True
            elif album_el.get("TITLE") != item.album:
                if execute:
                    album_el.set("TITLE", item.album)
                changed = True
        if changed:
            patched += 1
    if execute and patched:
        import shutil

        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = nml_path.with_suffix(nml_path.suffix + f".pre-industry-{stamp}")
        shutil.copy2(nml_path, backup)
        write_tree(tree, nml_path)
    return patched


def patch_xml_industry(
    fixes: list[IndustryFix],
    xml: Path | None = None,
    *,
    execute: bool,
) -> int:
    from urllib.parse import unquote

    from ix_crate.stems_playlists import REKORDBOX_XML

    xml_path = xml or REKORDBOX_XML
    by_path = artist_map(fixes)
    by_folder = {Path(item.folder).name: item for item in fixes if item.artist}
    if (not by_path and not by_folder) or not xml_path.is_file():
        return 0
    tree = ET.parse(xml_path)
    collection = tree.getroot().find("COLLECTION")
    if collection is None:
        return 0
    patched = 0
    for track in collection.findall("TRACK"):
        raw = unquote((track.get("Location") or "").replace("file://localhost", "").replace("file://", ""))
        if not raw:
            continue
        path = Path(raw)
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path
        item = by_path.get(resolved) or by_path.get(path)
        if item is None and "IndustryStems" in resolved.parts:
            idx = resolved.parts.index("IndustryStems")
            if idx + 1 < len(resolved.parts):
                item = by_folder.get(resolved.parts[idx + 1])
        if item is None:
            continue
        changed = False
        if item.title and track.get("Name") != item.title:
            if execute:
                track.set("Name", item.title)
            changed = True
        if item.artist and track.get("Artist") != item.artist:
            if execute:
                track.set("Artist", item.artist)
            changed = True
        if item.album and (track.get("Album") or "") != item.album:
            if execute:
                track.set("Album", item.album)
            changed = True
        if changed:
            patched += 1
    if execute and patched:
        import shutil

        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = xml_path.with_suffix(xml_path.suffix + f".pre-industry-{stamp}")
        shutil.copy2(xml_path, backup)
        write_tree(tree, xml_path)
    return patched


def write_applescript_tsv(fixes: list[IndustryFix], dest: Path | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = dest or (REPORTS / f"industry-stems-artists-{stamp}.tsv")
    lines = ["posix_path\tartist\talbum\ttitle"]
    for item in fixes:
        if not item.artist:
            continue
        for raw in item.files:
            lines.append(f"{raw}\t{item.artist}\t{item.album}\t{item.title}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_industry_report(plan: IndustryPlan, extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "packs": plan.packs,
        "resolved": plan.resolved,
        "unresolved": plan.unresolved,
        "files": plan.files,
        "nml_patched": plan.nml_patched,
        "crate_dropped": plan.crate_dropped,
        "fixes": [asdict(item) for item in plan.fixes],
        "keepers": [asdict(item) for item in plan.keepers],
        **(extra or {}),
    }
    dest = REPORTS / f"stemit-industry-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def format_industry_plan(plan: IndustryPlan) -> str:
    sources = Counter(item.source for item in plan.fixes)
    lines = [
        f"industry stems: {plan.packs} packs  resolved {plan.resolved}  "
        f"unresolved {plan.unresolved}  files {plan.files}  "
        f"nml {plan.nml_patched}  xml {plan.xml_patched}  "
        f"crate extras {plan.crate_dropped}"
    ]
    if sources:
        lines.append(
            "  sources " + " ".join(f"{key}={count}" for key, count in sorted(sources.items()))
        )
    shown = 0
    for item in plan.fixes:
        if not item.artist:
            continue
        lines.append(f"  artist  {item.artist} — {item.title}  ({item.source})")
        shown += 1
        if shown >= 12:
            break
    leftover = [item for item in plan.fixes if not item.artist]
    if leftover:
        lines.append(f"  unresolved {len(leftover)}")
        for item in leftover[:8]:
            lines.append(f"    {Path(item.folder).name}  →  {item.title}")
    by_crate: Counter[str] = Counter()
    dropped = 0
    for item in plan.keepers:
        by_crate[item.crate] += 1
        dropped += len(item.dropped)
    if by_crate:
        lines.append(
            "  crate dupes "
            + " ".join(f"{name}={by_crate[name]}" for name in ("Mixes", "Stems", "Acapellas", "Instrumentals") if by_crate[name])
            + f"  extra rows {dropped}"
        )
        for item in plan.keepers[:8]:
            lines.append(
                f"    keep {item.crate}  {item.artist} — {item.title}  "
                f"drop {len(item.dropped)}"
            )
        if len(plan.keepers) > 8:
            lines.append(f"    … {len(plan.keepers) - 8} more identity groups")
    return "\n".join(lines)


def build_industry_plan(
    *,
    lookup: bool = True,
    stems_root: Path | None = None,
    on_progress=None,
) -> IndustryPlan:
    root = (stems_root or STEMS_AUDIO).expanduser()
    fixes = plan_industry_artists(stems_root=root, lookup=lookup, on_progress=on_progress)
    keepers = plan_crate_keepers(stems_root=root, fixes=fixes)
    return IndustryPlan(
        packs=len(fixes),
        resolved=sum(1 for item in fixes if item.artist),
        unresolved=sum(1 for item in fixes if not item.artist),
        files=sum(len(item.files) for item in fixes),
        crate_dropped=sum(len(item.dropped) for item in keepers),
        fixes=fixes,
        keepers=keepers,
    )


def apply_industry_plan(
    plan: IndustryPlan,
    *,
    nml: Path | None = None,
    xml: Path | None = None,
    stems_root: Path | None = None,
) -> IndustryPlan:
    from ix_crate.stems_playlists import REKORDBOX_XML, rekordbox_is_running, traktor_index

    root = (stems_root or STEMS_AUDIO).expanduser()
    nml_path = nml or TRAKTOR_NML
    xml_path = xml or REKORDBOX_XML
    if not traktor_is_running():
        plan.nml_patched = patch_nml_industry(plan.fixes, nml=nml_path, execute=True)
        resolved = artist_map(plan.fixes)
        files = prefer_crate_files(walk_stems(root), root, resolved=resolved)
        write_traktor(files, traktor_index(nml_path), nml_path, stems_root=root)
    if xml_path.is_file() and not rekordbox_is_running():
        plan.xml_patched = patch_xml_industry(plan.fixes, xml=xml_path, execute=True)
    return plan


def run_industry_pass(
    *,
    execute: bool,
    lookup: bool = True,
    nml: Path | None = None,
    stems_root: Path | None = None,
    on_progress=None,
) -> IndustryPlan:
    plan = build_industry_plan(
        lookup=lookup, stems_root=stems_root, on_progress=on_progress
    )
    tsv = write_applescript_tsv(plan.fixes)
    extra = {
        "execute": execute,
        "traktor_running": traktor_is_running(),
        "applescript_tsv": str(tsv),
    }
    if not execute:
        extra["report"] = str(write_industry_report(plan, extra))
        return plan
    if traktor_is_running():
        extra["nml_skipped"] = "traktor-open"
        extra["report"] = str(write_industry_report(plan, extra))
        return plan
    apply_industry_plan(plan, nml=nml, stems_root=stems_root)
    extra["nml_patched"] = plan.nml_patched
    extra["stemit_rebuilt"] = True
    extra["report"] = str(write_industry_report(plan, extra))
    return plan
