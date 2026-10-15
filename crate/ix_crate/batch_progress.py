"""RunLogger phases for long crate shell batches (BABYLON, hygiene)."""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ix_crate.stems_path import ensure_stems_path

SCAN_PROGRESS = re.compile(r"(?:scan|library) (\d+)/(\d+)", re.I)
STEM_OK_PROGRESS = re.compile(r"^ok (\d+)/(\d+)\s", re.I)
DUMP_PROGRESS = re.compile(r"^dump (\d+)/(\d+)\s", re.I)
TOOL_ID = "ix.crate.babylon"
HUD_TITLE = "BABYLON"


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    argv: list[str]
    allow_fail: bool = False


def append_phase(
    logger: Any,
    name: str,
    *,
    wall_s: float,
    result: str,
    error: str | None = None,
) -> None:
    ensure_stems_path()
    from py.utils.runlog import utc_now

    stamp = utc_now()
    logger.tracks.append(
        {
            "source": f"phase:{name}",
            "name": name,
            "started_at": stamp,
            "ended_at": stamp,
            "wall_s": round(wall_s, 4),
            "audio_duration_s": None,
            "sec_per_audio_minute": None,
            "result": result,
            "vocals": "n/a",
            "instrumental": "n/a",
            "has_audio": True,
            "no_audio": False,
            "handling": [],
            "error": error,
            "mutagen": {},
            "jobs": [
                {
                    "action": "phase",
                    "dest": name,
                    "role": "",
                    "reason": name,
                    "result": result,
                    "error": error,
                }
            ],
            "resources": {},
            "resource_samples": [],
        }
    )


def _parse_progress_line(line: str, phase: str, panel: Any | None) -> None:
    if panel is None:
        return
    stripped = line.strip()
    for pattern, action in (
        (SCAN_PROGRESS, "scan"),
        (STEM_OK_PROGRESS, "stem"),
        (DUMP_PROGRESS, "dump"),
    ):
        m = pattern.search(stripped)
        if m:
            done, total = int(m.group(1)), max(1, int(m.group(2)))
            panel.set_job(done, total, phase, action)
            return
    if stripped.startswith("CRATER "):
        panel.set_job(0, 1, stripped, "crater")


def _phase_argv(spec: PhaseSpec, panel: Any | None) -> list[str]:
    argv = list(spec.argv)
    if panel is not None and spec.name.startswith("stemit-chain") and "--no-gui" not in argv:
        argv.append("--no-gui")
    return argv


def run_phase(
    logger: Any,
    panel: Any | None,
    index: int,
    total_phases: int,
    spec: PhaseSpec,
) -> int:
    if panel is not None:
        panel.set_job(index, total_phases, spec.name, "start")
    print(f"\n=== phase {index}/{total_phases}: {spec.name} ===", flush=True)
    t0 = time.perf_counter()
    argv = _phase_argv(spec, panel)
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            if panel is not None:
                panel.write(line)
            _parse_progress_line(line, spec.name, panel)
        code = proc.wait()
    except Exception as exc:
        wall = time.perf_counter() - t0
        append_phase(logger, spec.name, wall_s=wall, result="fail", error=str(exc))
        raise
    wall = time.perf_counter() - t0
    if code == 0 or spec.allow_fail:
        append_phase(logger, spec.name, wall_s=wall, result="pass")
    else:
        append_phase(
            logger,
            spec.name,
            wall_s=wall,
            result="fail",
            error=f"exit {code}",
        )
    return code


def ix_argv(*parts: str) -> list[str]:
    return [sys.executable, "-u", "-m", "ix_crate", *parts]


def build_babylon_phases(
    *,
    skip_hygiene: bool,
    skip_crater: bool,
    skip_stemit: bool,
    budget: int,
    stemit_batches: list[int] | None,
    follow: bool,
) -> list[PhaseSpec]:
    phases: list[PhaseSpec] = []
    quiet_repair = [
        "music-repair",
        "--execute",
        "--no-gui",
        "--no-notify",
        "--no-verbose",
    ]

    if not skip_hygiene:
        phases.extend(
            [
                PhaseSpec("music-reconcile", ix_argv("music-reconcile", "--execute", "--passes", "6")),
                PhaseSpec("music-repair", ix_argv(*quiet_repair)),
                PhaseSpec(
                    "music-genre",
                    ix_argv("music-genre", "--execute", "--passes", "5"),
                ),
            ]
        )

    if not skip_crater:
        phases.append(PhaseSpec("quit-decks", []))

    if not skip_stemit:
        batches: list[int] = []
        if stemit_batches:
            batches = list(stemit_batches)
        elif budget > 0:
            batches = [budget]
        for i, n in enumerate(batches, start=1):
            phases.append(
                PhaseSpec(
                    f"stemit-chain-{i}",
                    ix_argv("stemit-chain", "--execute", "--budget", str(n)),
                    allow_fail=True,
                )
            )

    if skip_crater:
        return phases

    if not skip_hygiene:
        phases.extend(
            [
                PhaseSpec(
                    "music-genre-xml",
                    ix_argv("music-genre", "--xml", "--execute"),
                ),
                PhaseSpec(
                    "xml-prune",
                    ix_argv("xml-prune", "--execute", "--verbose"),
                ),
            ]
        )

    crater = ix_argv("crater", "--execute")
    if not follow:
        crater.append("--skip-follow")
    phases.append(PhaseSpec("crater", crater))
    return phases


