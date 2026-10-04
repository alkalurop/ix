"""Rekordbox sampler Capture → Saved archive + ``SAMPLES/Samplers`` crates.

Reads ``~/Music/PioneerDJ/Sampler/Capture``, moves WAV captures into
``~/Music/PioneerDJ/Sampler/Saved``, and syncs the Saved folder into
rekordbox.xml and Traktor NML under ``SAMPLES/Samplers``.

When Saved already holds the same filename, the Capture file is removed
only if mutagen duration matches and decoded audio matches (same as
``music-replicants``). Different audio under the same name is left in
Capture for manual rename.

Dry-run default. Quit Rekordbox before xml. Quit Traktor before NML.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from ix_crate.crates import (
    CratePlaylist,
    SyncPlan,
    TrackRef,
    apply_nml,
    apply_xml,
    format_plan as format_sync_plan,
    nml_path_index,
    plan_membership,
    xml_path_index,
)
from ix_crate.dj_metadata import (
    enrich_ref_from_nml,
    enrich_ref_from_xml,
    match_xml_source_for_capture,
    nml_meta_by_path,
    xml_meta_by_path,
)
from ix_crate.identify import duration_close
from ix_crate.music_replicants import same_audio
from ix_crate.paths import REPORTS
from ix_crate.stems_playlists import REKORDBOX_XML, TRAKTOR_NML, rekordbox_is_running
from ix_crate.traktor_nml import mutagen_seconds, traktor_is_running

CAPTURE_DIR = Path.home() / "Music" / "PioneerDJ" / "Sampler" / "Capture"
SAVED_DIR = Path.home() / "Music" / "PioneerDJ" / "Sampler" / "Saved"
SAMPLES_FOLDER = "SAMPLES"
SAMPLERS_PLAYLIST = "Samplers"
TOOL_ID = "ix.crate.rekordbox-sample-crate"
LENGTH_SLACK = 0.25


@dataclass
class ArchiveAction:
    source: Path
    dest: Path
    action: str  # move | remove_duplicate | skip_exists | skip_conflict
    note: str = ""


@dataclass
class SampleCratePlan:
    capture_scanned: int = 0
    saved_count: int = 0
    archive: list[ArchiveAction] = field(default_factory=list)
    playlist_paths: list[str] = field(default_factory=list)


def sample_title_from_name(name: str) -> str:
    stem = Path(name).stem
    low = stem.lower()
    for suffix in ("_capture",):
        if low.endswith(suffix):
            return stem[: -len(suffix)].strip(" _-") or stem
    return stem


def sample_title_from_path(path: Path) -> str:
    return sample_title_from_name(path.name)


def _is_sample_file(path: Path) -> bool:
    if not path.is_file() or path.name.startswith("."):
        return False
    return path.suffix.lower() in {".wav", ".aiff", ".aif", ".flac", ".mp3"}


def _waves_same(left: Path, right: Path, cache: dict[str, str]) -> bool:
    a = mutagen_seconds(left)
    b = mutagen_seconds(right)
    if a is not None or b is not None:
        if not duration_close(a, b, slack=LENGTH_SLACK):
            return False
    return same_audio([left, right], cache)


def plan_archive_moves(
    *,
    capture: Path | None = None,
    saved: Path | None = None,
) -> list[ArchiveAction]:
    cap = (capture or CAPTURE_DIR).expanduser()
    store = (saved or SAVED_DIR).expanduser()
    actions: list[ArchiveAction] = []
    if not cap.is_dir():
        return actions
    cache: dict[str, str] = {}
    for source in sorted(cap.iterdir(), key=lambda p: p.name.lower()):
        if not _is_sample_file(source):
            continue
        dest = store / source.name
        if dest.is_file():
            if _waves_same(source, dest, cache):
                actions.append(
                    ArchiveAction(
                        source=source,
                        dest=dest,
                        action="remove_duplicate",
                        note="same filename + mutagen/audio match",
                    )
                )
            else:
                actions.append(
                    ArchiveAction(
                        source=source,
                        dest=dest,
                        action="skip_conflict",
                        note="filename exists in Saved with different audio",
                    )
                )
            continue
        actions.append(
            ArchiveAction(
                source=source,
                dest=dest,
                action="move",
                note="new capture → Saved",
            )
        )
    return actions


def list_saved_samples(*, saved: Path | None = None) -> list[Path]:
    store = (saved or SAVED_DIR).expanduser()
    if not store.is_dir():
        return []
    rows = [p.resolve() for p in store.iterdir() if _is_sample_file(p)]
    rows.sort(key=lambda p: p.name.lower())
    return rows


def apply_archive(actions: list[ArchiveAction], *, saved: Path | None = None) -> tuple[int, int, int]:
    store = (saved or SAVED_DIR).expanduser()
    store.mkdir(parents=True, exist_ok=True)
    moved = removed = skipped = 0
    for item in actions:
        if item.action == "move":
            item.dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item.source), str(item.dest))
            moved += 1
        elif item.action == "remove_duplicate":
            item.source.unlink(missing_ok=True)
            removed += 1
        elif item.action in {"skip_conflict", "skip_exists"}:
            skipped += 1
    return moved, removed, skipped


def _track_refs(paths: list[Path], *, nml: Path, xml: Path) -> list[TrackRef]:
    nml_meta = nml_meta_by_path(nml)
    xml_meta = xml_meta_by_path(xml)
    refs: list[TrackRef] = []
    for path in paths:
        title = sample_title_from_path(path)
        ref = TrackRef(path=path, artist="Sampler", title=title, label=title)
        ref = enrich_ref_from_nml(ref, nml_meta.get(path.resolve()))
        ref = enrich_ref_from_xml(ref, xml_meta.get(path.resolve()))
        if ref.artist in {"", "Sampler"}:
            source = match_xml_source_for_capture(title, xml)
            if source:
                ref = enrich_ref_from_xml(ref, source)
                if source.artist:
                    ref.artist = source.artist
        refs.append(ref)
    return refs


def build_sync_plan(
    *,
    dest: str,
    paths: list[Path],
    nml: Path,
    xml: Path,
) -> SyncPlan:
    crate = CratePlaylist(name=SAMPLERS_PLAYLIST, tracks=_track_refs(paths, nml=nml, xml=xml))
    if dest == "xml":
        index = xml_path_index(xml)
    else:
        index = nml_path_index(nml)
    return SyncPlan(
        source="rekordbox-capture",
        dest=dest,
        dest_folder=SAMPLES_FOLDER,
        playlists=plan_membership([crate], index),
        ingest=True,
    )


def plan_sample_crate(
    *,
    capture: Path | None = None,
    saved: Path | None = None,
) -> SampleCratePlan:
    archive = plan_archive_moves(capture=capture, saved=saved)
    cap = (capture or CAPTURE_DIR).expanduser()
    capture_scanned = sum(1 for p in cap.iterdir() if _is_sample_file(p)) if cap.is_dir() else 0
    saved_paths = list_saved_samples(saved=saved)
    # After execute, moved files join the playlist; include pending moves too.
    pending = [a.dest for a in archive if a.action == "move"]
    playlist = sorted({str(p) for p in saved_paths + pending}, key=str.lower)
    return SampleCratePlan(
        capture_scanned=capture_scanned,
        saved_count=len(saved_paths),
        archive=archive,
        playlist_paths=playlist,
    )


def format_plan(plan: SampleCratePlan) -> str:
    moves = sum(1 for a in plan.archive if a.action == "move")
    dupes = sum(1 for a in plan.archive if a.action == "remove_duplicate")
    conflicts = sum(1 for a in plan.archive if a.action == "skip_conflict")
    lines = [
        f"rekordbox-sample-crate  capture {plan.capture_scanned}  "
        f"saved {plan.saved_count}  playlist {len(plan.playlist_paths)}",
        f"  archive  move {moves}  dedupe {dupes}  conflict {conflicts}",
        f"  crates  {SAMPLES_FOLDER}/{SAMPLERS_PLAYLIST}  → rekordbox.xml + Traktor NML",
    ]
    for item in plan.archive[:12]:
        loc = str(item.source).replace(str(Path.home()), "~")
        lines.append(f"    {item.action:16}  {item.source.name}  {loc}  ({item.note})")
    if len(plan.archive) > 12:
        lines.append(f"    … {len(plan.archive) - 12} more capture actions")
    return "\n".join(lines)


def write_report(plan: SampleCratePlan, extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "capture_dir": str(CAPTURE_DIR),
        "saved_dir": str(SAVED_DIR),
        "capture_scanned": plan.capture_scanned,
        "saved_count": plan.saved_count,
        "archive": [
            {
                "source": str(item.source),
                "dest": str(item.dest),
                "action": item.action,
                "note": item.note,
            }
            for item in plan.archive
        ],
        "playlist_paths": plan.playlist_paths,
        **(extra or {}),
    }
    dest = REPORTS / f"rekordbox-sample-crate-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def run(
    *,
    execute: bool,
    capture: Path | None = None,
    saved: Path | None = None,
    nml: Path | None = None,
    xml: Path | None = None,
) -> int:
    nml_path = nml or TRAKTOR_NML
    xml_path = xml or REKORDBOX_XML
    plan = plan_sample_crate(capture=capture, saved=saved)
    print(format_plan(plan), flush=True)
    report = write_report(plan, {"execute": execute})
    print(f"report {report}", flush=True)

    paths = [Path(p) for p in plan.playlist_paths]
    if paths:
        xml_plan = build_sync_plan(dest="xml", paths=paths, nml=nml_path, xml=xml_path)
        nml_plan = build_sync_plan(dest="nml", paths=paths, nml=nml_path, xml=xml_path)
        print(format_sync_plan(xml_plan), flush=True)
        print(format_sync_plan(nml_plan), flush=True)

    if not execute:
        print(
            "dry-run. pass --execute to move Capture → Saved, dedupe, "
            f"and rewrite {SAMPLES_FOLDER}/{SAMPLERS_PLAYLIST} in NML + xml.",
            flush=True,
        )
        return 0

    if rekordbox_is_running():
        print("Rekordbox is open. Quit it before --execute writes rekordbox.xml.", flush=True)
        return 2
    if traktor_is_running():
        print("Traktor is open. Quit it before --execute writes collection.nml.", flush=True)
        return 2

    moved, removed, skipped = apply_archive(plan.archive, saved=saved)
    paths = list_saved_samples(saved=saved)
    if paths:
        xml_plan = build_sync_plan(dest="xml", paths=paths, nml=nml_path, xml=xml_path)
        nml_plan = build_sync_plan(dest="nml", paths=paths, nml=nml_path, xml=xml_path)
        apply_xml(xml_plan, xml_path)
        apply_nml(nml_plan, nml_path)

    print(
        f"archive  moved {moved}  removed dupes {removed}  skipped {skipped}  "
        f"playlist {len(paths)} tracks",
        flush=True,
    )
    print(
        f"Reload rekordbox xml (<>). {SAMPLES_FOLDER}/{SAMPLERS_PLAYLIST} in NML + xml.",
        flush=True,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ix_crate rekordbox-sample-crate", description=__doc__)
    parser.add_argument("--capture", type=Path, default=CAPTURE_DIR)
    parser.add_argument("--saved", type=Path, default=SAVED_DIR)
    parser.add_argument("--nml", type=Path, default=TRAKTOR_NML)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(
        execute=args.execute,
        capture=args.capture,
        saved=args.saved,
        nml=args.nml,
        xml=args.xml,
    )


if __name__ == "__main__":
    raise SystemExit(main())
