"""
Background processing for an uploaded dataset:

  1. Classify every tweet with the AI module (batches run in parallel, with retries).
  2. Publish the dataset immediately so the UI can show tweets/stats.
  3. Geocode place names, most-mentioned first; map points appear progressively.
  4. Persist the finished dataset.

The provided sample dataset is also written to data/sample_seed.json (committed),
tagged with a fingerprint of the AI code, so deployed servers load it instantly
instead of reprocessing on every cold start.
"""
import gzip
import hashlib
import json
import logging
import os
import threading
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from . import ai, geocode, store
from .config import (AI_CONCURRENCY, AI_WORKFLOW_DIR, BACKEND_DIR, BATCH_SIZE,
                     BUILTIN_DATASETS, BUILTIN_GEOCODE_MAX_LOOKUPS, BUILTIN_LLM_MAX_REQUESTS,
                     BUILTIN_USE_LLM, GEOCODE_MAX_LOOKUPS, LLM_MAX_REQUESTS_PER_DATASET,
                     SCOPE_PROBE_NAMES)
from .csv_loader import parse_tweets_csv

log = logging.getLogger("pipeline")
_jobs_executor = ThreadPoolExecutor(max_workers=2)

# Files whose changes should invalidate the precomputed sample.
_FINGERPRINT_FILES = [
    BACKEND_DIR / "app" / "ai.py",
    BACKEND_DIR / "app" / "geocode.py",
    BACKEND_DIR / "app" / "pipeline.py",
    AI_WORKFLOW_DIR / "analyzer.py",
    AI_WORKFLOW_DIR / "prompt_template.py",
    AI_WORKFLOW_DIR / "geocoder.py",
]


def ai_fingerprint() -> str:
    """Hash of the AI/geocoding code. Whether the seed used Gemini is recorded separately."""
    h = hashlib.sha1()
    for p in _FINGERPRINT_FILES:
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _builtin(dataset_id: str) -> Optional[Dict]:
    return next((b for b in BUILTIN_DATASETS if b["id"] == dataset_id), None)


def _read_seed(path) -> Optional[Dict]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def ensure_builtin_datasets():
    """
    Startup: make every built-in dataset available. Order of preference:
    already persisted with matching fingerprint > committed seed > reprocess
    (rule engine only unless BUILTIN_USE_LLM=1, so servers never spend quota here).
    """
    fp = ai_fingerprint()
    for b in BUILTIN_DATASETS:
        ds = store.datasets.get(b["id"])
        if ds and ds.get("fingerprint") == fp:
            continue
        store.datasets.pop(b["id"], None)
        seed = _read_seed(b["seed"]) if b["seed"].exists() else None
        if seed and seed.get("fingerprint") == fp:
            store.save_dataset(seed)
            log.info("loaded built-in dataset %s from seed (%d tweets)", b["id"], len(seed["tweets"]))
            continue
        if seed:
            log.warning("seed for %s is stale (AI code changed); reprocessing%s. Regenerate "
                        "locally with BUILTIN_USE_LLM=1 and commit data/seeds/.", b["id"],
                        " with Gemini" if BUILTIN_USE_LLM else " with the rule engine (no quota)")
        if b["csv"].exists():
            start(b["name"], parse_tweets_csv(b["csv"].read_bytes()), dataset_id=b["id"])


def start(name: str, tweets: List[Dict], dataset_id: str = None, scope: str = "auto") -> Dict:
    dataset_id = dataset_id or store.new_id()
    job = store.create_job(dataset_id, total=len(tweets))
    _jobs_executor.submit(_run, job["id"], dataset_id, name, tweets, scope)
    return job


# ---------------------------------------------------------------------------

_NOT_RELEVANT_ON_ERROR = {"relevant": False, "confidence": 0.0, "category": None,
                          "severity": None, "reasoning": "AI classification failed", "locations": [],
                          "source": "error"}


def _classify_with_retry(texts: List[str], use_llm: bool, attempts: int = 3) -> Tuple[List[Dict], bool]:
    """Returns (results, ok). Never raises — a failed batch is marked unrelated."""
    for attempt in range(attempts):
        try:
            # Retries never use the LLM: failed requests still cost quota.
            results = ai.classify_batch(texts, use_llm=use_llm and attempt == 0)
            if len(results) != len(texts):
                raise RuntimeError(f"classify_batch returned {len(results)} results for {len(texts)} tweets")
            return results, True
        except Exception as e:  # noqa: BLE001
            log.warning("classify_batch failed (attempt %d/%d): %s", attempt + 1, attempts, e)
            time.sleep(2 ** attempt)
    return [dict(_NOT_RELEVANT_ON_ERROR) for _ in texts], False


