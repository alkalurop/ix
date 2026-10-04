"""Repair Traktor collection.nml playlists and missing artwork IDs.

Playlist crates sometimes list the same PRIMARYKEY twice. This pass keeps
the first row and drops the extra. Collection paths are not deleted —
STEMIT Mixes / Stems / Acapellas / Instrumentals are four files, not
copies.

Missing artwork: copy a sibling's COVERARTID when the Coverart cache
file exists. Same folder first, then the same artist+album (never the
Singles dump). Does not mint NI cache files. Never writes rekordbox.xml.
Quit Traktor before --execute.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ix_crate.families import STEM_SUFFIXES
from ix_crate.identify import PLACEHOLDER_ALBUMS, duration_close
from ix_crate.music_repair import strip_copy_suffix
from ix_crate.music_replicants import _byte_digest, same_audio
from ix_crate.paths import REPORTS, STEMS_AUDIO
from ix_crate.riff_repair import copy_number
from ix_crate.safety import CrateSafetyError, assert_under_stems
from ix_crate.stems_playlists import TRAKTOR_NML
from ix_crate.xml_io import write_tree

COVERART = TRAKTOR_NML.parent / "Coverart"
TOOL_ID = "ix.crate.traktor-nml"
COPY_AUDIO = {".wav", ".aiff", ".aif", ".mp3", ".m4a"}
LENGTH_SLACK = 0.25


@dataclass
class PlaylistDedupe:
    path: str
    extras: int
    kept: int


@dataclass
class CopyTwin:
    keep: str
    drop: str
    seconds: float
    crate_note: str = ""


@dataclass
class NmlRepairPlan:
    playlist_extras: int = 0
    playlists: list[PlaylistDedupe] = field(default_factory=list)
    artwork: int = 0
    broken_cover_fixed: int = 0
    twins: list[CopyTwin] = field(default_factory=list)
    twins_skipped: int = 0
    stemit_rebuilt: bool = False


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


def mutagen_seconds(path: Path) -> float | None:
    """Duration from the file header. Never writes tags."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
    except Exception:
        return None
    if audio is None or audio.info is None:
        return None
    length = getattr(audio.info, "length", None)
    try:
        return float(length) if length else None
    except (TypeError, ValueError):
        return None


def is_stem_container(path: Path) -> bool:
    """True for ``.stem.m4a`` and Finder copies ``.stem (2).m4a``."""
    name = path.name.lower()
    if any(name.endswith(suffix) for suffix in STEM_SUFFIXES):
        return True
    return ".stem" in name and path.suffix.lower() in {".m4a", ".mp4", ".mp3"}


def _same_copy(keep: Path, extra: Path, cache: dict[str, str]) -> bool:
    """Mutagen duration already matched. Confirm audio without writing tags.

    Stem containers are never ffmpeg-decoded (too slow; never mutagen-write).
    WAV / ordinary m4a use the replicants decode hash.
    """
    if is_stem_container(keep) or is_stem_container(extra):
        try:
            if keep.stat().st_size != extra.stat().st_size:
                return False
        except OSError:
            return False
        a, b = _byte_digest(keep), _byte_digest(extra)
        return bool(a and a == b)
    return same_audio([keep, extra], cache)


def plan_copy_twins(*, stems_root: Path | None = None) -> tuple[list[CopyTwin], int]:
    """Finder ``(2)`` copies whose mutagen length matches and audio hashes equal.

    Mix / vocals / instrumental stay distinct: they do not share a copy-suffix
    stem. WAV is the IndustryStems pattern; ``.stem (2).m4a`` is the same
    Finder duplicate sitting in STEMIT Mixes because classify misses it.
    """
    root = (stems_root or STEMS_AUDIO).expanduser()
    twins: list[CopyTwin] = []
    skipped = 0
    cache: dict[str, str] = {}
    if not root.is_dir():
        return twins, skipped
    for extra in root.rglob("*"):
        if not extra.is_file() or extra.name.startswith("."):
            continue
        if copy_number(extra.stem) == 0:
            continue
        if extra.suffix.lower() not in COPY_AUDIO:
            continue
        keep = extra.with_name(strip_copy_suffix(extra.stem) + extra.suffix)
        if not keep.is_file() or keep.resolve() == extra.resolve():
            continue
        left = mutagen_seconds(keep)
        right = mutagen_seconds(extra)
        stemish = is_stem_container(keep) or is_stem_container(extra)
        if left is None and right is None and stemish:
            length_ok = True
        else:
            length_ok = duration_close(left, right, slack=LENGTH_SLACK)
        if not length_ok:
            skipped += 1
            continue
        if not _same_copy(keep, extra, cache):
            skipped += 1
            continue
        note = "mutagen-length+stem-bytes" if stemish else "mutagen-length+audio"
        twins.append(
            CopyTwin(
                keep=str(keep),
                drop=str(extra),
                seconds=left or right or 0.0,
                crate_note=note,
            )
        )
    twins.sort(key=lambda item: item.drop.lower())
    return twins, skipped


