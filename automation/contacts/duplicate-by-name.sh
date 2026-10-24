#!/usr/bin/env bash
# Duplicate preview: same First + Last name fields. Read-only.
set -euo pipefail

data="$(osascript <<'APPLESCRIPT'
tell application "Contacts"
  set lines to {}
  repeat with p in every person
    set fn to ""
    set ln to ""
    try
      set fn to first name of p
    end try
    try
      set ln to last name of p
    end try
    if fn is missing value then set fn to ""
    if ln is missing value then set ln to ""
    set disp to name of p
    set em to ""
    set ph to ""
    try
      set em to value of first email of p
    end try
    try
      set ph to value of first phone of p
    end try
    set pid to id of p as text
    set end of lines to (fn & tab & ln & tab & disp & tab & em & tab & ph & tab & pid)
  end repeat
  set AppleScript's text item delimiters to linefeed
  return lines as text
end tell
APPLESCRIPT
)"

printf '%s\n' "$data" | python3 <<'PY'
import sys
from collections import defaultdict

raw = sys.stdin.read()
rows = []
for line in raw.splitlines():
    line = line.rstrip("\r")
    if not line.strip():
        continue
    parts = line.split("\t", 6)
    while len(parts) < 6:
        parts.append("")
    fn, ln, disp, em, ph, pid = parts[:6]
    key = (fn.strip().casefold(), ln.strip().casefold())
    rows.append((key, fn.strip(), ln.strip(), disp.strip(), em.strip(), ph.strip(), pid.strip()))

groups = defaultdict(list)
for key, fn, ln, disp, em, ph, pid in rows:
    groups[key].append((fn, ln, disp, em, ph, pid))

dups = {k: v for k, v in groups.items() if len(v) > 1}

blank = ("", "")
involved = sum(len(v) for v in dups.values())

print("Apple Contacts — duplicate preview (same First + Last name)")
print("=" * 60)
print(f"Total cards scanned:     {len(rows)}")
print(f"Duplicate name groups:   {len(dups)}")
print(f"Cards in those groups:   {involved}")
print()

if not dups:
    print("No duplicates found by first + last name.")
    raise SystemExit(0)

def sort_key(k):
    fn, ln = k
    return (ln, fn)

for key in sorted(dups, key=sort_key):
    items = dups[key]
    if key == blank:
        title = "(blank first and last name)"
    else:
        title = f"{items[0][0]} {items[0][1]}".strip()
    print(f"=== {title} — {len(items)} cards ===")
    for fn, ln, disp, em, ph, pid in sorted(items, key=lambda x: (x[2].casefold(), x[3].casefold())):
        bits = []
        title_cf = title.casefold()
        if disp and disp.casefold() not in {title_cf, f"{fn} {ln}".strip().casefold()}:
            bits.append(f"list name: {disp}")
        if em:
            bits.append(em)
        if ph:
            bits.append(ph)
        detail = " | ".join(bits) if bits else "(no distinct list name / email / phone)"
        short_id = pid[:12] + "…" if len(pid) > 12 else pid
        print(f"  • {detail}  [id {short_id}]")
    print()
PY
