from __future__ import annotations

import unittest
from pathlib import Path

from ix_crate.dj_set_remaster_release import (
    Analysis,
    LoudnessInfo,
    PRESETS,
    StreamInfo,
    VolumeInfo,
    _parse_loudnorm_json,
    build_filter_chain,
    format_plan,
    peak_gain_db,
    RemasterPlan,
)


class DjSetRemasterReleaseTest(unittest.TestCase):
    def test_clipping_risk_high_on_true_peak_over_zero(self) -> None:
        analysis = Analysis(
            path=__file__,  # type: ignore[arg-type]
            stream=StreamInfo("pcm_s16le", 44100, 2, 60.0, None),
            volume=VolumeInfo(-12.0, 0.0, 100),
            loudness=LoudnessInfo(-10.0, 1.5, 6.0),
        )
        self.assertEqual(analysis.clipping_risk, "high")

    def test_peak_gain_db_scales_max_to_ceiling(self) -> None:
        self.assertAlmostEqual(peak_gain_db(-3.0, -1.0), 2.0)
        self.assertAlmostEqual(peak_gain_db(0.0, -1.0), -1.0)

    def test_standard_plus_matches_standard_lufs_without_denoise(self) -> None:
        sp = PRESETS["standard_plus"]
        st = PRESETS["standard"]
        self.assertEqual(sp.denoise, "off")
        self.assertEqual(sp.target_lufs, st.target_lufs)
        self.assertEqual(sp.output_sample_hz, 44100)

    def test_build_filter_chain_respects_denoise_off(self) -> None:
        chain = build_filter_chain(
            denoise="off", target_lufs=-16, true_peak=-1.0, lra=11.0
        )
        self.assertNotIn("afftdn", chain)
        self.assertIn("loudnorm=I=-16", chain)

    def test_parse_loudnorm_json(self) -> None:
        stderr = 'foo\n{"input_i": "-10.0", "input_tp": "1.0", "input_lra": "6.0", "input_thresh": "-20.0", "target_offset": "6.0"}\n'
        parsed = _parse_loudnorm_json(stderr)
        self.assertEqual(parsed["input_i"], -10.0)
        self.assertEqual(parsed["target_offset"], 6.0)

    def test_format_plan_includes_dest(self) -> None:
        src = Path("/tmp/Never Forget REC.wav")
        plan = RemasterPlan(
            source=src,
            dest=src.with_name("Never Forget REC_release.wav"),
            denoise="light",
            target_lufs=-16.0,
            true_peak=-1.0,
            lra=11.0,
            filter_chain="highpass=f=25",
            analysis=Analysis(
                path=__file__,  # type: ignore[arg-type]
                stream=StreamInfo("pcm_s16le", 44100, 2, 90.0, None),
                volume=VolumeInfo(-11.0, 0.0, 5000),
                loudness=LoudnessInfo(-10.0, 1.9, 6.1),
            ),
        )
        text = format_plan(plan)
        self.assertIn("clip risk  high", text)
        self.assertIn("filter  highpass", text)


if __name__ == "__main__":
    unittest.main()
