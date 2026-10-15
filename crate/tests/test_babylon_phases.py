import unittest

from ix_crate.batch_progress import build_babylon_phases


class BabylonPhaseTests(unittest.TestCase):
    def test_default_zero_stems_includes_crater(self) -> None:
        phases = build_babylon_phases(
            skip_hygiene=False,
            skip_crater=False,
            skip_stemit=False,
            budget=0,
            stemit_batches=None,
            follow=False,
        )
        names = [p.name for p in phases]
        self.assertIn("music-genre", names)
        self.assertIn("crater", names)
        self.assertNotIn("stemit-chain-1", names)
        self.assertEqual(names.index("quit-decks"), names.index("music-genre") + 1)

    def test_quit_decks_before_stemit_when_budget(self) -> None:
        phases = build_babylon_phases(
            skip_hygiene=False,
            skip_crater=False,
            skip_stemit=False,
            budget=150,
            stemit_batches=None,
            follow=False,
        )
        names = [p.name for p in phases]
        self.assertLess(names.index("quit-decks"), names.index("stemit-chain-1"))

    def test_stemit_batches(self) -> None:
        phases = build_babylon_phases(
            skip_hygiene=True,
            skip_crater=False,
            skip_stemit=False,
            budget=0,
            stemit_batches=[50, 100],
            follow=False,
        )
        names = [p.name for p in phases]
        self.assertEqual(names[:3], ["quit-decks", "stemit-chain-1", "stemit-chain-2"])
        self.assertTrue(phases[1].allow_fail)
