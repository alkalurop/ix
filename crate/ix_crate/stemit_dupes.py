"""Delete confirmed STEMIT copies from stems_audio, then rebuild crates.

The last pass only dropped playlist rows. Finder still had Mashups / Unknown
Album / Spring Blossoms copies, plus ``Title - vocals.m4a`` sitting next to
``Title_vocals.m4a``. This pass groups by crate + family key, keeps one
file, and unlinks extras when they are a dump copy, a dump-vs-dump twin,
a stem remux (``.stem.m4a`` vs ``.stem.mp3``), or the same audio.

Never deletes a unique mashup (no counterpart under Artist/Album).
Never deletes Industry Stems official WAV packs.
Never mutagen-writes. Never ffmpeg-decodes ``.stem.m4a``.
Never touches Media.localized. Families stay four files (mix / stem /
vocals / instrumental). Dry-run default.
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ix_crate.families import ROLE_NAMES, basename_without_container, family_key, is_audio
from ix_crate.xml_io import write_tree
from ix_crate.identify import duration_close, normalize_title
from ix_crate.music_repair import SKIP_SUFFIX
from ix_crate.music_replicants import _byte_digest, same_audio
from ix_crate.paths import REPORTS, STEMS_AUDIO
from ix_crate.role_titles import traktor_is_running
from ix_crate.safety import CrateSafetyError, assert_under_stems
from ix_crate.riff_repair import finder_copy_number
from ix_crate.stems_playlists import (
    classify,
    crate_keep_score,
    is_cloud_path,
    is_dump_path,
    prefer_crate_files,
    walk_stems,
)
from ix_crate.traktor_nml import is_stem_container, mutagen_seconds

TOOL_ID = "ix.crate.stemit-dedupe"
LENGTH_SLACK = 0.5


@dataclass
class DiskDupe:
    keep: str
    drop: str
    crate: str
    key: str
    reason: str


@dataclass
class DedupePlan:
    groups: int = 0
    extras: int = 0
    skipped: int = 0
    deleted: int = 0
    pruned: int = 0
    twins: list[DiskDupe] = field(default_factory=list)


def recording_key(path: Path) -> tuple[str, str]:
    crate = classify(path) or "parts"
    key = normalize_title(family_key(path))
    if not key or key in ROLE_NAMES:
        from ix_crate.industry_stems import industry_folder_title

        key = normalize_title(industry_folder_title(path.parent.name)) or path.stem.lower()
        if path.parent.parent.name.lower().replace(" ", "").replace("-", "") == "industrystems":
            key = f"{key} industry-pack"
    return crate, key


def is_industry_pack(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.expanduser().resolve())
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0].lower().replace(" ", "").replace("-", "") == "industrystems"


def _same_stem_bytes(keep: Path, extra: Path) -> bool:
    try:
        if keep.stat().st_size != extra.stat().st_size:
            return False
    except OSError:
        return False
    a, b = _byte_digest(keep), _byte_digest(extra)
    return bool(a and a == b)


def same_recording(keep: Path, extra: Path, cache: dict[str, str]) -> str:
    """Why extra is the same recording as keep, or empty if not."""
    try:
        if keep.stat().st_ino == extra.stat().st_ino:
            return "inode"
    except OSError:
        return ""
    stemish = is_stem_container(keep) or is_stem_container(extra)
    if stemish:
        if _same_stem_bytes(keep, extra):
            return "stem-bytes"
        return ""
    if any(path.name.lower().endswith(suffix) for suffix in SKIP_SUFFIX for path in (keep, extra)):
        return ""
    left, right = mutagen_seconds(keep), mutagen_seconds(extra)
    if not duration_close(left, right, slack=LENGTH_SLACK):
        return ""
    if same_audio([keep, extra], cache):
        return "same-audio"
    return ""


SPLIT_PARTS = {"drums", "bass", "other"}


def is_split_stem_part(path: Path) -> bool:
    """Mel / Industry drums-bass-other. Never collapse those into one file."""
    name = basename_without_container(path).lower()
    if name in SPLIT_PARTS:
        return True
    return any(
        name.endswith(f"_{role}") or name.endswith(f"- {role}") or name.endswith(f"-{role}")
        for role in SPLIT_PARTS
    )


def _family_copy_reason(keep: Path, extra: Path, confirmed: str) -> str:
    if confirmed:
        return confirmed
    if extra.name.lower() == keep.name.lower():
        return "dump-same-name"
    if recording_key(keep) != recording_key(extra):
        return ""
    if is_split_stem_part(keep) or is_split_stem_part(extra):
        return ""
    if is_stem_container(keep) or is_stem_container(extra):
        return "dump-same-stem-family"
    left, right = mutagen_seconds(keep), mutagen_seconds(extra)
    if left is None or right is None or duration_close(left, right, slack=LENGTH_SLACK):
        return "dump-same-family"
    return ""


def dump_copy(keep: Path, extra: Path, root: Path, cache: dict[str, str]) -> str:
    """Dump extras of the same family may be a re-mux (mp3 vs m4a)."""
    if is_industry_pack(extra, root) or is_industry_pack(keep, root):
        return ""
    extra_dump = is_dump_path(extra, root)
    confirmed = same_recording(keep, extra, cache)
    # Artist/Stems and Spring Blossoms are also dump folders. Still drop
    # the lower-ranked extra when both sides live in a dump.
    if extra_dump:
        return _family_copy_reason(keep, extra, confirmed)
    if confirmed:
        return confirmed
    if extra.name.lower() == keep.name.lower() and album_title_variant(keep, extra, root):
        return "album-variant"
    if is_split_stem_part(keep) or is_split_stem_part(extra):
        return ""
    if not (is_stem_container(keep) or is_stem_container(extra)):
        return ""
    if recording_key(keep) != recording_key(extra):
        return ""
    if keep.parent == extra.parent:
        return "stem-family-remux"
    return ""


def album_title_variant(keep: Path, extra: Path, root: Path) -> bool:
    """Same release filed twice under punctuation-variant album folders."""
    try:
        base = root.expanduser().resolve()
        keep_rel = keep.resolve().relative_to(base)
        extra_rel = extra.resolve().relative_to(base)
    except ValueError:
        return False
    if keep_rel.parts[0] != extra_rel.parts[0]:
        return False
    keep_album = keep_rel.parts[1] if len(keep_rel.parts) > 1 else ""
    extra_album = extra_rel.parts[1] if len(extra_rel.parts) > 1 else ""
    return _album_key(keep_album) == _album_key(extra_album) and bool(_album_key(keep_album))


def _album_key(name: str) -> str:
    text = normalize_title(name.replace("_", " "))
    for noise in (
        "original motion picture soundtrack",
        "original soundtrack",
        "motion picture soundtrack",
    ):
        text = text.replace(noise, " ")
    return " ".join(text.split())


def plan_disk_dupes(
    *,
    stems_root: Path | None = None,
    on_progress=None,
) -> DedupePlan:
    root = (stems_root or STEMS_AUDIO).expanduser()
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    if not root.is_dir():
        return DedupePlan()
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith(".") or not is_audio(path):
            continue
        if is_industry_pack(path, root):
            continue
        if is_cloud_path(path, root):
            continue
        groups[recording_key(path)].append(path.resolve())
    plan = DedupePlan()
    cache: dict[str, str] = {}
    items = [(key, rows) for key, rows in groups.items() if len(rows) > 1]
    plan.groups = len(items)
    total = len(items)
    for index, ((crate, key), rows) in enumerate(items, start=1):
        if on_progress:
            on_progress(index, total, key, crate)
        ranked = sorted(rows, key=lambda path: crate_keep_score(path, root), reverse=True)
        keep = ranked[0]
        for extra in ranked[1:]:
            if extra == keep:
                continue
            if is_industry_pack(extra, root):
                plan.skipped += 1
                continue
            reason = dump_copy(keep, extra, root, cache)
            if not reason:
                plan.skipped += 1
                continue
            plan.twins.append(
                DiskDupe(
                    keep=str(keep),
                    drop=str(extra),
                    crate=crate,
                    key=key,
                    reason=reason,
                )
            )
    plan.twins.sort(key=lambda item: (item.crate, item.key, item.drop.lower()))
    plan.extras = len(plan.twins)
    return plan


def copy_group_key(path: Path) -> tuple[str, Path, str]:
    from ix_crate.families import STEM_SUFFIXES, strip_role_markup
    from ix_crate.riff_repair import FINDER_COPY_MAX, copy_number

    crate = classify(path) or "parts"
    lower = path.name.lower()
    name = path.name
    for suffix in STEM_SUFFIXES:
        if lower.endswith(suffix):
            name = path.name[: -len(suffix)]
            break
    else:
        name = path.stem
    numbered = copy_number(name)
    if 0 < numbered <= FINDER_COPY_MAX and "(" in name:
        name = name[: name.rfind("(")].rstrip()
    name = re.sub(r"\.stem$", "", name, flags=re.I)
    key = normalize_title(strip_role_markup(name))
    key = re.sub(r"\s+\d{1,2}$", "", key)
    return crate, path.parent.resolve(), key


def plan_finder_copies(
    *,
    stems_root: Path | None = None,
) -> DedupePlan:
    """Finder ``(2)`` copies next to a keeper with the same title/artist role."""
    root = (stems_root or STEMS_AUDIO).expanduser()
    plan = DedupePlan()
    if not root.is_dir():
        return plan
    groups: dict[tuple[str, Path, str], list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith(".") or not is_audio(path):
            continue
        if is_industry_pack(path, root) or is_cloud_path(path, root):
            continue
        if is_split_stem_part(path):
            continue
        groups[copy_group_key(path)].append(path.resolve())
    items = [(key, rows) for key, rows in groups.items() if len(rows) > 1]
    plan.groups = len(items)
    for (crate, _parent, key), rows in items:
        keepers = [path for path in rows if finder_copy_number(path) == 0]
        copies = [path for path in rows if finder_copy_number(path) > 0]
        if not keepers or not copies:
            plan.skipped += len(copies)
            continue
        keep = max(keepers, key=lambda path: crate_keep_score(path, root))
        for extra in copies:
            plan.twins.append(
                DiskDupe(
                    keep=str(keep),
                    drop=str(extra),
                    crate=crate,
                    key=key,
                    reason="finder-copy",
                )
            )
    plan.twins.sort(key=lambda item: (item.crate, item.key, item.drop.lower()))
    plan.extras = len(plan.twins)
    return plan


def prune_empty_dirs(root: Path) -> int:
    """Remove empty folders under stems_audio. Never the root itself."""
    base = root.expanduser().resolve()
    removed = 0
    dirs = sorted(
        (path for path in base.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for folder in dirs:
        try:
            folder.relative_to(base)
        except ValueError:
            continue
        if folder == base:
            continue
        try:
            next(folder.iterdir())
        except StopIteration:
            folder.rmdir()
            removed += 1
        except OSError:
            continue
    return removed


def apply_disk_dupes(
    plan: DedupePlan,
    *,
    stems_root: Path | None = None,
    on_progress=None,
) -> int:
    root = (stems_root or STEMS_AUDIO).expanduser().resolve()
    deleted = 0
    total = len(plan.twins)
    for index, item in enumerate(plan.twins, start=1):
        extra = Path(item.drop).expanduser().resolve()
        if stems_root is None:
            assert_under_stems(extra)
        else:
            try:
                extra.relative_to(root)
            except ValueError as exc:
                raise CrateSafetyError(f"Refusing path outside stems_audio: {extra}") from exc
        if extra.is_file():
            if is_cloud_path(extra, root):
                plan.skipped += 1
                print(f"  skip cloud  {extra}", flush=True)
                continue
            try:
                extra.unlink()
            except OSError as exc:
                plan.skipped += 1
                print(f"  skip  {extra.name}  ({exc})", flush=True)
                continue
            deleted += 1
        if on_progress:
            on_progress(index, total, Path(item.drop).name, item.crate)
    plan.deleted = deleted
    plan.pruned = prune_empty_dirs(root)
    return deleted


def write_dedupe_report(plan: DedupePlan, extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "groups": plan.groups,
        "extras": plan.extras,
        "skipped": plan.skipped,
        "deleted": plan.deleted,
        "pruned": plan.pruned,
        "twins": [asdict(item) for item in plan.twins],
        **(extra or {}),
    }
    dest = REPORTS / f"stemit-dedupe-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def format_dedupe_plan(plan: DedupePlan) -> str:
    reasons: dict[str, int] = defaultdict(int)
    crates: dict[str, int] = defaultdict(int)
    for item in plan.twins:
        reasons[item.reason] += 1
        crates[item.crate] += 1
    lines = [
        f"stemit-dedupe: {plan.groups} groups  extras {plan.extras}  "
        f"skipped {plan.skipped}  deleted {plan.deleted}  pruned {plan.pruned}"
    ]
    if crates:
        lines.append(
            "  crates "
            + " ".join(
                f"{name}={crates[name]}"
                for name in ("Mixes", "Stems", "Acapellas", "Instrumentals", "parts")
                if crates[name]
            )
        )
    if reasons:
        lines.append(
            "  reasons " + " ".join(f"{key}={count}" for key, count in sorted(reasons.items()))
        )
    for item in plan.twins[:12]:
        lines.append(
            f"  drop  {item.crate}  {Path(item.drop).name}  keep {Path(item.keep).name}  ({item.reason})"
        )
    if len(plan.twins) > 12:
        lines.append(f"  … {len(plan.twins) - 12} more")
    return "\n".join(lines)


def drop_missing_stems_nml(root, stems_root: Path) -> int:
    """Drop collection rows under stems_audio whose files are gone."""
    from ix_crate.stems_playlists import _loc_to_path
    from ix_crate.traktor_nml import drop_paths_from_nml

    missing: list[Path] = []
    collection = root.find("COLLECTION")
    if collection is None:
        return 0
    base = stems_root.expanduser().resolve()
    for entry in collection.findall("ENTRY"):
        location = entry.find("LOCATION")
        if location is None:
            continue
        directory = location.get("DIR") or ""
        if "stems_audio" not in directory:
            continue
        path = _loc_to_path(directory, location.get("FILE") or "")
        try:
            path.relative_to(base)
        except ValueError:
            continue
        if not path.is_file():
            missing.append(path)
    if not missing:
        return 0
    return drop_paths_from_nml(root, missing)


def rebuild_after_dedupe(
    plan: DedupePlan,
    *,
    stems_root: Path | None = None,
) -> int:
    import shutil
    import xml.etree.ElementTree as ET

    from ix_crate.stems_playlists import TRAKTOR_NML, traktor_index, write_traktor
    from ix_crate.traktor_nml import drop_paths_from_nml

    root = (stems_root or STEMS_AUDIO).expanduser()
    nml = TRAKTOR_NML
    if not nml.is_file():
        return 0
    tree = ET.parse(nml)
    drop_paths_from_nml(tree.getroot(), [Path(item.drop) for item in plan.twins])
    drop_missing_stems_nml(tree.getroot(), root)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = nml.with_suffix(nml.suffix + f".pre-dedupe-{stamp}")
    shutil.copy2(nml, backup)
    write_tree(tree, nml)
    files = prefer_crate_files(walk_stems(root), root)
    return write_traktor(files, traktor_index(nml), nml, stems_root=root)
