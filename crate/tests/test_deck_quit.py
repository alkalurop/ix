"""Deck quit patterns (Traktor Pro 4 vs legacy Traktor.app)."""

import unittest

from ix_crate.deck_quit import DECK_PROCESS_PATTERNS, process_pattern_matches_traktor_pro


class DeckQuitPatternsTest(unittest.TestCase):
    def test_traktor_pro_4_cmdline(self) -> None:
        cmd = (
            "/Applications/Native Instruments/Traktor Pro 4/"
            "Traktor Pro 4.app/Contents/MacOS/Traktor Pro 4"
        )
        self.assertTrue(process_pattern_matches_traktor_pro(cmd))

    def test_legacy_traktor_cmdline(self) -> None:
        cmd = "/Applications/Traktor.app/Contents/MacOS/Traktor"
        self.assertFalse(process_pattern_matches_traktor_pro(cmd))
        self.assertIn(r"Traktor\.app/Contents/MacOS", DECK_PROCESS_PATTERNS)


if __name__ == "__main__":
    unittest.main()
