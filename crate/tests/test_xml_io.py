from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory

from ix_crate.crater import require_xml
from ix_crate.xml_io import write_tree


class XmlIoTest(unittest.TestCase):
    def test_write_tree_replaces_and_leaves_no_temp(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rekordbox.xml"
            path.write_text("<old/>", encoding="utf-8")
            tree = ET.ElementTree(ET.fromstring("<DJ_PLAYLISTS/>"))
            write_tree(tree, path)
            self.assertIn("DJ_PLAYLISTS", path.read_text(encoding="utf-8"))
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_failed_write_keeps_the_previous_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rekordbox.xml"
            path.write_text("<old/>", encoding="utf-8")

            class Boom:
                def write(self, dest, *args, **kwargs) -> None:
                    Path(dest).write_text("partial", encoding="utf-8")
                    raise OSError("killed")

            with self.assertRaises(OSError):
                write_tree(Boom(), path)  # type: ignore[arg-type]
            self.assertEqual(path.read_text(encoding="utf-8"), "<old/>")
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_truncated_xml_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rekordbox.xml"
            path.write_text('<DJ_PLAYLISTS><TRACK Name="', encoding="utf-8")
            self.assertEqual(require_xml(path), 2)
            self.assertTrue(path.read_text(encoding="utf-8").startswith("<DJ_PLAYLISTS>"))
