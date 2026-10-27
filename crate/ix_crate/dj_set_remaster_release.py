"""Remaster DJ set recordings (Rekordbox / Traktor REC) for release listening.

Dry-run default: ffprobe + volumedetect + EBU R128 on the source file, then
print a proposed ffmpeg chain (high-pass, optional light denoise, compression,
two-pass loudnorm). ``--execute`` writes ``<stem>_release.wav`` beside the
input or under ``--dest-dir``. After the wet chain, ``--blend-dry`` (default
0.2) mixes unprocessed source with filtered audio; ``--peak-normalize-ceiling``
(default −1 dBFS) scales the result last. ``--compare-presets`` plans gentle /
standard / broadcast / clean WAVs for A/B in Audition. ``--preset standard_plus`` is
−16 LUFS like standard but denoise off and fixed 44.1 kHz PCM. ``--waveforms`` writes PNG
waveforms (and optional spectrograms); with ``--execute`` stacks a compare
sheet when multiple outputs exist.

Does not touch rekordbox.xml, NML, or Music.app. Requires Homebrew ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from ix_crate.paths import AUDIO_EXTS, REPORTS

TOOL_ID = "ix.crate.dj-set-remaster-release"
DEFAULT_LUFS = -16.0
DEFAULT_TRUE_PEAK = -1.0
DEFAULT_LRA = 11.0
DEFAULT_BLEND_DRY = 0.2
DEFAULT_PEAK_NORMALIZE_CEILING = -1.0
WAVEFORM_WIDTH = 2400
WAVEFORM_HEIGHT = 320
SPECTRUM_HEIGHT = 420
WEDGE_COLS = 4
WEDGE_COL_W = WAVEFORM_WIDTH // WEDGE_COLS
COMPARE_PRESET_NAMES = ("gentle", "standard", "broadcast", "clean")


class FFmpegError(RuntimeError):
    pass


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegError("ffmpeg not found (brew install ffmpeg)")
    return path


def _ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FFmpegError("ffprobe not found (comes with ffmpeg)")
    return path


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


@dataclass
class StreamInfo:
    codec: str
    sample_rate: int
    channels: int
    duration_s: float
    bit_rate: int | None


@dataclass
class LoudnessInfo:
    integrated_lufs: float | None
    true_peak_dbfs: float | None
    lra_lu: float | None


@dataclass
class VolumeInfo:
    mean_db: float | None
    max_db: float | None
    samples_at_0db: int | None


@dataclass
class Analysis:
    path: Path
    stream: StreamInfo
    volume: VolumeInfo
    loudness: LoudnessInfo

    @property
    def clipping_risk(self) -> str:
        tp = self.loudness.true_peak_dbfs
        at0 = self.volume.samples_at_0db or 0
        if tp is not None and tp > 0.0:
            return "high"
        if at0 > 1000 or (self.volume.max_db is not None and self.volume.max_db >= 0.0):
            return "high"
        if tp is not None and tp > -1.0:
            return "moderate"
        return "low"


@dataclass
class Preset:
    name: str
    denoise: str
    target_lufs: float
    true_peak: float
    lra: float
    ratio: float = 3.0
    threshold_db: float = -20.0
    output_sample_hz: int | None = None


PRESETS: dict[str, Preset] = {
    "gentle": Preset(
        "gentle", "light", -18.0, -1.5, 13.0, ratio=2.0, threshold_db=-22.0
    ),
    "standard": Preset("standard", "light", -16.0, -1.0, 11.0),
    "standard_plus": Preset(
        "standard_plus",
        "off",
        -16.0,
        -1.0,
        11.0,
        output_sample_hz=44100,
    ),
    "broadcast": Preset(
        "broadcast", "medium", -14.0, -1.0, 8.0, ratio=4.0, threshold_db=-18.0
    ),
    "clean": Preset(
        "clean", "off", -16.0, -1.0, 11.0, ratio=2.5, threshold_db=-24.0
    ),
}


@dataclass
class RemasterPlan:
    source: Path
    dest: Path
    denoise: str
    target_lufs: float
    true_peak: float
    lra: float
    filter_chain: str
    analysis: Analysis
    preset: str | None = None
    ratio: float = 3.0
    threshold_db: float = -20.0
    output_sample_hz: int | None = None
    blend_dry: float = 0.0
    peak_normalize_ceiling: float | None = None


def peak_gain_db(max_volume_db: float, ceiling_db: float) -> float:
    """Linear gain (dB) so max_volume_db lands on ceiling_db."""
    return ceiling_db - max_volume_db


def probe_stream(path: Path) -> StreamInfo:
    completed = _run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,duration,bit_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or f"ffprobe failed: {path}")
    payload = json.loads(completed.stdout or "{}")
    streams = payload.get("streams") or payload.get("stream") or []
    if not streams:
        raise FFmpegError(f"no audio stream: {path}")
    row = streams[0]
    try:
        duration = float(row.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    bit_rate: int | None
    try:
        bit_rate = int(row["bit_rate"]) if row.get("bit_rate") else None
    except (TypeError, ValueError):
        bit_rate = None
    return StreamInfo(
        codec=str(row.get("codec_name") or ""),
        sample_rate=int(row.get("sample_rate") or 0),
        channels=int(row.get("channels") or 0),
        duration_s=duration,
        bit_rate=bit_rate,
    )


def measure_volume(path: Path) -> VolumeInfo:
    completed = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
    )
    text = (completed.stderr or "") + (completed.stdout or "")
    mean = max_db = None
    at0: int | None = None
    for line in text.splitlines():
        if "mean_volume:" in line:
            try:
                mean = float(line.split("mean_volume:")[1].split("dB")[0].strip())
            except ValueError:
                pass
        if "max_volume:" in line:
            try:
                max_db = float(line.split("max_volume:")[1].split("dB")[0].strip())
            except ValueError:
                pass
        if "histogram_0db:" in line:
            try:
                at0 = int(line.split("histogram_0db:")[1].strip())
            except ValueError:
                pass
    return VolumeInfo(mean_db=mean, max_db=max_db, samples_at_0db=at0)


def measure_loudness(path: Path) -> LoudnessInfo:
    completed = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ]
    )
    text = (completed.stderr or "") + (completed.stdout or "")
    integrated = true_peak = lra = None
    for line in text.splitlines():
        m = re.search(r"\bI:\s*([-0-9.]+)\s*LUFS", line)
        if m:
            integrated = float(m.group(1))
        m = re.search(r"Peak:\s*([-0-9.]+)\s*dBFS", line)
        if m:
            true_peak = float(m.group(1))
        m = re.match(r"\s*LRA:\s*([-0-9.]+)\s*LU\s*$", line)
        if m:
            lra = float(m.group(1))
    return LoudnessInfo(
        integrated_lufs=integrated,
        true_peak_dbfs=true_peak,
        lra_lu=lra,
    )


def analyze(path: Path) -> Analysis:
    return Analysis(
        path=path,
        stream=probe_stream(path),
        volume=measure_volume(path),
        loudness=measure_loudness(path),
    )


def _denoise_filter(level: str) -> str:
    if level == "off":
        return ""
    if level == "medium":
        return "afftdn=nf=-20:nt=w,"
    return "afftdn=nf=-25:nt=w,"


def build_filter_chain(
    *,
    denoise: str,
    target_lufs: float,
    true_peak: float,
    lra: float,
    ratio: float = 3.0,
    threshold_db: float = -20.0,
) -> str:
    parts = [
        "highpass=f=25",
        _denoise_filter(denoise).rstrip(","),
        (
            "acompressor="
            f"threshold={threshold_db}dB:ratio={ratio}:attack=5:release=80:makeup=1"
        ),
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}",
    ]
    return ",".join(p for p in parts if p)


def default_dest(
    source: Path, dest_dir: Path | None, *, preset: str | None = None
) -> Path:
    base = dest_dir if dest_dir is not None else source.parent
    suffix = f"_release_{preset}" if preset else "_release"
    return base / f"{source.stem}{suffix}.wav"


def plan(
    source: Path,
    *,
    dest: Path | None,
    dest_dir: Path | None,
    denoise: str,
    target_lufs: float,
    true_peak: float,
    lra: float,
    ratio: float = 3.0,
    threshold_db: float = -20.0,
    preset: str | None = None,
    output_sample_hz: int | None = None,
    blend_dry: float = 0.0,
    peak_normalize_ceiling: float | None = None,
    analysis: Analysis | None = None,
) -> RemasterPlan:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    out = dest if dest is not None else default_dest(source, dest_dir, preset=preset)
    measured = analysis if analysis is not None else analyze(source)
    chain = build_filter_chain(
        denoise=denoise,
        target_lufs=target_lufs,
        true_peak=true_peak,
        lra=lra,
        ratio=ratio,
        threshold_db=threshold_db,
    )
    return RemasterPlan(
        source=source,
        dest=out,
        denoise=denoise,
        target_lufs=target_lufs,
        true_peak=true_peak,
        lra=lra,
        filter_chain=chain,
        analysis=measured,
        preset=preset,
        ratio=ratio,
        threshold_db=threshold_db,
        output_sample_hz=output_sample_hz,
        blend_dry=blend_dry,
        peak_normalize_ceiling=peak_normalize_ceiling,
    )


def plan_from_preset(
    source: Path,
    preset: Preset,
    *,
    dest: Path | None = None,
    dest_dir: Path | None,
    analysis: Analysis,
    blend_dry: float = 0.0,
    peak_normalize_ceiling: float | None = None,
) -> RemasterPlan:
    return plan(
        source,
        dest=dest,
        dest_dir=dest_dir,
        denoise=preset.denoise,
        target_lufs=preset.target_lufs,
        true_peak=preset.true_peak,
        lra=preset.lra,
        ratio=preset.ratio,
        threshold_db=preset.threshold_db,
        preset=preset.name,
        output_sample_hz=preset.output_sample_hz,
        blend_dry=blend_dry,
        peak_normalize_ceiling=peak_normalize_ceiling,
        analysis=analysis,
    )


def _parse_loudnorm_json(stderr: str) -> dict[str, float]:
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end <= start:
        raise FFmpegError("loudnorm pass 1 did not return JSON")
    payload = json.loads(stderr[start : end + 1])
    keys = (
        "input_i",
        "input_tp",
        "input_lra",
        "input_thresh",
        "target_offset",
    )
    out: dict[str, float] = {}
    for key in keys:
        if key not in payload:
            raise FFmpegError(f"loudnorm JSON missing {key}")
        out[key] = float(payload[key])
    return out


def _pcm_encode_args(output_sample_hz: int | None) -> list[str]:
    if output_sample_hz is not None:
        return ["-ar", str(output_sample_hz), "-c:a", "pcm_s16le"]
    return []


def _wet_loudnorm_filter(plan: RemasterPlan) -> str:
    base_chain = build_filter_chain(
        denoise=plan.denoise,
        target_lufs=plan.target_lufs,
        true_peak=plan.true_peak,
        lra=plan.lra,
        ratio=plan.ratio,
        threshold_db=plan.threshold_db,
    )
    measure_af = f"{base_chain}:print_format=json"
    pass1 = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-i",
            str(plan.source),
            "-af",
            measure_af,
            "-f",
            "null",
            "-",
        ]
    )
    if pass1.returncode != 0:
        raise FFmpegError(pass1.stderr.strip() or "loudnorm pass 1 failed")
    measured = _parse_loudnorm_json(pass1.stderr or "")
    return (
        f"{base_chain}:"
        f"measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:"
        "linear=true:print_format=summary"
    )


def _encode_wet_to_path(plan: RemasterPlan, out_path: Path) -> None:
    apply_af = _wet_loudnorm_filter(plan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-y",
        "-i",
        str(plan.source),
        "-af",
        apply_af,
        *_pcm_encode_args(plan.output_sample_hz),
        str(out_path),
    ]
    completed = _run(cmd)
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or "wet encode failed")


def _blend_dry_wet(
    source: Path,
    wet: Path,
    dest: Path,
    *,
    dry: float,
    output_sample_hz: int | None,
) -> None:
    wet_w = 1.0 - dry
    if output_sample_hz is not None:
        hz = output_sample_hz
        graph = (
            f"[0:a]aresample={hz}[dry];[1:a]aresample={hz}[wet];"
            f"[dry][wet]amix=inputs=2:duration=longest:normalize=0:"
            f"weights={dry} {wet_w}[out]"
        )
    else:
        graph = (
            f"[0:a][1:a]amix=inputs=2:duration=longest:normalize=0:"
            f"weights={dry} {wet_w}[out]"
        )
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-y",
        "-i",
        str(source),
        "-i",
        str(wet),
        "-filter_complex",
        graph,
        "-map",
        "[out]",
        *_pcm_encode_args(output_sample_hz),
        str(dest),
    ]
    completed = _run(cmd)
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or "dry/wet blend failed")


def _measure_max_volume_db(path: Path) -> float:
    completed = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
    )
    text = (completed.stderr or "") + (completed.stdout or "")
    match = re.search(r"max_volume:\s*([-\d.]+)\s*dB", text)
    if not match:
        raise FFmpegError(f"volumedetect max_volume missing: {path}")
    return float(match.group(1))


def _peak_normalize_file(
    in_path: Path,
    out_path: Path,
    ceiling_db: float,
    *,
    output_sample_hz: int | None,
) -> None:
    max_db = _measure_max_volume_db(in_path)
    gain_db = peak_gain_db(max_db, ceiling_db)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(),
        "-hide_banner",
        "-y",
        "-i",
        str(in_path),
        "-af",
        f"volume={gain_db}dB:precision=double",
    ]
    if output_sample_hz is not None:
        cmd.extend(["-ar", str(output_sample_hz), "-c:a", "pcm_s16le"])
    cmd.append(str(out_path))
    completed = _run(cmd)
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or "peak normalize failed")


def _encode_two_pass_loudnorm(plan: RemasterPlan) -> None:
    """Two-pass loudnorm wet chain, optional dry blend, optional peak ceiling."""
    plan.dest.parent.mkdir(parents=True, exist_ok=True)
    needs_post = plan.blend_dry > 0.0 or plan.peak_normalize_ceiling is not None
    wet_path = plan.dest
    temps: list[Path] = []
    if needs_post:
        wet_path = plan.dest.with_name(f".{plan.dest.stem}.wet.wav")
        temps.append(wet_path)
    _encode_wet_to_path(plan, wet_path)
    current = wet_path
    if plan.blend_dry > 0.0:
        blend_path = plan.dest.with_name(f".{plan.dest.stem}.blend.wav")
        temps.append(blend_path)
        _blend_dry_wet(
            plan.source,
            wet_path,
            blend_path,
            dry=plan.blend_dry,
            output_sample_hz=plan.output_sample_hz,
        )
        current = blend_path
    if plan.peak_normalize_ceiling is not None:
        _peak_normalize_file(
            current,
            plan.dest,
            plan.peak_normalize_ceiling,
            output_sample_hz=plan.output_sample_hz,
        )
    elif current != plan.dest:
        if plan.dest.is_file():
            plan.dest.unlink()
        current.replace(plan.dest)
    for tmp in temps:
        if tmp.is_file() and tmp != plan.dest:
            tmp.unlink(missing_ok=True)


@dataclass
class WaveformContext:
    """Shared linear peak envelope + spectrogram gain from the source analysis."""

    ref_peak_db: float | None
    spectrum_gain: float
    caption: str


def build_waveform_context(analysis: Analysis) -> WaveformContext:
    peak = analysis.volume.max_db
    # Anchor spectrogram gain to the source peak so all renders share one dB-ish scale.
    target_db = -8.0
    if peak is None:
        gain = 1.0
    else:
        gain = max(0.05, min(128.0, 10 ** ((target_db - peak) / 20)))
    cap = (
        "waveform showwavespic draw=full filter=peak (linear PCM, not per-file normalize); "
        f"spectrogram scale=lin gain={gain:.4f} ref_peak={peak} dBFS"
    )
    return WaveformContext(ref_peak_db=peak, spectrum_gain=gain, caption=cap)


def render_waveform_png(
    audio: Path, png: Path, *, label: str, ctx: WaveformContext | None = None
) -> None:
    del label  # encoded in the PNG file name
    del ctx
    png.parent.mkdir(parents=True, exist_ok=True)
    filter_complex = (
        f"showwavespic=s={WAVEFORM_WIDTH}x{WAVEFORM_HEIGHT}:colors=0x3b82f6|0xef4444:"
        "draw=full:filter=peak"
    )
    completed = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-y",
            "-i",
            str(audio),
            "-filter_complex",
            filter_complex,
            "-frames:v",
            "1",
            str(png),
        ]
    )
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or f"waveform failed: {audio}")


def render_spectrogram_png(
    audio: Path, png: Path, *, ctx: WaveformContext | None = None
) -> None:
    png.parent.mkdir(parents=True, exist_ok=True)
    gain = ctx.spectrum_gain if ctx is not None else 1.0
    completed = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-y",
            "-i",
            str(audio),
            "-lavfi",
            (
                f"showspectrumpic=s={WAVEFORM_WIDTH}x{SPECTRUM_HEIGHT}:color=intensity:"
                f"scale=lin:gain={gain}"
            ),
            "-frames:v",
            "1",
            str(png),
        ]
    )
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or f"spectrogram failed: {audio}")


def stack_pngs_vertical(pngs: list[Path], out: Path) -> None:
    if len(pngs) < 2:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    for png in pngs:
        inputs.extend(["-i", str(png)])
    stack = "".join(f"[{i}:v]" for i in range(len(pngs)))
    filter_complex = f"{stack}vstack=inputs={len(pngs)}[v]"
    completed = _run(
        [
            _ffmpeg(),
            "-hide_banner",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            str(out),
        ]
    )
    if completed.returncode != 0:
        raise FFmpegError(completed.stderr.strip() or "waveform stack failed")


def waveform_stem(source: Path, dest_dir: Path | None) -> Path:
    base = dest_dir if dest_dir is not None else source.parent
    return base / f"{source.stem}_waveforms"


def _magick_bin() -> str:
    for name in ("magick", "convert"):
        path = shutil.which(name)
        if path:
            return path
    raise FFmpegError("ImageMagick not found (brew install imagemagick)")


def _magick_run(args: list[str]) -> None:
    completed = subprocess.run([_magick_bin(), *args], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise FFmpegError(err or "ImageMagick failed")


def _resize_col(src: Path, dest: Path, *, height: int) -> None:
    _magick_run([str(src), "-resize", f"{WEDGE_COL_W}x{height}!", str(dest)])


def _magick_font_path() -> str:
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Verdana.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return "Arial"


def _magick_font_args() -> list[str]:
    return ["-font", _magick_font_path()]


def _label_png(src: Path, dest: Path, text: str) -> None:
    _magick_run(
        [
            str(src),
            *_magick_font_args(),
            "-gravity",
            "northwest",
            "-fill",
            "white",
            "-stroke",
            "black",
            "-strokewidth",
            "2",
            "-pointsize",
            "18",
            "-annotate",
            "+8+6",
            text,
            str(dest),
        ]
    )


def _diff_png(a: Path, b: Path, dest: Path, *, amplify: str = "2") -> None:
    _magick_run(
        [
            str(a),
            str(b),
            "-compose",
            "difference",
            "-composite",
            "-auto-level",
            "-evaluate",
            "multiply",
            amplify,
            str(dest),
        ]
    )


def _blend_png(a: Path, b: Path, dest: Path) -> None:
    _magick_run(
        [
            str(a),
            str(b),
            "-compose",
            "blend",
            "-define",
            "compose:args=50",
            "-composite",
            str(dest),
        ]
    )


def render_magick_delta_panel(
    out: Path,
    *,
    title: str,
    subtitle: str,
    source_wf: Path,
    variant_wf: Path,
    source_spec: Path | None,
    variant_spec: Path | None,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / f".{out.stem}_magick"
    tmp.mkdir(parents=True, exist_ok=True)
    src_r = tmp / "src_wf_r.png"
    var_r = tmp / "var_wf_r.png"
    _resize_col(source_wf, src_r, height=WAVEFORM_HEIGHT)
    _resize_col(variant_wf, var_r, height=WAVEFORM_HEIGHT)
    src_l = tmp / "src_wf.png"
    var_l = tmp / "var_wf.png"
    _label_png(src_r, src_l, "SOURCE (shared linear ref)")
    _label_png(var_r, var_l, "VARIANT")
    wf_diff = tmp / "wf_diff.png"
    _diff_png(src_r, var_r, wf_diff)
    _label_png(wf_diff, wf_diff, "WAVEFORM DIFF (norm x2)")
    wf_blend = tmp / "wf_blend.png"
    _blend_png(src_r, var_r, wf_blend)
    _label_png(wf_blend, wf_blend, "50% OVERLAP")
    wf_row = tmp / "wf_row.png"
    _magick_run([str(src_l), str(var_l), str(wf_blend), str(wf_diff), "+append", str(wf_row)])
    header = tmp / "header.png"
    _magick_run(
        [
            "-size",
            f"{WAVEFORM_WIDTH}x100",
            "xc:#121212",
            *_magick_font_args(),
            "-gravity",
            "center",
            "-fill",
            "white",
            "-pointsize",
            "22",
            "-annotate",
            "0",
            f"{title}\n{subtitle}",
            str(header),
        ]
    )
    stack_rows: list[str] = [str(header), str(wf_row)]
    if source_spec is not None and variant_spec is not None:
        src_sr = tmp / "src_spec_r.png"
        var_sr = tmp / "var_spec_r.png"
        _resize_col(source_spec, src_sr, height=SPECTRUM_HEIGHT)
        _resize_col(variant_spec, var_sr, height=SPECTRUM_HEIGHT)
        src_s = tmp / "src_spec.png"
        var_s = tmp / "var_spec.png"
        _label_png(src_sr, src_s, "SOURCE spectrum")
        _label_png(var_sr, var_s, "VARIANT spectrum")
        spec_diff = tmp / "spec_diff.png"
        _diff_png(src_sr, var_sr, spec_diff, amplify="3")
        _label_png(spec_diff, spec_diff, "SPECTRUM DIFF (norm x3)")
        spec_blend = tmp / "spec_blend.png"
        _blend_png(src_sr, var_sr, spec_blend)
        _label_png(spec_blend, spec_blend, "50% OVERLAP")
        spec_row = tmp / "spec_row.png"
        _magick_run(
            [str(src_s), str(var_s), str(spec_blend), str(spec_diff), "+append", str(spec_row)]
        )
        stack_rows.append(str(spec_row))
    _magick_run([*stack_rows, "-append", str(out)])
    for child in tmp.iterdir():
        child.unlink(missing_ok=True)
    tmp.rmdir()


def _preset_subtitle(item: RemasterPlan) -> str:
    return (
        f"denoise {item.denoise}  |  {item.target_lufs} LUFS  |  "
        f"TP {item.true_peak} dBFS  |  LRA {item.lra} LU  |  "
        f"compress {item.threshold_db} dB / {item.ratio}:1"
    )


def render_magick_wedges(
    wf_dir: Path,
    source: Path,
    renders: list[RemasterPlan],
    *,
    ctx: WaveformContext,
    with_spectrogram: bool,
) -> list[Path]:
    src_wf = wf_dir / f"{source.stem}_00_source.png"
    src_spec = wf_dir / f"{source.stem}_00_source_spectrum.png"
    outs: list[Path] = []
    for item in renders:
        if not item.preset:
            continue
        var_wf = wf_dir / f"{source.stem}_{item.preset}.png"
        if not var_wf.is_file():
            continue
        var_spec = wf_dir / f"{source.stem}_{item.preset}_spectrum.png"
        out = wf_dir / f"{source.stem}_wedge_{item.preset}.png"
        render_magick_delta_panel(
            out,
            title=f"WEDGE  {item.preset.upper()}  vs  source",
            subtitle=f"{_preset_subtitle(item)}\n{ctx.caption}",
            source_wf=src_wf,
            variant_wf=var_wf,
            source_spec=src_spec if with_spectrogram and src_spec.is_file() else None,
            variant_spec=var_spec if with_spectrogram and var_spec.is_file() else None,
        )
        outs.append(out)
        print(f"wedge  {out}", flush=True)
    if outs:
        sheet = wf_dir / f"{source.stem}_wedge_all.png"
        _magick_run([*(str(p) for p in outs), "-append", str(sheet)])
        print(f"wedge sheet  {sheet}", flush=True)
    return outs


def format_plan(plan: RemasterPlan) -> str:
    a = plan.analysis
    s = a.stream
    v = a.volume
    loud = a.loudness
    mins = int(s.duration_s // 60)
    secs = int(s.duration_s % 60)
    tag = f" [{plan.preset}]" if plan.preset else ""
    lines = [
        f"dj-set-remaster-release{tag}  {plan.source.name}",
        f"  stream  {s.codec}  {s.sample_rate} Hz  {s.channels} ch  {mins}:{secs:02d}",
        f"  volume  mean {v.mean_db} dB  max {v.max_db} dB  samples@0dB {v.samples_at_0db}",
        (
            f"  loudness  I {loud.integrated_lufs} LUFS  "
            f"true peak {loud.true_peak_dbfs} dBFS  LRA {loud.lra_lu} LU"
        ),
        f"  clip risk  {a.clipping_risk}",
        f"  target  {plan.target_lufs} LUFS  TP {plan.true_peak} dBFS  denoise {plan.denoise}",
    ]
    if plan.output_sample_hz is not None:
        lines.append(f"  encode  {plan.output_sample_hz} Hz  pcm_s16le")
    if plan.blend_dry > 0.0:
        wet = 1.0 - plan.blend_dry
        lines.append(
            f"  blend  dry {plan.blend_dry:.2f} / wet {wet:.2f} (orig / filtered)"
        )
    if plan.peak_normalize_ceiling is not None:
        lines.append(
            f"  peak normalize  max sample → {plan.peak_normalize_ceiling} dBFS (last)"
        )
    lines.extend(
        [
            f"  out  {plan.dest}",
            f"  filter  {plan.filter_chain}",
        ]
    )
    if a.clipping_risk == "high":
        lines.append(
            "  note  source is clipped or above 0 dBFS — remaster limits peaks; "
            "distortion already baked in cannot be removed"
        )
    return "\n".join(lines)


def write_report(plan: RemasterPlan, *, execute: bool) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    payload = {
        "tool": TOOL_ID,
        "execute": execute,
        "source": str(plan.source),
        "dest": str(plan.dest),
        "denoise": plan.denoise,
        "target_lufs": plan.target_lufs,
        "true_peak": plan.true_peak,
        "lra": plan.lra,
        "filter_chain": plan.filter_chain,
        "blend_dry": plan.blend_dry,
        "peak_normalize_ceiling": plan.peak_normalize_ceiling,
        "analysis": {
            "stream": asdict(plan.analysis.stream),
            "volume": asdict(plan.analysis.volume),
            "loudness": asdict(plan.analysis.loudness),
            "clipping_risk": plan.analysis.clipping_risk,
        },
    }
    dest = REPORTS / f"dj-set-remaster-release-{stamp}.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ix_crate dj-set-remaster-release",
        description=__doc__,
    )
    parser.add_argument(
        "--path",
        type=Path,
        required=True,
        help="Source WAV/AIFF/FLAC/etc. (DJ set recording).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Output file path (default: <stem>_release beside input).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Output directory when --dest is omitted.",
    )
    parser.add_argument(
        "--denoise",
        choices=("off", "light", "medium"),
        default="light",
        help="afftdn strength (default light).",
    )
    parser.add_argument(
        "--lufs",
        type=float,
        default=DEFAULT_LUFS,
        help=f"Integrated loudness target (default {DEFAULT_LUFS}).",
    )
    parser.add_argument(
        "--true-peak",
        type=float,
        default=DEFAULT_TRUE_PEAK,
        help=f"True peak ceiling dBFS (default {DEFAULT_TRUE_PEAK}).",
    )
    parser.add_argument(
        "--lra",
        type=float,
        default=DEFAULT_LRA,
        help=f"Loudness range target LU (default {DEFAULT_LRA}).",
    )
    parser.add_argument(
        "--compare-presets",
        action="store_true",
        help="Plan gentle, standard, broadcast, and clean WAVs (Audition A/B).",
    )
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default=None,
        help="Render one named preset (e.g. standard_plus).",
    )
    parser.add_argument(
        "--waveforms",
        action="store_true",
        help="Write PNG waveforms; with --execute stack source + renders.",
    )
    parser.add_argument(
        "--spectrogram",
        action="store_true",
        help="Also write spectrogram PNGs (with --waveforms).",
    )
    parser.add_argument(
        "--magick-deltas",
        action="store_true",
        help="ImageMagick wedge panels (source vs variant diff/overlap). "
        "Default with --compare-presets --waveforms --execute.",
    )
    parser.add_argument(
        "--no-magick-deltas",
        action="store_true",
        help="Skip ImageMagick wedge panels.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--blend-dry",
        type=float,
        default=DEFAULT_BLEND_DRY,
        metavar="RATIO",
        help=(
            "Unprocessed source mix 0..1; wet is (1−dry). "
            f"Default {DEFAULT_BLEND_DRY} (20%% orig / 80%% filtered). "
            "Use 0 for filtered only."
        ),
    )
    parser.add_argument(
        "--peak-normalize-ceiling",
        type=float,
        default=DEFAULT_PEAK_NORMALIZE_CEILING,
        metavar="DBFS",
        help=(
            "Final step: scale so the file peak hits this dBFS "
            f"(default {DEFAULT_PEAK_NORMALIZE_CEILING})."
        ),
    )
    parser.add_argument(
        "--no-peak-normalize",
        action="store_true",
        help="Skip final peak normalize (loudnorm TP limit only).",
    )
    return parser


def _encoding_options(args: argparse.Namespace) -> tuple[float, float | None]:
    blend = float(args.blend_dry)
    if not 0.0 <= blend <= 1.0:
        raise ValueError("--blend-dry must be between 0 and 1")
    peak = None if args.no_peak_normalize else float(args.peak_normalize_ceiling)
    return blend, peak


def _run_waveforms(
    source: Path,
    *,
    dest_dir: Path | None,
    renders: list[RemasterPlan],
    spectrogram: bool,
    ctx: WaveformContext,
) -> Path:
    wf_dir = waveform_stem(source, dest_dir)
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "SCALE.txt").write_text(ctx.caption + "\n", encoding="utf-8")
    stack: list[Path] = []
    src_png = wf_dir / f"{source.stem}_00_source.png"
    render_waveform_png(source, src_png, label="source", ctx=ctx)
    stack.append(src_png)
    print(f"waveform  {src_png}", flush=True)
    if spectrogram:
        spec = wf_dir / f"{source.stem}_00_source_spectrum.png"
        render_spectrogram_png(source, spec, ctx=ctx)
        print(f"spectrogram  {spec}", flush=True)
    for item in renders:
        label = item.preset or item.dest.stem
        png = wf_dir / f"{source.stem}_{label}.png"
        if item.dest.is_file():
            render_waveform_png(item.dest, png, label=label, ctx=ctx)
            stack.append(png)
            print(f"waveform  {png}", flush=True)
            if spectrogram:
                spec = wf_dir / f"{source.stem}_{label}_spectrum.png"
                render_spectrogram_png(item.dest, spec, ctx=ctx)
                print(f"spectrogram  {spec}", flush=True)
    compare = wf_dir / f"{source.stem}_waveform_compare.png"
    if len(stack) > 1:
        stack_pngs_vertical(stack, compare)
        print(f"compare  {compare}", flush=True)
    return wf_dir


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.compare_presets and args.dest is not None:
        print("use --dest-dir with --compare-presets, not --dest", flush=True)
        return 2
    if args.compare_presets and args.preset is not None:
        print("use --compare-presets or --preset, not both", flush=True)
        return 2
    source = args.path.expanduser().resolve()
    try:
        blend_dry, peak_ceiling = _encoding_options(args)
        if args.compare_presets:
            analysis = analyze(source)
            plans = [
                plan_from_preset(
                    source,
                    PRESETS[name],
                    dest_dir=args.dest_dir,
                    analysis=analysis,
                    blend_dry=blend_dry,
                    peak_normalize_ceiling=peak_ceiling,
                )
                for name in COMPARE_PRESET_NAMES
            ]
        elif args.preset is not None:
            analysis = analyze(source)
            plans = [
                plan_from_preset(
                    source,
                    PRESETS[args.preset],
                    dest_dir=args.dest_dir,
                    dest=args.dest,
                    analysis=analysis,
                    blend_dry=blend_dry,
                    peak_normalize_ceiling=peak_ceiling,
                )
            ]
        else:
            plans = [
                plan(
                    source,
                    dest=args.dest,
                    dest_dir=args.dest_dir,
                    denoise=args.denoise,
                    target_lufs=args.lufs,
                    true_peak=args.true_peak,
                    lra=args.lra,
                    blend_dry=blend_dry,
                    peak_normalize_ceiling=peak_ceiling,
                )
            ]
    except (FileNotFoundError, FFmpegError, ValueError) as exc:
        print(exc, flush=True)
        return 2
    for item in plans:
        print(format_plan(item), flush=True)
        print("", flush=True)
    report = write_report(plans[0], execute=bool(args.execute))
    print(f"report {report}", flush=True)
    wf_ctx = build_waveform_context(plans[0].analysis)
    want_magick = args.magick_deltas or (
        args.compare_presets and args.waveforms and args.execute and not args.no_magick_deltas
    )
    if args.waveforms and not args.execute:
        try:
            _run_waveforms(
                source,
                dest_dir=args.dest_dir,
                renders=[],
                spectrogram=bool(args.spectrogram),
                ctx=wf_ctx,
            )
        except FFmpegError as exc:
            print(exc, flush=True)
            return 2
    if not args.execute:
        print(
            "dry-run. pass --execute to write WAV(s) (two-pass loudnorm). "
            "Audition still wins for listening; waveforms are level/shape hints.",
            flush=True,
        )
        return 0
    try:
        for item in plans:
            _encode_two_pass_loudnorm(item)
            print(f"wrote {item.dest}", flush=True)
    except FFmpegError as exc:
        print(exc, flush=True)
        return 2
    if args.waveforms:
        try:
            wf_dir = _run_waveforms(
                source,
                dest_dir=args.dest_dir,
                renders=plans,
                spectrogram=bool(args.spectrogram),
                ctx=wf_ctx,
            )
            print(f"waveforms  {wf_dir}", flush=True)
            if want_magick and args.compare_presets:
                render_magick_wedges(
                    wf_dir,
                    source,
                    plans,
                    ctx=wf_ctx,
                    with_spectrogram=bool(args.spectrogram),
                )
        except FFmpegError as exc:
            print(exc, flush=True)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
