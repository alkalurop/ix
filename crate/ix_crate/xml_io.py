"""Replace library XML in one step.

``ElementTree.write`` onto the live path truncates the file first. A quit
or reboot in the middle leaves ``rekordbox.xml`` or ``collection.nml``
unreadable, and the next CRATER stops. Write a sibling temp file, then
``os.replace`` so readers keep the previous complete document.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path


def write_tree(tree: ET.ElementTree, path: Path) -> None:
    dest = Path(path)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        tree.write(tmp, encoding="UTF-8", xml_declaration=True)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
