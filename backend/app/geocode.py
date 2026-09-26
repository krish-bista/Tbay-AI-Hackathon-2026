"""
Place name -> coordinates.

Resolution order for each raw name the AI extracts:
  1. The ai_workflow gazetteer (instant, hand-verified coordinates).
  2. OpenStreetMap Nominatim, restricted to a box around the dataset's "anchor"
     (where the disaster is). Of the top 5 candidates we take the first whose
     name actually matches and that is a place (not a shop/office/etc.), so junk
     names like "Plumbing" or "Prince" aren't plotted.

Province/country-level results are dropped: they land on a meaningless centroid.
The cache stores raw candidates, so acceptance rules can change without re-querying.
Nominatim's policy is max 1 request/second, so results are cached in
data/geocode_cache.json (committed to the repo).
"""
import json
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

import httpx

from . import ai  # noqa: F401  (puts ai_workflow/ on sys.path)
from .config import DATA_DIR, GEOCODE_COUNTRY_CODES, GEOCODE_USER_AGENT

try:
    from geocoder import KNOWN_GAZETTEER  # ai_workflow/geocoder.py
except ImportError:
    KNOWN_GAZETTEER = {}

CACHE_PATH = DATA_DIR / "geocode_cache.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Anchor box half-size in degrees (~330 km N-S, ~350 km E-W at 50°N).
BOX_LAT, BOX_LON = 3.0, 5.0
# Nominatim place_rank: 4 country, 8 state/province, 12 county, 16 city, 18-22 suburb, 26+ street.
MIN_PLACE_RANK = 12
# Street/building-level matches must be within ~50 km of the anchor.
STREET_RADIUS = 0.45

# Gazetteer entries that are regions, not places.
_REGION_KEYS = {"alberta", "western canada", "canada"}
# Backend additions/corrections to the ai_workflow gazetteer: (lat, lon, display name)
_EXTRA_GAZETTEER = {
    "siksika": (50.663, -112.625, "Siksika Nation, AB"),
    "siksika nation": (50.663, -112.625, "Siksika Nation, AB"),
    "siksika first nation": (50.663, -112.625, "Siksika Nation, AB"),
}
# OSM categories that are businesses, not places people report flooding at.
_REJECT_CATEGORIES = {"shop", "office", "craft", "tourism", "man_made", "historic", "emergency",
                      "landuse", "aerialway"}
# Places/areas: single-word and partial matches are only trusted for these.
_AREA_CATEGORIES = {"place", "boundary", "natural", "waterway"}
# Specific facilities: only trusted with a distinctive (3+ word) name, e.g. "Chinook Regional Hospital".
_FACILITY_CATEGORIES = {"amenity", "building"}
# Trailing qualifiers stripped before lookup ("Canmore Alberta" -> "Canmore").
_TRAILING = re.compile(
    r"(\s*,?\s*\b(alberta|ab|canada|ca|ontario|on|manitoba|mb|saskatchewan|sk|"
    r"british columbia|bc|quebec|qc)\b)+$", re.IGNORECASE)
_STOPWORDS = {
    "the", "city", "downtown", "town", "home", "bank", "noon", "lots", "art", "hope",
    "river", "rescue", "emergency", "news", "flood", "flooding", "army", "god", "his",
    "history", "summer", "northern", "southern", "western", "eastern", "canadian",
    "dome", "plumbing", "govt", "government", "red cross", "mother nature", "canada day",
    "city hall", "walmart", "costco", "sobeys", "safeway", "tim hortons", "mcdonalds",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "today", "tonight", "tomorrow",
}

_lock = threading.Lock()
_last_request = 0.0
_cache: Dict[str, List[Dict]] = {}

_gaz_index: Dict[str, Tuple[float, float, str]] = {}
for _k, _v in {**KNOWN_GAZETTEER, **_EXTRA_GAZETTEER}.items():
    if _k not in _REGION_KEYS:
        _gaz_index[_k] = _v
        _gaz_index[_k.replace(" ", "")] = _v  # "highriver" -> "high river"


def normalize(raw: str) -> str:
    name = re.sub(r"^[#@]+", "", (raw or "").strip())
    name = _TRAILING.sub("", name).strip(" ,.-")
    return name


_PROVINCES = {"alberta": "ab", "ab": "ab", "british columbia": "bc", "bc": "bc", "ontario": "on",
               "on": "on", "manitoba": "mb", "mb": "mb", "saskatchewan": "sk", "sk": "sk",
               "quebec": "qc", "qc": "qc"}