def _plan_llm(tweets: List[Dict], use_llm: bool, max_requests: int) -> List[Dict]:
    """
    Which tweets go to the LLM. Small datasets: all of them. Large ones (more batches than
    max_requests): only likely-flood tweets, strongest signals first, up to the cap.
    Everything else is classified by the free rule engine.
    """
    if not use_llm:
        return []
    if len(tweets) <= max_requests * BATCH_SIZE:
        return list(tweets)
    scored = [(ai.llm_priority(t["text"]), t) for t in tweets]
    candidates = [t for p, t in sorted(scored, key=lambda x: -x[0]) if p > 0]
    return candidates[:max_requests * BATCH_SIZE]


def _classify_all(job_id: str, tweets: List[Dict], use_llm: bool, max_requests: int):
    llm_tweets = _plan_llm(tweets, use_llm, max_requests)
    llm_ids = {id(t) for t in llm_tweets}
    rule_tweets = [t for t in tweets if id(t) not in llm_ids]
    batches = ([(llm_tweets[i:i + BATCH_SIZE], True) for i in range(0, len(llm_tweets), BATCH_SIZE)]
               + [(rule_tweets[i:i + BATCH_SIZE], False) for i in range(0, len(rule_tweets), BATCH_SIZE)])
    store.update_job(job_id, llm_tweets=len(llm_tweets),
                     llm_requests_planned=-(-len(llm_tweets) // BATCH_SIZE))
    done = [0]
    failed = [0]
    lock = threading.Lock()

    def work(args):
        batch, batch_llm = args
        results, ok = _classify_with_retry([t["text"] for t in batch], batch_llm)
        for t, r in zip(batch, results):
            t["relevant"] = bool(r.get("relevant"))
            t["confidence"] = float(r.get("confidence") or 0)
            t["category"] = r.get("category") if t["relevant"] else None
            t["severity"] = r.get("severity") if t["relevant"] else None
            t["reasoning"] = r.get("reasoning") or ""
            t["disaster_type"] = r.get("disaster_type") or "none"
            t["ai_source"] = r.get("source") or "rules"
            t["location_names"] = list(r.get("locations") or []) if t["relevant"] else []
            t["locations"] = []
        with lock:
            done[0] += len(batch)
            if not ok:
                failed[0] += len(batch)
            store.update_job(job_id, processed=done[0], ai_failed=failed[0])

    with ThreadPoolExecutor(max_workers=AI_CONCURRENCY) as pool:
        list(pool.map(work, batches))


def _add_location(tweets: List[Dict], loc: Dict):
    for t in tweets:
        if not any(l["name"] == loc["name"] for l in t["locations"]):
            t["locations"].append(dict(loc))


def _geocode_all(job_id: str, ds: Dict, scope: str, max_lookups: int):
    """
    scope: "regional" | "world" | "auto". Regional datasets bound OpenStreetMap lookups to a
    box around the disaster; world datasets look places up anywhere (no country preference).
    """
    tweets = ds["tweets"]
    by_name: Dict[str, List[Dict]] = defaultdict(list)
    for t in tweets:
        for n in t.pop("location_names", []):
            by_name[n].append(t)
        # Tweets with their own GPS coordinates in the CSV
        if t["relevant"] and t.get("lat") is not None and t.get("lon") is not None:
            t["locations"].append({"name": "Tweet GPS", "lat": t["lat"], "lon": t["lon"],
                                   "precision": "gps"})

    names = sorted(by_name, key=lambda n: len(by_name[n]), reverse=True)
    store.update_job(job_id, stage="geocoding", places_done=0, places_total=len(names))
    progress = {"done": 0, "lookups": 0}

    def step(n: Optional[str] = None, hit: Optional[Dict] = None):
        if n is not None and hit:
            _add_location(by_name[n], hit)
        progress["done"] += 1
        store.update_job(job_id, places_done=progress["done"])

    # 1. Gazetteer (instant). GPS columns in the CSV are the best hint of where things are.
    points = [(t["lat"], t["lon"], 1) for t in tweets
              if t.get("lat") is not None and t.get("lon") is not None]
    remaining = []
    gaz_hits: Dict[str, Dict] = {}  # applied once the scope is known (see below)
    for n in names:
        hit = geocode.lookup_gazetteer(n)
        if hit:
            gaz_hits[n] = hit
            points.append((hit["lat"], hit["lon"], len(by_name[n])))
        elif geocode.worth_looking_up(n):
            remaining.append(n)
        else:
            step()

    def lookup(n: str, anchor, country_first: bool) -> Optional[Dict]:
        if not geocode.is_cached(n, anchor, country_first):
            if progress["lookups"] >= max_lookups:
                return None
            progress["lookups"] += 1
        return geocode.lookup_nominatim(n, anchor, country_first)

    # 2. Decide scope. Uploads: look up the most-mentioned names anywhere and see how
    #    spread out they are.
    probe_hits: Dict[str, Optional[Dict]] = {}
    if scope == "auto":
        for n in remaining[:SCOPE_PROBE_NAMES]:
            probe_hits[n] = lookup(n, None, country_first=False)
        points += [(h["lat"], h["lon"], len(by_name[n])) for n, h in probe_hits.items() if h]
        # Judge spread by DISTINCT places: one heavily retweeted place mustn't decide it.
        scope = geocode.detect_scope([(la, lo, 1) for la, lo, _ in points])
        log.info("dataset %s scope detected: %s", ds["id"], scope)
    ds["scope"] = scope
    store.update_job(job_id, scope=scope)

    if scope == "world":
        ds["anchor"] = None
        for n, hit in gaz_hits.items():
            step(n, hit)
        for n in remaining:
            hit = probe_hits[n] if n in probe_hits else lookup(n, None, country_first=False)
            step(n, hit)
        return

    # 3. Regional: find the centre of activity, then bound lookups to a box around it.
    anchor = geocode.weighted_anchor(points)
    queue = list(remaining)
    while anchor is None and queue and progress["lookups"] < 10:
        n = queue.pop(0)
        hit = lookup(n, None, country_first=True)
        step(n, hit)
        if hit:
            points.append((hit["lat"], hit["lon"], len(by_name[n])))
            if len(points) >= 3:
                anchor = geocode.weighted_anchor(points)
    if anchor is None:
        anchor = geocode.weighted_anchor(points)
    ds["anchor"] = anchor
    # Gazetteer entries far from this disaster are a different place with the same name
    # ("Queensland" Liquor in Calgary is not Queensland, Australia): look those up
    # again inside the region instead.
    for n, hit in gaz_hits.items():
        if anchor is None or geocode.in_region(hit, anchor):
            step(n, hit)
        else:
            queue.append(n)
    for n in queue:
        step(n, lookup(n, anchor, country_first=True))


def _prefer_specific(tweets: List[Dict]):
    """
    Drop a tweet's city-level point when it also names a place inside that city
    ("Mission, Calgary, AB" makes "Calgary, AB, Canada" redundant). Cuts pin-stacking
    on city centroids without losing tweets that only name the city.
    """
    for t in tweets:
        locs = t.get("locations") or []
        if len(locs) < 2:
            continue
        local_names = [l["name"].lower() for l in locs if l.get("precision") in ("local", "gps")]
        keep = [l for l in locs
                if l.get("precision") != "city"
                or not any(l["name"].split(",")[0].strip().lower() in n for n in local_names)]
        t["locations"] = keep or locs


def _run(job_id: str, dataset_id: str, name: str, tweets: List[Dict], scope: str = "auto"):
    try:
        store.update_job(job_id, status="running", stage="classifying")
        builtin = _builtin(dataset_id)
        if builtin:
            use_llm, max_requests = BUILTIN_USE_LLM, BUILTIN_LLM_MAX_REQUESTS
            scope, max_lookups = builtin.get("scope", "auto"), BUILTIN_GEOCODE_MAX_LOOKUPS
        else:
            use_llm, max_requests = True, LLM_MAX_REQUESTS_PER_DATASET
            max_lookups = GEOCODE_MAX_LOOKUPS
        _classify_all(job_id, tweets, use_llm, max_requests)

        ds = {"id": dataset_id, "name": name, "created_at": time.time(),
              "tweets": tweets, "processing": True, "builtin": bool(builtin)}
        store.publish_dataset(ds)  # tweets & stats are browsable from here on
        store.update_job(job_id, dataset_ready=True)

        _geocode_all(job_id, ds, scope, max_lookups)
        _prefer_specific(tweets)

        ds["processing"] = False
        if builtin:
            ds["fingerprint"] = ai_fingerprint()
            ds["builtin"] = True
            _write_seed(ds, builtin["seed"])
        store.save_dataset(ds)
        store.update_job(job_id, status="done", stage="done")
        log.info("dataset %s processed: %d tweets", dataset_id, len(tweets))
    except Exception as e:  # noqa: BLE001 — surface any failure to the UI
        traceback.print_exc()
        store.update_job(job_id, status="failed", stage="failed", error=str(e))


def _write_seed(ds: Dict, path):
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(ds, f, separators=(",", ":"))
    os.replace(tmp, path)
