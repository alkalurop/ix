#!/bin/bash
# STEMIT a genre batch, then CRATER.
#
# From a clone of https://github.com/ixamal/ix (Music.app on this Mac):
#
#   docs/examples/stemit-crater.sh                 # next 200 stems, then CRATER
#   BUDGET=100 docs/examples/stemit-crater.sh
#   SKIP_STEMIT=1 docs/examples/stemit-crater.sh   # CRATER only
#   SKIP_CRATER=1 docs/examples/stemit-crater.sh   # stems only
#   FOLLOW=1 docs/examples/stemit-crater.sh        # CRATER also runs MusicBrainz + Shazam
#   HYGIENE=1 docs/examples/stemit-crater.sh       # library-hygiene before STEMIT + CRATER
#
# Preflight (Rekordbox can stay open): PREFLIGHT=1 docs/examples/library-hygiene.sh
#
# The stems factory is the separate repo at ~/github/ixamal/stems
# (Homebrew Python 3.12 .venv; see that repo's RUNBOOK). Tracks that
# already have a .stem.m4a are skipped.
#
# Music.app is opened for the genre walk and the playlist bridge.
# Traktor and Rekordbox are asked to quit before CRATER writes NML or xml.
# If a save dialog is up, click through — the script waits, it does not
# force-kill. A stem-factory failure still continues into CRATER.
# Closing this terminal does not stop the job.
#
# Log: ~/local_tools/crate/reports/stemit-crater-<utc>.log
#      (crater-<utc>.log when SKIP_STEMIT=1)
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUDGET="${BUDGET:-200}"
REPORTS="${HOME}/local_tools/crate/reports"
mkdir -p "$REPORTS"
if [[ -z "${LOG:-}" ]]; then
  if [[ "${SKIP_STEMIT:-}" == 1 ]]; then
    LOG="${REPORTS}/crater-$(date -u +%Y%m%dT%H%M%SZ).log"
  else
    LOG="${REPORTS}/stemit-crater-$(date -u +%Y%m%dT%H%M%SZ).log"
  fi
fi

if [[ "${FOREGROUND:-}" != 1 ]]; then
  if pgrep -f 'Python.*-m py\.exec\.separate' >/dev/null; then
    echo "STEMIT factory already running (py.exec.separate). Stop it first." >&2
    exit 1
  fi
  export BUDGET SKIP_CRATER SKIP_STEMIT FOLLOW HYGIENE ROOT LOG
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
  echo "started log=$LOG"
  echo "tail -f $LOG"
  exit 0
fi

cd "$ROOT"
export PYTHONPATH=crate
HYGIENE_SCRIPT="${ROOT}/docs/examples/library-hygiene.sh"

if [[ "${HYGIENE:-}" == 1 ]]; then
  echo "HYGIENE music phase $(date)"
  FOREGROUND=1 LOG="$LOG" MUSIC_ONLY=1 bash "$HYGIENE_SCRIPT"
fi

if [[ "${SKIP_STEMIT:-}" != 1 ]]; then
  echo "STEMIT ${BUDGET} start $(date)"
  echo "Walking Music.app genres. The factory starts after ${BUDGET} tracks still need stems."
  open -a Music 2>/dev/null || true
  set +e
  nice -n 10 python3 -u -m ix_crate stemit-chain --execute --budget "$BUDGET"
  stem_code=$?
  set -e
  echo "STEMIT exit ${stem_code} $(date)"
else
  echo "SKIP_STEMIT=1 $(date)"
fi

if [[ "${SKIP_CRATER:-}" == 1 ]]; then
  echo "SKIP_CRATER=1; done."
  exit 0
fi

if [[ "${HYGIENE:-}" == 1 ]]; then
  echo "HYGIENE decks phase + CRATER $(date)"
  FOREGROUND=1 LOG="$LOG" DECKS_ONLY=1 bash "$HYGIENE_SCRIPT"
  crater_code=$?
  echo "HYGIENE+CRATER exit ${crater_code} $(date)"
  exit "${crater_code}"
fi

echo "Quitting Traktor and Rekordbox. If a dialog is up, click through. $(date)"
for app in rekordbox Traktor; do
  osascript -e "tell application \"$app\" to quit" 2>/dev/null || true
done
while pgrep -f 'rekordbox.app/Contents/MacOS' >/dev/null \
   || pgrep -f 'Traktor.app/Contents/MacOS' >/dev/null; do
  sleep 15
done
echo "decks closed $(date)"
open -a Music 2>/dev/null || true
sleep 5

args=(crater --execute)
if [[ "${FOLLOW:-}" != 1 ]]; then
  args+=(--skip-follow)
fi
nice -n 10 python3 -u -m ix_crate "${args[@]}"
crater_code=$?
echo "CRATER exit ${crater_code} $(date)"
exit "${crater_code}"
