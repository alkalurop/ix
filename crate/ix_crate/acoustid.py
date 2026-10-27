"""AcoustID fingerprint lookup. fpcalc is local; API is api.acoustid.org.

Application client key is the public AcoustID client id unless ACOUSTID_API_KEY is set.
Never submit fingerprints. Never Discogs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from ix_crate.identify import clean_text, duration_close

ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
# Public AcoustID application client id (not a user secret). Override with ACOUSTID_API_KEY.
ACOUSTID_CLIENT = "v8pQ6oyB"
ACOUSTID_GAP = 0.4
MIN_SCORE = 0.55
FPCALC_TIMEOUT = 45


def fpcalc_bin() -> str | None:
    found = shutil.which("fpcalc")
    if found:
        return found
    brew = Path("/opt/homebrew/bin/fpcalc")
    if brew.is_file():
        return str(brew)
    return None


def client_key() -> str:
    return os.environ.get("ACOUSTID_API_KEY") or ACOUSTID_CLIENT


def fingerprint(path: Path) -> tuple[float, str] | None:
    binary = fpcalc_bin()
    if not binary or not path.is_file():
        return None
    try:
        raw = subprocess.check_output(
            [binary, "-json", str(path)],
            timeout=FPCALC_TIMEOUT,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(raw.decode("utf-8"))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TimeoutError):
        return None
    duration = data.get("duration")
    fp = data.get("fingerprint")
    if duration is None or not fp:
        return None
    return float(duration), str(fp)


def _hit_from_recording(rec: dict, score: float) -> dict | None:
    title = clean_text(str(rec.get("title") or ""))
    artists = rec.get("artists") or []
    artist = ""
    if artists:
        artist = clean_text(str(artists[0].get("name") or ""))
    if not artist or not title:
        return None
    album = ""
    for group in rec.get("releasegroups") or rec.get("releases") or []:
        album = clean_text(str(group.get("title") or ""))
        if album:
            break
    rec_dur = rec.get("duration")
    duration = float(rec_dur) if rec_dur else None
    return {
        "artist": artist,
        "album": album,
        "title": title,
        "duration": duration,
        "score": score,
        "source": "acoustid",
    }


def parse_acoustid(payload: dict, local_duration: float | None) -> dict | None:
    results = payload.get("results") or []
    ranked = sorted(results, key=lambda item: float(item.get("score") or 0), reverse=True)
    best: dict | None = None
    for result in ranked:
        score = float(result.get("score") or 0)
        if score < MIN_SCORE:
            continue
        for rec in result.get("recordings") or []:
            hit = _hit_from_recording(rec, score)
            if not hit:
                continue
            if local_duration and hit.get("duration"):
                if duration_close(local_duration, hit["duration"], slack=12.0):
                    hit["duration_match"] = True
                    return hit
            if best is None:
                best = hit
        if best and score >= 0.85:
            return best
    return best


def acoustid_identify(path: Path, cache: dict, local_duration: float | None = None) -> dict | None:
    from ix_crate.lookup import _http_json, _save_cache

    key = f"acoustid::{str(path.resolve()).lower()}::{int(path.stat().st_mtime) if path.exists() else 0}"
    if key in cache:
        return cache[key]
    fp = fingerprint(path)
    if fp is None:
        cache[key] = None
        _save_cache(cache)
        return None
    duration, digest = fp
    query = urllib.parse.urlencode(
        {
            "client": client_key(),
            "meta": "recordings+releasegroups+compress",
            "duration": str(int(round(duration))),
            "fingerprint": digest,
        }
    )
    payload = _http_json(f"{ACOUSTID_URL}?{query}", cache, f"acoustid-raw::{digest[:48]}", gap=ACOUSTID_GAP)
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        cache[key] = None
        _save_cache(cache)
        return None
    hit = parse_acoustid(payload, local_duration or duration)
    cache[key] = hit
    _save_cache(cache)
    return hit