def apply_copy_twins(
    twins: list[CopyTwin], *, stems_root: Path | None = None
) -> int:
    removed = 0
    root = (stems_root or STEMS_AUDIO).expanduser().resolve()
    for item in twins:
        extra = Path(item.drop).expanduser().resolve()
        if stems_root is None:
            assert_under_stems(extra)
        else:
            try:
                extra.relative_to(root)
            except ValueError as exc:
                raise CrateSafetyError(f"Refusing path outside stems_audio: {extra}") from exc
        if extra.is_file():
            extra.unlink()
            removed += 1
    return removed


def drop_paths_from_nml(root: ET.Element, paths: Iterable[Path]) -> int:
    from ix_crate.stems_playlists import _loc_to_path, _traktor_key

    resolved = {path.expanduser().resolve() for path in paths}
    keys = {_traktor_key(path) for path in resolved}
    dropped = 0
    collection = root.find("COLLECTION")
    if collection is not None:
        for entry in list(collection.findall("ENTRY")):
            location = entry.find("LOCATION")
            if location is None:
                continue
            path = _loc_to_path(location.get("DIR") or "", location.get("FILE") or "")
            if path in resolved:
                collection.remove(entry)
                dropped += 1
        collection.set("ENTRIES", str(len(collection.findall("ENTRY"))))
    playlists = root.find("PLAYLISTS")
    if playlists is None:
        return dropped
    folder = playlists.find("NODE")
    if folder is None:
        return dropped
    for node, _path in _walk_playlists(folder):
        playlist = node.find("PLAYLIST")
        if playlist is None:
            continue
        kept = 0
        for entry in list(playlist.findall("ENTRY")):
            pk = entry.find("PRIMARYKEY")
            if pk is None:
                kept += 1
                continue
            key = (pk.get("TYPE") or "", pk.get("KEY") or "")
            if key in keys:
                playlist.remove(entry)
                continue
            kept += 1
        playlist.set("ENTRIES", str(kept))
    return dropped


def cache_ok(cid: str, cover_root: Path) -> bool:
    if not cid or "/" not in cid:
        return False
    folder, ident = cid.split("/", 1)
    if not folder or not ident:
        return False
    return (cover_root / folder / f"{ident}000").is_file()


def _playlist_path(stack: list[str], name: str) -> str:
    return "/".join(stack + [name])


def _walk_playlists(node: ET.Element, stack: list[str] | None = None):
    stack = stack or []
    if node.get("TYPE") == "PLAYLIST":
        yield node, _playlist_path(stack, node.get("NAME") or "")
    sub = node.find("SUBNODES")
    if sub is None:
        return
    name = node.get("NAME") or ""
    child_stack = stack + [name] if name else stack
    for child in sub.findall("NODE"):
        yield from _walk_playlists(child, child_stack)


def dedupe_playlists(root: ET.Element, *, execute: bool) -> list[PlaylistDedupe]:
    playlists_el = root.find("PLAYLISTS")
    if playlists_el is None:
        return []
    root_node = playlists_el.find("NODE")
    if root_node is None:
        return []
    reports: list[PlaylistDedupe] = []
    for node, path in _walk_playlists(root_node):
        playlist = node.find("PLAYLIST")
        if playlist is None:
            continue
        seen: set[tuple[str, str]] = set()
        extras = 0
        kept = 0
        for entry in list(playlist.findall("ENTRY")):
            pk = entry.find("PRIMARYKEY")
            if pk is None:
                kept += 1
                continue
            key = (pk.get("TYPE") or "", pk.get("KEY") or "")
            if key in seen:
                extras += 1
                if execute:
                    playlist.remove(entry)
                continue
            seen.add(key)
            kept += 1
        if extras:
            if execute:
                playlist.set("ENTRIES", str(kept))
            reports.append(PlaylistDedupe(path=path, extras=extras, kept=kept))
    return reports


def _cover_id(entry: ET.Element) -> str:
    info = entry.find("INFO")
    if info is None:
        return ""
    return info.get("COVERARTID") or ""


def _set_cover_id(entry: ET.Element, cid: str) -> None:
    info = entry.find("INFO")
    if info is None:
        info = ET.SubElement(entry, "INFO")
    info.set("COVERARTID", cid)


def _album_title(entry: ET.Element) -> str:
    album = entry.find("ALBUM")
    if album is None:
        return ""
    return album.get("TITLE") or ""


def _pick_cover(ids: list[str]) -> str | None:
    if not ids:
        return None
    return Counter(ids).most_common(1)[0][0]


