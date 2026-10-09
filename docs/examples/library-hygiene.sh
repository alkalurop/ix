#!/bin/bash
# Library hygiene — EDM genre cleanup, Music relink, dead rekordbox.xml rows, CRATER.
#
# Rekordbox must quit before the xml steps. Music.app should be open for the
# Music phase. Traktor must quit before CRATER writes NML.
#
#   docs/examples/library-hygiene.sh              # full pass (detached)
#   PREFLIGHT=1 docs/examples/library-hygiene.sh  # counts only; decks stay open
#   MUSIC_ONLY=1 docs/examples/library-hygiene.sh # file + Music genres; decks stay open
#   DECKS_ONLY=1 docs/examples/library-hygiene.sh # quit decks, xml genre, prune, CRATER
#   SKIP_CRATER=1 docs/examples/library-hygiene.sh
#   FOLLOW=1 docs/examples/library-hygiene.sh     # CRATER runs MusicBrainz + Shazam
#
# Chain with STEMIT:
#   HYGIENE=1 BUDGET=100 docs/examples/stemit-crater.sh
#
# Log: ~/local_tools/crate/reports/library-hygiene-<utc>.log
#
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPORTS="${HOME}/local_tools/crate/reports"
EMAIL_TO="${EMAIL_TO:-david@alkalurops.org}"
mkdir -p "$REPORTS"
LOG="${LOG:-${REPORTS}/library-hygiene-$(date -u +%Y%m%dT%H%M%SZ).log}"

notify_hygiene() {
  local status="$1"
  [[ "${SKIP_NOTIFY:-}" == 1 ]] && return 0
  local summary="Library hygiene ${status}."
  PYTHONPATH=crate python3 -u -m ix_crate.batch_notify \
    --tool-id ix.crate.hygiene \
    --title "Library hygiene" \
    --log "$LOG" \
    --status "$status" \
    --started-at "${HYGIENE_STARTED_AT:-$(python3 -c 'import time; print(time.time())')}" \
    --summary "$summary"
}

if [[ "${FOREGROUND:-}" != 1 && "${PREFLIGHT:-}" != 1 ]]; then
  if pgrep -f 'Python.*-m py\.exec\.separate' >/dev/null; then
    echo "STEMIT factory already running (py.exec.separate). Stop it first." >&2
    exit 1
  fi
  export ROOT LOG REPORTS SKIP_CRATER FOLLOW MUSIC_ONLY DECKS_ONLY
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

preflight() {
  echo "LIBRARY HYGIENE preflight $(date)"
  echo "Rekordbox can stay open for this section."
  python3 -u <<'PY'
import plistlib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

from ix_crate.crates import itunes_library_xml
from ix_crate.music_genre import clean_genre
from ix_crate.stems_playlists import REKORDBOX_XML
from ix_crate.xml_prune import plan_prune

it = itunes_library_xml()
with it.open("rb") as f:
    tracks = (plistlib.load(f).get("Tracks") or {}).values()
edm = Counter()
house_tail = 0
for row in tracks:
    g = str(row.get("Genre") or "").strip()
    if not g:
        continue
    if g.upper().startswith("EDM"):
        edm[g] += 1
    elif clean_genre(g) != g:
        house_tail += 1
print(f"Music library XML: {len(tracks)} tracks")
print(f"  EDM-prefixed genres: {sum(edm.values())} rows")
for name, count in edm.most_common(8):
    print(f"    {count:5}  {name}")
if house_tail:
    print(f"  other genres needing clean_genre: {house_tail} rows")

if REKORDBOX_XML.is_file():
    root = ET.parse(REKORDBOX_XML).getroot()
    collection = root.find("COLLECTION")
    rb_edm = rb_clean = 0
    if collection is not None:
        for track in collection.findall("TRACK"):
            g = (track.get("Genre") or "").strip()
            if g.upper().startswith("EDM"):
                rb_edm += 1
            elif g and clean_genre(g) != g:
                rb_clean += 1
    plan = plan_prune(root)
    print(f"rekordbox.xml: {plan.scanned} TRACK rows")
    print(f"  EDM-prefixed Genre attrs: {rb_edm}")
    print(f"  other Genre attrs needing clean_genre: {rb_clean}")
    reasons = plan.reasons()
    dead = sum(reasons.values())
    print(f"  xml-prune would drop: {dead} ({', '.join(f'{k}={v}' for k, v in sorted(reasons.items())) or 'none'})")
    print("  note: Rekordbox autolocate misses in the app are often master.db rows.")
    print("        xml-prune fixes the sidecar; reload <> after the decks phase.")
else:
    print(f"rekordbox.xml missing: {REKORDBOX_XML}")
PY
  echo "Preflight done. Run without PREFLIGHT=1 when Rekordbox can quit."
}

