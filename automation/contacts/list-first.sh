#!/usr/bin/env bash
# Print first N contacts (AppleScript internal order). Read-only.
set -euo pipefail

N="${1:-2}"

osascript <<APPLESCRIPT
tell application "Contacts"
  activate
  set thePeople to every person
  set limitN to ${N}
  if (count of thePeople) < limitN then set limitN to (count of thePeople)
  repeat with i from 1 to limitN
    set p to item i of thePeople
    set nm to name of p
    set ph to ""
    set em to ""
    try
      set ph to value of (first phone of p)
    end try
    try
      set em to value of (first email of p)
    end try
    log (nm & " | " & ph & " | " & em)
  end repeat
end tell
APPLESCRIPT
