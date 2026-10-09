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
#
# Time (rough): STEMIT=0 hygiene + CRATER ~20–45 min (music-genre can run 1–2 h if
# thousands of rows need clean_genre). Each stem budget ~3.5–4.5 min/track. FOLLOW=1 adds hours.
#
# Log: ~/local_tools/crate/reports/babylon-<utc>.log
# JSON + Mail.app notify via ix_crate.batch_notify (stems progress utils).
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPORTS="${HOME}/local_tools/crate/reports"
BUDGET="${BUDGET:-0}"
HYGIENE_SCRIPT="${ROOT}/docs/examples/library-hygiene.sh"
mkdir -p "$REPORTS"
LOG="${LOG:-${REPORTS}/babylon-$(date -u +%Y%m%dT%H%M%SZ).log}"
STARTED_AT="$(python3 -c 'import time; print(time.time())')"

notify_babylon() {
  local status="$1"
  local summary="${2:-BABYLON ${status}.}"
  PYTHONPATH=crate python3 -u -m ix_crate.batch_notify \
    --tool-id ix.crate.babylon \
    --title BABYLON \
    --log "$LOG" \
    --status "$status" \
    --started-at "$STARTED_AT" \
    --summary "$summary" \
    ${BABYLON_NO_NOTIFY:+--no-notify}
}

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

run_stemit_batches() {
  if [[ "${SKIP_STEMIT:-}" == 1 ]]; then
    echo "SKIP_STEMIT=1 $(date)"
    return 0
  fi
  local batches=()
  if [[ -n "${STEMIT_BATCHES:-}" ]]; then
    read -r -a batches <<< "${STEMIT_BATCHES}"
  elif [[ "${BUDGET:-0}" -gt 0 ]]; then
    batches=("$BUDGET")
  else
    echo "STEMIT=0 (no BUDGET / STEMIT_BATCHES) $(date)"
    return 0
  fi
  open -a Music 2>/dev/null || true
  local total=0
  for n in "${batches[@]}"; do
    total=$((total + n))
  done
  echo "STEMIT batches (${#batches[@]} runs, ${total} tracks max) $(date)"
  local i=0
  for n in "${batches[@]}"; do
    i=$((i + 1))
    echo "STEMIT batch ${i}/${#batches[@]} budget=${n} $(date)"
    set +e
    nice -n 10 python3 -u -m ix_crate stemit-chain --execute --budget "$n"
    local code=$?
    set -e
    echo "STEMIT batch ${i} exit ${code} $(date)"
  done
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
  export ROOT LOG REPORTS BUDGET SKIP_STEMIT SKIP_HYGIENE FOLLOW STEMIT_BATCHES STARTED_AT BABYLON_NO_NOTIFY
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
trap 'notify_babylon fail "BABYLON failed — see log."; exit 1' ERR

echo "BABYLON start $(date)  log=$LOG"
print_eta
echo "Mixed In Key: quit optional (CRATER reads mikdb read-only). Quit Rekordbox + Traktor before deck writes."
echo ""

if [[ "${SKIP_HYGIENE:-}" != 1 ]]; then
  echo "=== hygiene music phase $(date) ==="
  FOREGROUND=1 LOG="$LOG" SKIP_NOTIFY=1 MUSIC_ONLY=1 bash "$HYGIENE_SCRIPT"
fi

run_stemit_batches

if [[ "${SKIP_CRATER:-}" == 1 ]]; then
  echo "SKIP_CRATER=1; BABYLON done $(date)"
  notify_babylon ok "BABYLON finished (CRATER skipped)."
  exit 0
fi

if [[ "${SKIP_HYGIENE:-}" != 1 ]]; then
  echo "=== hygiene decks phase + CRATER (MiK, GENRES, samples, remix) $(date) ==="
  FOREGROUND=1 LOG="$LOG" SKIP_NOTIFY=1 DECKS_ONLY=1 bash "$HYGIENE_SCRIPT"
else
  echo "=== CRATER only $(date) ==="
  for app in rekordbox Traktor; do
    osascript -e "tell application \"$app\" to quit" 2>/dev/null || true
  done
  while pgrep -f 'rekordbox.app/Contents/MacOS' >/dev/null \
     || pgrep -f 'Traktor.app/Contents/MacOS' >/dev/null; do
    sleep 15
  done
  open -a Music 2>/dev/null || true
  sleep 5
  args=(crater --execute)
  [[ "${FOLLOW:-}" != 1 ]] && args+=(--skip-follow)
  nice -n 10 python3 -u -m ix_crate "${args[@]}"
fi

echo ""
echo "BABYLON done $(date)"
echo "Reload rekordbox xml (<>). Don't ask again + No on tag overwrite."
notify_babylon ok "BABYLON finished — hygiene + CRATER (MiK mashups/playlists)."