run_music_phase() {
  echo "=== Music phase (Rekordbox may stay open) $(date) ==="
  open -a Music 2>/dev/null || true
  echo "music-reconcile (dead Music.app rows from iTunes XML map)"
  nice -n 10 python3 -u -m ix_crate music-reconcile --execute --passes 6
  echo "music-repair (Locate / ! rows under Media.localized + stems_audio)"
  nice -n 10 python3 -u -m ix_crate music-repair --execute --no-gui
  echo "music-genre (file tags + Music.app library rows; clean_genre)"
  nice -n 10 python3 -u -m ix_crate music-genre --execute --passes 5
}

quit_decks() {
  echo "Quitting Traktor and Rekordbox. If a dialog is up, click through. $(date)"
  for app in rekordbox Traktor; do
    osascript -e "tell application \"$app\" to quit" 2>/dev/null || true
  done
  while pgrep -f 'rekordbox.app/Contents/MacOS' >/dev/null \
     || pgrep -f 'Traktor.app/Contents/MacOS' >/dev/null; do
    sleep 15
  done
  echo "decks closed $(date)"
}

run_decks_phase() {
  echo "=== Decks phase $(date) ==="
  quit_decks
  open -a Music 2>/dev/null || true
  sleep 5
  echo "music-genre --xml (rekordbox.xml TRACK Genre; quit Rekordbox first)"
  nice -n 10 python3 -u -m ix_crate music-genre --xml --execute
  echo "xml-prune (drop missing-file and .m4p rows from rekordbox.xml)"
  nice -n 10 python3 -u -m ix_crate xml-prune --execute --verbose
  if [[ "${SKIP_CRATER:-}" == 1 ]]; then
    echo "SKIP_CRATER=1; decks phase done."
    return 0
  fi
  args=(crater --execute)
  if [[ "${FOLLOW:-}" != 1 ]]; then
    args+=(--skip-follow)
  fi
  echo "CRATER (playlists, STEMIT crates, GENRES/ACAPELLAS, xml-prune again)"
  nice -n 10 python3 -u -m ix_crate "${args[@]}"
  echo ""
  echo "After Rekordbox opens: reload rekordbox xml (<>)."
  echo "On tag overwrite: Don't ask again + No (file tags are already clean)."
  echo "Tracks that still fail autolocate live only in master.db — remove or relocate in-app."
}

if [[ "${PREFLIGHT:-}" == 1 ]]; then
  preflight | tee "${REPORTS}/library-hygiene-preflight-$(date -u +%Y%m%dT%H%M%SZ).log"
  exit 0
fi

HYGIENE_STARTED_AT="$(python3 -c 'import time; print(time.time())')"
echo "LIBRARY HYGIENE start $(date)  log=$LOG"
trap 'notify_hygiene fail; exit 1' ERR

if [[ "${DECKS_ONLY:-}" == 1 ]]; then
  run_decks_phase
elif [[ "${MUSIC_ONLY:-}" == 1 ]]; then
  run_music_phase
else
  run_music_phase
  run_decks_phase
fi

echo "LIBRARY HYGIENE done $(date)"
notify_hygiene ok
