"""Traktor remix sets + deck samples → Rekordbox / NML under ``SAMPLES/Remixes/``.

Every remix set in Traktor NML (factory ContentImport and user sets — all
``ALBUM`` / folder names ending in ``Traktor Remix Set``) gets its own
playlist: ``SAMPLES/Remixes/<Set Name>/``.

Flat captures under ``~/Music/Traktor/Samples`` → ``SAMPLES/Remixes/Deck Captures``.

Ingest copies artist, title, album, BPM, key, and genre from Traktor NML into
rekordbox.xml and back from xml into NML when the other side is missing a row.

Dry-run default. Quit Rekordbox before xml. Quit Traktor before NML.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
import xml.etree.ElementTree as ET
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
    NmlMeta,
    XmlMeta,
    enrich_ref_from_nml,
    enrich_ref_from_xml,
    nml_meta_by_path,
    xml_meta_by_path,
)
from ix_crate.paths import AUDIO_EXTS, REPORTS
from ix_crate.stems_playlists import (
    REKORDBOX_XML,
    TRAKTOR_NML,
    _loc_to_path,
    rekordbox_is_running,
)
from ix_crate.traktor_nml import traktor_is_running

TRAKTOR_SAMPLES = Path.home() / "Music" / "Traktor" / "Samples"
TRAKTOR_CONTENT = Path.home() / "Music" / "Traktor" / "ContentImport"
REMIX_SET_SUFFIX = " - Traktor Remix Set"
SAMPLES_FOLDER = "SAMPLES"
REMIXES_SUBFOLDER = "Remixes"
DECK_CAPTURES_PLAYLIST = "Deck Captures"
TOOL_ID = "ix.crate.traktor-remix-crate"


@dataclass
class RemixCratePlan:
    remix_sets: dict[str, list[str]] = field(default_factory=dict)
    flat_samples: list[str] = field(default_factory=list)


def _is_audio(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTS and not path.name.startswith(".")


def remix_playlist_name(album_title: str) -> str:
    title = (album_title or "").strip()
    if title.endswith(REMIX_SET_SUFFIX):
        return title[: -len(REMIX_SET_SUFFIX)].strip() or title
    if title.endswith(" Traktor Remix Set"):
        return title[: -len(" Traktor Remix Set")].strip() or title
    return title or "Untitled Remix Set"


def _entry_path(entry: ET.Element) -> Path | None:
    location = entry.find("LOCATION")
    if location is None:
        return None
    directory = location.get("DIR") or ""
    file_attr = location.get("FILE") or ""
    try:
        path = _loc_to_path(directory, file_attr)
    except OSError:
        return None
    if not path.is_file():
        return None
    return path.resolve()


def _entry_album(entry: ET.Element) -> str:
    album = entry.find("ALBUM")
    if album is None:
        return ""
    return (album.get("TITLE") or "").strip()


def index_remix_sets_from_nml(nml: Path) -> dict[str, list[Path]]:
    """All remix sets in NML (factory + user). Set name → sample paths."""
    if not nml.is_file():
        return {}
    root = ET.parse(nml).getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        return {}
    grouped: dict[str, list[Path]] = defaultdict(list)
    content_root = TRAKTOR_CONTENT.expanduser().resolve()
    for entry in collection.findall("ENTRY"):
        path = _entry_path(entry)
        if path is None:
            continue
        album = _entry_album(entry)
        if REMIX_SET_SUFFIX in album or album.endswith(" Traktor Remix Set"):
            name = remix_playlist_name(album)
            grouped[name].append(path)
            continue
        try:
            rel = path.relative_to(content_root)
        except ValueError:
            continue
        if rel.parts and "traktor remix set" in rel.parts[0].lower():
            name = remix_playlist_name(rel.parts[0])
            grouped[name].append(path)
    for name in grouped:
        grouped[name] = sorted(set(grouped[name]), key=lambda p: p.name.lower())
    return dict(grouped)


def list_flat_traktor_samples(*, samples_dir: Path | None = None) -> list[Path]:
    root = (samples_dir or TRAKTOR_SAMPLES).expanduser()
    if not root.is_dir():
        return []
    rows = [p.resolve() for p in root.iterdir() if _is_audio(p)]
    rows.sort(key=lambda p: p.name.lower())
    return rows


def _ref_for_path(
    path: Path,
    *,
    nml_index: dict[Path, NmlMeta],
    xml_index: dict[Path, XmlMeta],
    default_artist: str,
) -> TrackRef:
    ref = TrackRef(path=path, artist=default_artist, title=path.stem, label=path.stem)
    ref = enrich_ref_from_nml(ref, nml_index.get(path.resolve()))
    ref = enrich_ref_from_xml(ref, xml_index.get(path.resolve()))
    if not ref.title:
        ref.title = path.stem
    return ref


def _crates_from_plan(
    remix_sets: dict[str, list[Path]],
    flat_samples: list[Path],
    *,
    nml: Path,
    xml: Path,
) -> list[CratePlaylist]:
    nml_meta = nml_meta_by_path(nml)
    xml_meta = xml_meta_by_path(xml)
    crates: list[CratePlaylist] = []
    for name, paths in sorted(remix_sets.items(), key=lambda item: item[0].casefold()):
        if not paths:
            continue
        tracks = [
            _ref_for_path(
                p,
                nml_index=nml_meta,
                xml_index=xml_meta,
                default_artist="Traktor Remix",
            )
            for p in paths
        ]
        crates.append(
            CratePlaylist(name=name, folder=(REMIXES_SUBFOLDER,), tracks=tracks)
        )
    if flat_samples:
        tracks = [
            _ref_for_path(
                p,
                nml_index=nml_meta,
                xml_index=xml_meta,
                default_artist="Traktor Sample",
            )
            for p in flat_samples
        ]
        crates.append(
            CratePlaylist(
                name=DECK_CAPTURES_PLAYLIST,
                folder=(REMIXES_SUBFOLDER,),
                tracks=tracks,
            )
        )
    return crates


def plan_remix_crate(*, nml: Path | None = None, samples_dir: Path | None = None) -> RemixCratePlan:
    nml_path = nml or TRAKTOR_NML
    sets = index_remix_sets_from_nml(nml_path)
    flat = list_flat_traktor_samples(samples_dir=samples_dir)
    return RemixCratePlan(
        remix_sets={name: [str(p) for p in paths] for name, paths in sets.items()},
        flat_samples=[str(p) for p in flat],
    )


def format_plan(plan: RemixCratePlan) -> str:
    set_tracks = sum(len(v) for v in plan.remix_sets.values())
    lines = [
        f"traktor-remix-crate  sets {len(plan.remix_sets)}  cells {set_tracks}  "
        f"deck captures {len(plan.flat_samples)}",
        f"  folder  {SAMPLES_FOLDER}/{REMIXES_SUBFOLDER}/<set name>  (all NML remix sets)",
        f"  folder  {SAMPLES_FOLDER}/{REMIXES_SUBFOLDER}/{DECK_CAPTURES_PLAYLIST}",
    ]
    for name in sorted(plan.remix_sets, key=str.casefold)[:10]:
        lines.append(f"    {name}  {len(plan.remix_sets[name])}")
    if len(plan.remix_sets) > 10:
        lines.append(f"    … {len(plan.remix_sets) - 10} more sets")
    return "\n".join(lines)


def write_report(plan: RemixCratePlan, extra: dict | None = None) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "samples_folder": SAMPLES_FOLDER,
        "remixes_subfolder": REMIXES_SUBFOLDER,
        "remix_sets": plan.remix_sets,
        "flat_samples": plan.flat_samples,
        **(extra or {}),
    }
    dest = REPORTS / f"traktor-remix-crate-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def _sync_plan(
    *,
    dest: str,
    crates: list[CratePlaylist],
    nml: Path,
    xml: Path,
) -> SyncPlan | None:
    if not crates:
        return None
    index = xml_path_index(xml) if dest == "xml" else nml_path_index(nml)
    return SyncPlan(
        source="traktor-remix",
        dest=dest,
        dest_folder=SAMPLES_FOLDER,
        playlists=plan_membership(crates, index),
        ingest=True,
    )


def run(
    *,
    execute: bool,
    nml: Path | None = None,
    xml: Path | None = None,
    samples_dir: Path | None = None,
) -> int:
    nml_path = nml or TRAKTOR_NML
    xml_path = xml or REKORDBOX_XML
    plan = plan_remix_crate(nml=nml_path, samples_dir=samples_dir)
    print(format_plan(plan), flush=True)
    report = write_report(plan, {"execute": execute})
    print(f"report {report}", flush=True)

    sets = {name: [Path(p) for p in paths] for name, paths in plan.remix_sets.items()}
    flat = [Path(p) for p in plan.flat_samples]
    crates = _crates_from_plan(sets, flat, nml=nml_path, xml=xml_path)

    xml_plan = _sync_plan(dest="xml", crates=crates, nml=nml_path, xml=xml_path)
    nml_plan = _sync_plan(dest="nml", crates=crates, nml=nml_path, xml=xml_path)
    if xml_plan:
        print(format_sync_plan(xml_plan), flush=True)
    if nml_plan:
        print(format_sync_plan(nml_plan), flush=True)

    if not execute:
        print(
            "dry-run. pass --execute to rewrite SAMPLES/Remixes/* in NML + xml "
            "with Traktor/xml metadata on ingest.",
            flush=True,
        )
        return 0

    if rekordbox_is_running():
        print("Rekordbox is open. Quit it before --execute writes rekordbox.xml.", flush=True)
        return 2
    if traktor_is_running():
        print("Traktor is open. Quit it before --execute writes collection.nml.", flush=True)
        return 2

    if xml_plan:
        apply_xml(xml_plan, xml_path)
    if nml_plan:
        apply_nml(nml_plan, nml_path)

    print(
        f"wrote {len(crates)} playlist(s) under {SAMPLES_FOLDER}/{REMIXES_SUBFOLDER}/ "
        f"({len(sets)} remix sets + deck captures).",
        flush=True,
    )
    print("Reload rekordbox xml (<>).", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ix_crate traktor-remix-crate", description=__doc__)
    parser.add_argument("--nml", type=Path, default=TRAKTOR_NML)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument("--samples-dir", type=Path, default=TRAKTOR_SAMPLES)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(
        execute=args.execute,
        nml=args.nml,
        xml=args.xml,
        samples_dir=args.samples_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