def _provinces_in(text: str) -> set:
    parts = [p.strip().lower() for p in text.split(",")[1:]]  # only qualifiers after a comma
    return {_PROVINCES[p] for p in parts if p in _PROVINCES}


def lookup_gazetteer(raw: str) -> Optional[Dict]:
    hit = _gazetteer_hit(raw)
    if not hit:
        return None
    wanted = _provinces_in(raw)
    have = set(re.findall(r"\b(AB|BC|ON|MB|SK|QC)\b", hit[2]))
    if wanted and have and not ({h.lower() for h in have} & wanted):
        return None  # "Mission, BC" is not Mission, Calgary
    lat, lon, display = hit
    return {"name": display, "lat": lat, "lon": lon}


def _gazetteer_hit(raw: str) -> Optional[Tuple[float, float, str]]:
    key = normalize(raw).lower()
    hit = _gaz_index.get(key) or _gaz_index.get(key.replace(" ", ""))
    if not hit and "," in key:
        # "Mission, Calgary" -> gazetteer "mission" if its entry is in Calgary too.
        first, rest = key.split(",", 1)
        cand = _gaz_index.get(first.strip())
        if cand and all(part.strip() in cand[2].lower() for part in rest.split(",") if part.strip()):
            hit = cand
    return hit


def worth_looking_up(raw: str) -> bool:
    name = normalize(raw)
    if len(name) < 3 or name.lower() in _STOPWORDS or name.lower() in _REGION_KEYS:
        return False
    return any(c.isalpha() for c in name)


def _norm_words(s: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    s = re.sub(r"^(the|town of|city of|village of|summer village of)\s+", "", s.strip())
    return " ".join(s.split())


_GENERIC_SUFFIXES = {"city", "town", "village", "municipality", "county", "district", "province",
                     "river", "creek", "lake", "park", "first nation", "nation"}


def _acceptable(query: str, cand: Dict) -> bool:
    if cand.get("rank", 0) < MIN_PLACE_RANK or cand.get("cat") in _REJECT_CATEGORIES:
        return False
    # Match on the place itself: "Tacloban, Philippines" -> "tacloban"
    q, n = _norm_words(query.split(",")[0]), _norm_words(cand.get("n") or "")
    cat, words = cand.get("cat"), len(q.split())
    if not n:
        return False
    if cat in _FACILITY_CATEGORIES and words < 3:
        return False
    if words == 1 and cat not in _AREA_CATEGORIES:
        return False
    if q == n:
        return True
    # "Tacloban" -> "Tacloban City", "Siksika" -> "Siksika Nation"
    if cat in _AREA_CATEGORIES and n.startswith(q + " ") and n[len(q) + 1:] in _GENERIC_SUFFIXES:
        return True
    # Multi-word query contained in an area's name, e.g. "stoney nakoda nation"
    return words >= 2 and cat in _AREA_CATEGORIES and q in n


def _short_name(display_name: str) -> str:
    parts = [p.strip() for p in display_name.split(",")]
    parts = [p for p in parts if p and not re.match(r"^[A-Z]\d[A-Z]", p) and not p.isdigit()]
    return ", ".join(parts[:3])


def _box_key(anchor: Optional[Tuple[float, float]]) -> str:
    return "any" if anchor is None else f"{anchor[0]:.1f},{anchor[1]:.1f}"


def _load_cache():
    global _cache
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            # Only keep entries in the current format: "name|box" -> [candidates]
            _cache = {k: v for k, v in data.items() if "|" in k and isinstance(v, list)}
        except ValueError:
            _cache = {}


def _save_cache():
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_cache, indent=0, sort_keys=True))
    os.replace(tmp, CACHE_PATH)


def _query_nominatim(name: str, anchor: Optional[Tuple[float, float]],
                     countrycodes: str = "") -> Optional[List[Dict]]:
    """Raw candidates, [] if none, None on network error (not cached)."""
    global _last_request
    wait = 1.1 - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    params = {"q": name, "format": "jsonv2", "limit": 5}
    if anchor is not None:
        lat, lon = anchor
        params["viewbox"] = f"{lon - BOX_LON},{lat + BOX_LAT},{lon + BOX_LON},{lat - BOX_LAT}"
        params["bounded"] = 1
    if countrycodes:
        params["countrycodes"] = countrycodes
    try:
        r = httpx.get(NOMINATIM_URL, params=params,
                      headers={"User-Agent": GEOCODE_USER_AGENT}, timeout=6)
        r.raise_for_status()
        results = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        _last_request = time.time()
    return [{
        "name": _short_name(r.get("display_name") or name),
        "n": r.get("name") or "",
        "cat": r.get("category") or "",
        "lat": float(r["lat"]),
        "lon": float(r["lon"]),
        "rank": int(r.get("place_rank") or 0),
    } for r in results]


