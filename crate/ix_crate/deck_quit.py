"""AppleScript quit for Rekordbox and Traktor before xml/NML writes."""

from __future__ import annotations

import subprocess
import sys
import time


def decks_running() -> bool:
    for pattern in ("rekordbox.app/Contents/MacOS", "Traktor.app/Contents/MacOS"):
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


def quit_decks() -> None:
    print("Quitting Traktor and Rekordbox. If a dialog is up, click through.", flush=True)
    for app in ("rekordbox", "Traktor"):
        subprocess.run(
            ["osascript", "-e", f'tell application "{app}" to quit'],
            check=False,
            capture_output=True,
            timeout=30,
        )
    while decks_running():
        time.sleep(15)
    print("decks closed", flush=True)


def ensure_decks_closed(*, confirm: bool = False) -> None:
    """Default: quit nicely when either deck app is running. ``confirm=True`` prompts first."""
    if not decks_running():
        return
    if confirm:
        confirm_quit_decks()
    quit_decks()