def share_artwork(
    collection: ET.Element,
    cover_root: Path,
    *,
    execute: bool,
) -> tuple[int, int]:
    """Copy a valid sibling COVERARTID onto entries that have none."""
    by_dir: dict[str, list[ET.Element]] = defaultdict(list)
    by_album: dict[tuple[str, str], list[ET.Element]] = defaultdict(list)
    for entry in collection.findall("ENTRY"):
        loc = entry.find("LOCATION")
        if loc is None:
            continue
        by_dir[loc.get("DIR") or ""].append(entry)
        album = _album_title(entry).strip()
        if album.lower() in PLACEHOLDER_ALBUMS or album.lower() == "singles":
            continue
        artist = (entry.get("ARTIST") or "").strip().lower()
        by_album[(artist, album.lower())].append(entry)

    assigned: dict[int, str] = {}

    def apply_group(entries: list[ET.Element]) -> None:
        good = [
            _cover_id(item)
            for item in entries
            if cache_ok(_cover_id(item), cover_root)
        ]
        cid = _pick_cover(good)
        if not cid:
            return
        for item in entries:
            current = _cover_id(item)
            if cache_ok(current, cover_root):
                continue
            if id(item) in assigned:
                continue
            assigned[id(item)] = cid

    for entries in by_dir.values():
        apply_group(entries)
    for entries in by_album.values():
        apply_group(entries)

    artwork = 0
    broken = 0
    for entry in collection.findall("ENTRY"):
        cid = assigned.get(id(entry))
        if not cid:
            continue
        current = _cover_id(entry)
        if current and not cache_ok(current, cover_root):
            broken += 1
        artwork += 1
        if execute:
            _set_cover_id(entry, cid)
    return artwork, broken


def plan_repair(
    nml: Path | None = None,
    cover_root: Path | None = None,
    *,
    execute: bool,
) -> tuple[NmlRepairPlan, ET.ElementTree]:
    nml_path = nml or TRAKTOR_NML
    covers = cover_root or COVERART
    tree = ET.parse(nml_path)
    root = tree.getroot()
    plan = NmlRepairPlan()
    plan.playlists = dedupe_playlists(root, execute=execute)
    plan.playlist_extras = sum(item.extras for item in plan.playlists)
    collection = root.find("COLLECTION")
    if collection is not None:
        plan.artwork, plan.broken_cover_fixed = share_artwork(
            collection, covers, execute=execute
        )
    return plan, tree


def write_nml(tree: ET.ElementTree, nml: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = nml.with_suffix(nml.suffix + f".pre-nml-repair-{stamp}")
    shutil.copy2(nml, backup)
    write_tree(tree, nml)
    return backup


def write_report(plan: NmlRepairPlan, extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "playlist_extras": plan.playlist_extras,
        "artwork": plan.artwork,
        "broken_cover_fixed": plan.broken_cover_fixed,
        "twins": [asdict(item) for item in plan.twins],
        "twins_skipped": plan.twins_skipped,
        "stemit_rebuilt": plan.stemit_rebuilt,
        "playlists": [asdict(item) for item in plan.playlists],
        **(extra or {}),
    }
    dest = REPORTS / f"traktor-nml-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def format_plan(plan: NmlRepairPlan) -> str:
    lines = [
        f"traktor-nml: playlist extras {plan.playlist_extras}  "
        f"artwork {plan.artwork}  broken-cover-fixed {plan.broken_cover_fixed}  "
        f"copy-twins {len(plan.twins)}  skipped {plan.twins_skipped}"
    ]
    for item in plan.playlists[:12]:
        lines.append(f"  playlist  {item.path}  extras {item.extras}  keep {item.kept}")
    if len(plan.playlists) > 12:
        lines.append(f"  … {len(plan.playlists) - 12} more playlists")
    for item in plan.twins[:8]:
        lines.append(f"  twin  drop {Path(item.drop).name}  keep {Path(item.keep).name}  {item.seconds:.1f}s")
    if len(plan.twins) > 8:
        lines.append(f"  … {len(plan.twins) - 8} more copy-twins")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write collection.nml. Quit Traktor first.",
    )
    args = parser.parse_args(argv)
    if args.execute and traktor_is_running():
        print("Traktor is open. Quit it before --execute.", file=sys.stderr)
        return 2
    plan, tree = plan_repair(execute=False)
    plan.twins, plan.twins_skipped = plan_copy_twins()
    report = write_report(plan, {"execute": args.execute})
    print(format_plan(plan), flush=True)
    print(f"report: {report}", flush=True)
    if not args.execute:
        print("dry-run. pass --execute to drop copy-twins, rewrite STEMIT crates, write collection.nml.", flush=True)
        return 0
    twins = list(plan.twins)
    try:
        apply_copy_twins(twins)
    except CrateSafetyError as exc:
        print(exc, file=sys.stderr)
        return 2
    plan, tree = plan_repair(execute=True)
    plan.twins = twins
    dropped = drop_paths_from_nml(tree.getroot(), [Path(item.drop) for item in twins])
    backup = write_nml(tree, TRAKTOR_NML)
    from ix_crate.stems_playlists import prefer_crate_files, traktor_index, walk_stems, write_traktor

    files = prefer_crate_files(walk_stems(), STEMS_AUDIO)
    index = traktor_index(TRAKTOR_NML)
    added = write_traktor(files, index, TRAKTOR_NML)
    plan.stemit_rebuilt = True
    write_report(
        plan,
        {
            "execute": True,
            "backup": str(backup),
            "nml_rows_dropped": dropped,
            "stemit_added": added,
        },
    )
    print(
        f"dropped {len(plan.twins)} copy files  nml rows {dropped}  "
        f"STEMIT rebuilt (+{added} collection). backup {backup}",
        flush=True,
    )
    print("reopen Traktor. Mix / stem / vocals / instrumental stay four files.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
