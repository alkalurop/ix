"""Drop rekordbox.xml rows Rekordbox can never import.

Rekordbox re-reads every COLLECTION TRACK on each ``<>`` reload and writes
``~/Documents/rekordbox/Import Log - <date>.txt`` for the ones it rejects.
Stale rows repeat that dialog forever. This removes:

* ``.m4p`` — Apple DRM purchases; Rekordbox cannot decode them.
* files no longer on disk (moved, renamed, culled).

Rows under ``/Volumes`` stay: a drive that is unplugged is not a dead file.
Playlist ``TRACK Key`` refs to dropped rows go with them. Dry-run default.
Quit Rekordbox before ``--execute``.
"""

from __future__ import annotations

import argparse
import shutil
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from ix_crate.stems_playlists import REKORDBOX_XML, rekordbox_is_running
from ix_crate.xml_io import write_tree

NEVER_IMPORTS = {".m4p"}


@dataclass
class PrunePlan:
    scanned: int = 0
    dead: dict[str, tuple[str, str]] = field(default_factory=dict)

    def reasons(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for reason, _path in self.dead.values():
            counts[reason] = counts.get(reason, 0) + 1
        return counts


def location_path(raw: str) -> str:
    return unquote((raw or "").replace("file://localhost", "").replace("file://", ""))


def _on_disk(path: str) -> bool:
    for form in (path, unicodedata.normalize("NFC", path), unicodedata.normalize("NFD", path)):
        try:
            if Path(form).is_file():
                return True
        except OSError:
            continue
    return False


def dead_reason(path: str) -> str | None:
    if not path or path.startswith("/Volumes/"):
        return None
    if Path(path).suffix.lower() in NEVER_IMPORTS:
        return "m4p"
    if not _on_disk(path):
        return "missing"
    return None


def plan_prune(root: ET.Element) -> PrunePlan:
    plan = PrunePlan()
    collection = root.find("COLLECTION")
    if collection is None:
        return plan
    for track in collection.findall("TRACK"):
        plan.scanned += 1
        path = location_path(track.get("Location") or "")
        reason = dead_reason(path)
        tid = track.get("TrackID") or ""
        if reason and tid:
            plan.dead[tid] = (reason, path)
    return plan


def apply_prune(root: ET.Element, plan: PrunePlan) -> int:
    if not plan.dead:
        return 0
    collection = root.find("COLLECTION")
    removed = 0
    if collection is not None:
        for track in list(collection.findall("TRACK")):
            if (track.get("TrackID") or "") in plan.dead:
                collection.remove(track)
                removed += 1
        collection.set("Entries", str(len(collection.findall("TRACK"))))
    playlists = root.find("PLAYLISTS")
    if playlists is not None:
        for node in playlists.iter("NODE"):
            if node.get("Type") != "1" or node.get("KeyType", "0") != "0":
                continue
            refs = node.findall("TRACK")
            kept = 0
            for ref in refs:
                if (ref.get("Key") or "") in plan.dead:
                    node.remove(ref)
                else:
                    kept += 1
            if len(refs) != kept:
                node.set("Entries", str(kept))
    return removed


def prune_xml(xml: Path = REKORDBOX_XML, *, execute: bool = False) -> PrunePlan:
    tree = ET.parse(xml)
    plan = plan_prune(tree.getroot())
    if execute and plan.dead:
        apply_prune(tree.getroot(), plan)
        shutil.copy2(xml, xml.with_suffix(xml.suffix + ".prune.bak"))
        write_tree(tree, xml)
    return plan


def format_plan(plan: PrunePlan, *, verbose: bool = False) -> str:
    counts = ", ".join(f"{k}={v}" for k, v in sorted(plan.reasons().items())) or "none"
    lines = [f"rekordbox.xml prune: {len(plan.dead)} of {plan.scanned} TRACK rows ({counts})"]
    if verbose:
        lines += [f"  {reason:<8} {path}" for reason, path in plan.dead.values()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ix_crate xml-prune", description=__doc__)
    parser.add_argument("--xml", type=Path, default=REKORDBOX_XML)
    parser.add_argument("--verbose", action="store_true", help="List every dropped row.")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.execute and rekordbox_is_running():
        print("Rekordbox is open. Quit it before --execute writes rekordbox.xml.", flush=True)
        return 2
    plan = prune_xml(args.xml, execute=args.execute)
    print(format_plan(plan, verbose=args.verbose), flush=True)
    if not args.execute:
        print("dry-run. pass --execute to drop these rows.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