def decks_running() -> bool:
    from ix_crate.deck_quit import decks_running as _running

    return _running()


def open_music() -> None:
    subprocess.run(
        ["open", "-a", "Music"],
        check=False,
        capture_output=True,
        timeout=30,
    )


def quit_decks() -> None:
    from ix_crate.deck_quit import quit_decks as _quit

    _quit()


def run_with_runlog(
    *,
    tool_id: str,
    title: str,
    phases: list[PhaseSpec],
    extra: dict[str, Any] | None,
    log_args: Any,
    on_phase: Callable[[PhaseSpec], None] | None = None,
) -> int:
    ensure_stems_path()
    from py.utils.notify import notify_complete, resolve_charts, summary_from_payload
    from py.utils.runlog import RunLogger, is_verbose, want_notify

    gui = bool(getattr(log_args, "gui", True))
    dry_run = not bool(getattr(log_args, "execute", False))
    panel = None
    if gui:
        try:
            from py.utils.progress import ProgressPanel

            panel = ProgressPanel.try_open(title)
        except ImportError as exc:
            print(f"progress GUI skipped ({exc})", flush=True)
    logger = RunLogger(
        tool_id,
        verbose=is_verbose(log_args),
        dry_run=dry_run,
        extra=extra or {},
        panel=panel,
    )
    if panel is not None:
        panel.set_totals(len(phases), len(phases))
        if hasattr(panel, "set_phase_plan"):
            panel.set_phase_plan([p.name for p in phases])
            for n in range(1, len(phases) + 1):
                panel.set_phase_state(n, "pending")

    def work() -> int:
        failed = False
        for i, spec in enumerate(phases, start=1):
            if on_phase:
                on_phase(spec)
            if panel is not None and hasattr(panel, "set_phase_state"):
                panel.set_phase_state(i, "running")
            if spec.name == "quit-decks":
                t0 = time.perf_counter()
                print("\n=== phase quit-decks ===", flush=True)
                if panel is not None:
                    panel.set_job(i, len(phases), spec.name, "quit")
                from ix_crate.deck_quit import ensure_decks_closed

                ensure_decks_closed(
                    confirm=bool(getattr(log_args, "confirm_deck_quit", False)),
                )
                append_phase(logger, spec.name, wall_s=time.perf_counter() - t0, result="pass")
                if panel is not None and hasattr(panel, "set_phase_state"):
                    panel.set_phase_state(i, "done")
                continue
            if spec.name.startswith("stemit-chain"):
                open_music()
            code = run_phase(logger, panel, i, len(phases), spec)
            if panel is not None and hasattr(panel, "set_phase_state"):
                panel.set_phase_state(i, "fail" if code != 0 and not spec.allow_fail else "done")
            if code != 0 and not spec.allow_fail:
                failed = True
                break
        return 1 if failed else 0

    def finish(code: int) -> int:
        try:
            logger.close()
        except Exception as exc:
            print(f"run log close failed: {exc}", flush=True)
        payload = logger.payload or {}
        if extra and extra.get("babylon_log"):
            payload.setdefault("extra", {}).update(extra)
        n_fail = sum(1 for t in payload.get("tracks") or [] if t.get("result") == "fail")
        summary = summary_from_payload(payload) if payload.get("tracks") else f"{title} finished"
        if n_fail:
            summary = f"{title} finished with {n_fail} failed phase(s)"
        charts = resolve_charts(payload)
        if want_notify(log_args, dry_run):
            notify_complete(title=tool_id, body=summary, payload=payload)
        if panel is not None:
            try:
                panel.finish(summary, charts=charts)
            except Exception as exc:
                print(f"progress GUI finish skipped ({exc})", flush=True)
        return code

    if panel is None:
        code = work()
        return finish(code)
    code_box: list[int] = []

    def thread_main() -> None:
        code_box.append(work())

    worker = threading.Thread(target=thread_main, name=tool_id, daemon=False)
    worker.start()
    panel.mainloop()
    worker.join()
    return finish(code_box[0] if code_box else 1)
