#!/bin/bash
# BABYLON — hygiene + optional STEMIT genre batches + full CRATER (MiK, mashups, decks).
#
# Default STEMIT=0 (no factory). Mixed In Key playlists are written inside CRATER
# (readonly SQLite on Collection11.mikdb — MiK app may stay open).
#
#   docs/examples/babylon.sh
#   BUDGET=100 docs/examples/babylon.sh
#   STEMIT_BATCHES="50 100 200" docs/examples/babylon.sh   # multiple genre walks
#   FOLLOW=1 docs/examples/babylon.sh                        # MusicBrainz + Shazam (hours)
#   SKIP_HYGIENE=1 docs/examples/babylon.sh                # CRATER only (still quits decks)
#   PREFLIGHT=1 docs/examples/babylon.sh                     # counts; decks may stay open
#   docs/examples/babylon.sh --force                         # confirm, then quit Rekordbox + Traktor
#
# Time (rough): STEMIT=0 hygiene + CRATER ~20–45 min (music-genre can run 1–2 h if
# thousands of rows need clean_genre). Each stem budget ~3.5–4.5 min/track. FOLLOW=1 adds hours.
#
# Log: ~/local_tools/crate/reports/babylon-<utc>.log
# Progress: ix_crate babylon (RunLogger + optional HUD); JSON/charts under stems log/
# and a copy next to the shell log. Mail via notify_complete when the run ends.
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

BABYLON_FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) BABYLON_FORCE=1 ;;
    -h|--help)
      sed -n '2,19p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done
export BABYLON_FORCE

babylon_confirm_quit_decks() {
  echo ""
  echo "BABYLON --force: will ask Rekordbox and Traktor to quit (AppleScript quit, never force-kill)."
  echo "If a save or unsaved-set dialog appears, click through in those apps."
  local ans=""
  if [[ -t 0 ]]; then
    read -r -p "Quit Rekordbox and Traktor now? [y/N] " ans
  elif [[ -r /dev/tty ]]; then
    read -r -p "Quit Rekordbox and Traktor now? [y/N] " ans </dev/tty
  else
    echo "No TTY for confirmation; use FOREGROUND=1 in a terminal or quit decks manually." >&2
    exit 1
  fi
  case "$ans" in
    [yY]|[yY][eE][sS]) ;;
    *)
      echo "Aborted (--force requires yes)."
      exit 1
      ;;
  esac
}

babylon_quit_decks() {
  echo "Quitting Traktor and Rekordbox. If a dialog is up, click through. $(date)"
  for app in rekordbox Traktor; do
    osascript -e "tell application \"$app\" to quit" 2>/dev/null || true
  done
  while pgrep -f 'rekordbox.app/Contents/MacOS' >/dev/null \
     || pgrep -f 'Traktor.app/Contents/MacOS' >/dev/null; do
    sleep 15
  done
  echo "decks closed $(date)"
  export BABYLON_FORCE_QUIT_DONE=1
}

maybe_force_quit_decks() {
  [[ "${BABYLON_FORCE:-}" == 1 ]] || return 0
  [[ "${BABYLON_FORCE_QUIT_DONE:-}" == 1 ]] && return 0
  babylon_confirm_quit_decks
  babylon_quit_decks
}

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPORTS="${HOME}/local_tools/crate/reports"
BUDGET="${BUDGET:-0}"
HYGIENE_SCRIPT="${ROOT}/docs/examples/library-hygiene.sh"
mkdir -p "$REPORTS"
LOG="${LOG:-${REPORTS}/babylon-$(date -u +%Y%m%dT%H%M%SZ).log}"

print_eta() {
  PYTHONPATH=crate python3 -u <<'PY'
import os
from ix_crate.batch_notify import estimate_minutes

budget = int(os.environ.get("BUDGET", "0") or 0)
raw = (os.environ.get("STEMIT_BATCHES") or "").strip()
batches = [int(x) for x in raw.split() if x.strip()] if raw else None
follow = os.environ.get("FOLLOW", "") == "1"
hygiene = os.environ.get("SKIP_HYGIENE", "") != "1"
lo, hi = estimate_minutes(budget=budget, batches=batches, follow=follow, hygiene=hygiene)
print(f"ETA (rough): {lo}–{hi} min wall clock")
PY
}

if [[ "${PREFLIGHT:-}" == 1 ]]; then
  export PYTHONPATH=crate
  cd "$ROOT"
  PREFLIGHT=1 FOREGROUND=1 bash "$HYGIENE_SCRIPT" | tee "${REPORTS}/babylon-preflight-$(date -u +%Y%m%dT%H%M%SZ).log"
  exit 0
fi

if [[ "${FOREGROUND:-}" != 1 ]]; then
  if pgrep -f 'Python.*-m py\.exec\.separate' >/dev/null; then
    echo "STEMIT factory already running (py.exec.separate). Stop it first." >&2
    exit 1
  fi
  maybe_force_quit_decks
  export ROOT LOG REPORTS BUDGET SKIP_STEMIT SKIP_HYGIENE SKIP_CRATER FOLLOW STEMIT_BATCHES BABYLON_NO_NOTIFY BABYLON_FORCE BABYLON_FORCE_QUIT_DONE
  # Detached runs skip Tk (system python3 often lacks _tkinter); use FOREGROUND=1 for HUD.
  export BABYLON_NO_GUI="${BABYLON_NO_GUI:-1}"
  python3 -c '
import os, sys
log, script = sys.argv[1], sys.argv[2]
if os.fork():
    os._exit(0)
os.setsid()
if os.fork():
    os._exit(0)
fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(fd, 1)
os.dup2(fd, 2)
os.close(fd)
env = os.environ.copy()
env["FOREGROUND"] = "1"
env["LOG"] = log
os.execvpe("/bin/bash", ["/bin/bash", script], env)
' "$LOG" "$0"
  echo "BABYLON started log=$LOG"
  print_eta
  echo "tail -f $LOG"
  exit 0
fi

cd "$ROOT"
export PYTHONPATH=crate

echo "BABYLON start $(date)  log=$LOG"
print_eta
maybe_force_quit_decks

args=(babylon --execute --log "$LOG" --budget "$BUDGET")
[[ "${SKIP_HYGIENE:-}" == 1 ]] && args+=(--skip-hygiene)
[[ "${SKIP_CRATER:-}" == 1 ]] && args+=(--skip-crater)
[[ "${SKIP_STEMIT:-}" == 1 ]] && args+=(--skip-stemit)
[[ "${FOLLOW:-}" == 1 ]] && args+=(--follow)
[[ -n "${STEMIT_BATCHES:-}" ]] && args+=(--stemit-batches "$STEMIT_BATCHES")
[[ "${BABYLON_NO_NOTIFY:-}" == 1 ]] && args+=(--no-notify)
[[ "${BABYLON_NO_GUI:-}" == 1 ]] && args+=(--no-gui)
nice -n 10 python3 -u -m ix_crate "${args[@]}"
exit $?