def _candidates(name: str, anchor: Optional[Tuple[float, float]], countrycodes: str = "") -> List[Dict]:
    key = f"{name.lower()}|{_box_key(anchor)}" + (f":{countrycodes}" if countrycodes else "")
    with _lock:
        if key in _cache:
            return _cache[key]
        cands = _query_nominatim(name, anchor, countrycodes)
        if cands is None:  # network error: don't cache
            return []
        _cache[key] = cands
        _save_cache()
        return cands


def lookup_nominatim(raw: str, anchor: Optional[Tuple[float, float]],
                     country_first: bool = True) -> Optional[Dict]:
    """
    Cached, rate-limited, thread-safe. Returns {"name", "lat", "lon"} or None.
    With no anchor and country_first, the configured country (GEOCODE_COUNTRY_CODES) is
    tried first. World-scope datasets pass country_first=False.
    """
    name = normalize(raw)
    if anchor is None and country_first and GEOCODE_COUNTRY_CODES:
        hit = _pick(name, _candidates(name, None, GEOCODE_COUNTRY_CODES), None)
        if hit:
            return hit
    return _pick(name, _candidates(name, anchor), anchor)


def _pick(name: str, cands: List[Dict], anchor: Optional[Tuple[float, float]]) -> Optional[Dict]:
    ok = [c for c in cands if _acceptable(name, c)]
    if anchor is None:
        # No disaster centre to check against: a street/building name could be anywhere.
        ok = [c for c in ok if c.get("rank", 0) < 26]
    else:
        # Streets/buildings (rank >= 26) only make sense close to the disaster.
        ok = [c for c in ok if c.get("rank", 0) < 26
              or abs(c["lat"] - anchor[0]) < STREET_RADIUS and abs(c["lon"] - anchor[1]) < STREET_RADIUS * 1.6]
    if not ok:
        return None
    if anchor is not None:
        # Prefer the match nearest the disaster ("Kensington" -> Calgary, not Edmonton).
        ok.sort(key=lambda c: (c["lat"] - anchor[0]) ** 2 + (c["lon"] - anchor[1]) ** 2)
    c = ok[0]
    return {"name": c["name"], "lat": c["lat"], "lon": c["lon"]}


def is_cached(raw: str, anchor: Optional[Tuple[float, float]], country_first: bool = True) -> bool:
    """True if looking this name up needs no network request."""
    key = f"{normalize(raw).lower()}|{_box_key(anchor)}"
    if anchor is None and country_first and GEOCODE_COUNTRY_CODES:
        return key + f":{GEOCODE_COUNTRY_CODES}" in _cache
    return key in _cache


def _km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))


def detect_scope(points: List[Tuple[float, float, int]], min_points: int = 5,
                 radius_km: float = 1500, regional_share: float = 0.6) -> str:
    """
    "regional" if most mention-weight sits within radius_km of the weighted median,
    else "world". Too few points to judge -> "regional" (the proven default).
    """
    if len(points) < min_points:
        return "regional"
    centre = weighted_anchor(points)
    total = sum(w for _, _, w in points)
    near = sum(w for la, lo, w in points if _km((la, lo), centre) <= radius_km)
    return "regional" if near / total >= regional_share else "world"


def in_region(place: Dict, anchor: Tuple[float, float]) -> bool:
    """Inside the regional search box around the anchor."""
    return abs(place["lat"] - anchor[0]) <= BOX_LAT and abs(place["lon"] - anchor[1]) <= BOX_LON


def weighted_anchor(points: List[Tuple[float, float, int]]) -> Optional[Tuple[float, float]]:
    """Mention-weighted median of (lat, lon, weight) — robust to a few far-off outliers."""
    if not points:
        return None

    def wmedian(vals):
        vals = sorted(vals)
        half = sum(w for _, w in vals) / 2
        acc = 0
        for v, w in vals:
            acc += w
            if acc >= half:
                return v
        return vals[-1][0]

    return (wmedian([(p[0], p[2]) for p in points]), wmedian([(p[1], p[2]) for p in points]))


_load_cache()
