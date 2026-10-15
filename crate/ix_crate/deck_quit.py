"""AppleScript quit for Rekordbox and Traktor before xml/NML writes."""

from __future__ import annotations

import re
import subprocess
import sys
import time

# pgrep -f patterns (main binary under .app/Contents/MacOS)
DECK_PROCESS_PATTERNS: tuple[str, ...] = (
    r"rekordbox\.app/Contents/MacOS",
    r"Traktor Pro \d+\.app/Contents/MacOS",
    r"Traktor\.app/Contents/MacOS",
)

# osascript application names (try each; harmless if not installed)
DECK_APPLESCRIPT_NAMES: tuple[str, ...] = (
    "rekordbox",
    "Traktor Pro 4",
    "Traktor Pro 3",
    "Traktor",
)

_WAIT_S = 15
_MAX_WAIT_ROUNDS = 40  # 10 min


def decks_running() -> bool:
    for pattern in DECK_PROCESS_PATTERNS:
        r = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return True
    return False


def _read_yes_no(prompt: str) -> bool:
    if sys.stdin.isatty():
        ans = input(prompt)
    else:
        try:
            with open("/dev/tty", "r") as tty:
                ans = tty.readline()
        except OSError:
            return False
    ans = (ans or "").strip()
    return ans.lower() in {"y", "yes"}


def confirm_quit_decks() -> None:
    """Optional; use ``--confirm-deck-quit`` on ``ix_crate babylon``."""
    print(
        "\nBABYLON will ask Rekordbox and Traktor to quit (AppleScript quit, never force-kill).",
        flush=True,
    )
    print("If a save dialog is up, click through in those apps.", flush=True)
    if not _read_yes_no("Quit Rekordbox and Traktor now? [y/N] "):
        raise SystemExit("Aborted (decks must quit before xml/NML writes).")


def _send_quit_applescript() -> None:
    for app in DECK_APPLESCRIPT_NAMES:
        subprocess.run(
            ["osascript", "-e", f'tell application "{app}" to quit'],
            check=False,
            capture_output=True,
            timeout=30,
        )


def quit_decks() -> None:
    print("Quitting Traktor and Rekordbox. If a dialog is up, click through.", flush=True)
    _send_quit_applescript()
    rounds = 0
    while decks_running():
        rounds += 1
        if rounds > _MAX_WAIT_ROUNDS:
            print(
                "decks still running after wait — close Rekordbox/Traktor manually, then continue.",
                flush=True,
            )
            return
        time.sleep(_WAIT_S)
        if rounds % 4 == 0:
            _send_quit_applescript()
    print("decks closed", flush=True)


def ensure_decks_closed(
    *,
    confirm: bool = False,
    always_confirm: bool | None = None,
    skip_prompt: bool | None = None,  # noqa: ARG001 — removed API; ignored
    always_attempt: bool = True,
) -> None:
    """Default: AppleScript-quit deck apps, then wait. Never force-kill."""
    if always_confirm is not None:
        confirm = bool(always_confirm)
    running = decks_running()
    if not running and not always_attempt:
        return
    if confirm and running:
        confirm_quit_decks()
    quit_decks()


def process_pattern_matches_traktor_pro(path: str) -> bool:
    """Test helper: whether a process cmdline matches Traktor Pro installs."""
    return bool(re.search(r"Traktor Pro \d+\.app/Contents/MacOS", path))
