#!/bin/bash
# Monthly ixamal → alkalurop mirror. 15th of the month.
# Org profile (the GitHub org section): https://github.com/alkalurop
# Load: docs/examples/ai.ixamal.alkalurop-bridge.plist
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

SRC_OWNER="${SRC_OWNER:-ixamal}"
DST_ORG="${DST_ORG:-alkalurop}"

need() { command -v "$1" >/dev/null || { echo "need $1" >&2; exit 1; }; }
need gh
need git
gh auth status >/dev/null

should_skip() {
  case "$1" in
    .github) return 0 ;;
  esac
  return 1
}

dst_owner() {
  # GitHub follows transfer redirects (alkalurop/ix → ixamal/ix). Require the org owner.
  gh api "repos/${DST_ORG}/${1}" --jq '.owner.login' 2>/dev/null || true
}

ensure_dst() {
  local name="$1" desc="$2" homepage="$3"
  if [ "$(dst_owner "$name")" = "$DST_ORG" ]; then
    return 0
  fi
  gh repo create "${DST_ORG}/${name}" --public \
    --description "$desc" \
    --homepage "$homepage"
}

mirror_one() {
  local name="$1"
  local src="https://github.com/${SRC_OWNER}/${name}.git"
  local dst="https://github.com/${DST_ORG}/${name}.git"
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/alkalurop-bridge.XXXXXX")"
  git clone --bare "$src" "${tmp}/${name}.git"
  git --git-dir="${tmp}/${name}.git" push --mirror "$dst"
  rm -rf "$tmp"
}

echo "==> listing public ${SRC_OWNER} originals"
names=""
while IFS= read -r name; do
  [ -n "$name" ] || continue
  names="${names}${names:+ }${name}"
done <<EOF
$(gh repo list "$SRC_OWNER" --limit 100 --json name,isPrivate,isFork,isArchived \
    --jq '.[] | select(.isPrivate==false and .isFork==false and .isArchived==false) | .name')
EOF

if [ -z "$names" ]; then
  echo "no public ${SRC_OWNER} originals" >&2
  exit 1
fi

for name in $names; do
  if should_skip "$name"; then
    echo "-- skip ${name}"
    continue
  fi
  desc="$(gh repo view "${SRC_OWNER}/${name}" --json description --jq '.description // empty')"
  url="$(gh repo view "${SRC_OWNER}/${name}" --json url --jq '.url')"
  [ -n "$desc" ] || desc="Bridge of ${SRC_OWNER}/${name}"
  echo "==> ${SRC_OWNER}/${name} → ${DST_ORG}/${name}"
  ensure_dst "$name" "Bridge of ${SRC_OWNER}/${name} — ${desc}" "$url"
  mirror_one "$name"
done

echo "==> done ${DST_ORG} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
