"""
Living Flood Map — backend API.

Run locally:  uvicorn app.main:app --reload --port 8000
Interactive docs: http://localhost:8000/docs
"""
import csv
import io
import logging
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

from . import ai, pipeline, store
from .config import (ALLOWED_ORIGINS, DEFAULT_DATASET_ID, FRONTEND_DIST, MAX_SUMMARY_TWEETS,
                     MAX_UPLOAD_MB)
from .csv_loader import CSVError, parse_tweets_csv

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Living Flood Map API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@app.on_event("startup")
def startup():
    store.load_persisted()
    pipeline.ensure_builtin_datasets()  # "sample" (Alberta) and "bonus" (world)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dataset_or_404(dataset_id: str) -> Dict:
    ds = store.get_dataset(dataset_id)
    if ds is None:
        job = store.find_job_for_dataset(dataset_id)
        if job:
            raise HTTPException(409, detail={"message": "Dataset is still processing", "job": job})
        raise HTTPException(404, "Dataset not found")
    return ds


def _relevant_param(value: Optional[str]) -> Optional[bool]:
    """"true" / "false" / "all" (or empty) -> True / False / None."""
    v = (value or "").strip().lower()
    return True if v in ("true", "1", "yes") else False if v in ("false", "0", "no") else None


# UI labels / synonyms -> backend category keys ("Rescue / Help" -> rescue_help).
_CATEGORY_ALIASES = {
    "rescue": "rescue_help", "help": "rescue_help", "rescue help": "rescue_help",
    "request for help": "rescue_help", "medical": "rescue_help", "medical need": "rescue_help",
    "elder home water": "rescue_help",
    "evacuation": "evacuation", "evacuations": "evacuation", "rising water evacuation": "evacuation",
    "infrastructure": "infrastructure_damage", "infrastructure damage": "infrastructure_damage",
    "submerged road bridge": "infrastructure_damage", "damage": "infrastructure_damage",
    "weather": "weather_water_levels", "water": "weather_water_levels",
    "weather water": "weather_water_levels", "weather water levels": "weather_water_levels",
    "official update": "weather_water_levels", "official updates": "weather_water_levels",
    "donations": "donations_volunteering", "donation": "donations_volunteering",
    "volunteering": "donations_volunteering", "donations volunteering": "donations_volunteering",
    "volunteer relief effort": "donations_volunteering", "relief": "donations_volunteering",
    "sympathy": "sympathy_support", "support": "sympathy_support",
    "sympathy support": "sympathy_support", "general concern": "sympathy_support",
    "other": "other_related", "other related": "other_related",
}


def _category_set(value: Optional[str]) -> set:
    """Accept backend keys ("evacuation") and UI labels ("Evacuation", "Rescue / Help")."""
    out = set()
    for raw in _csv_set(value):
        if raw in ai.CATEGORIES:
            out.add(raw)
            continue
        key = " ".join(re.sub(r"[^a-z]+", " ", raw.lower()).split())
        if key.replace(" ", "_") in ai.CATEGORIES:
            out.add(key.replace(" ", "_"))
        elif key in _CATEGORY_ALIASES:
            out.add(_CATEGORY_ALIASES[key])
        else:
            out.add(raw)  # unknown: matches nothing, as before
    return out


def _csv_set(value: Optional[str]) -> set:
    return {v.strip() for v in (value or "").split(",") if v.strip()}


def _filter(tweets: List[Dict], relevant: Optional[bool] = True, category: Optional[str] = None,
            q: Optional[str] = None, location: Optional[str] = None, min_confidence: float = 0.0,
            has_location: Optional[bool] = None, severity: Optional[str] = None,
            disaster_type: Optional[str] = None) -> List[Dict]:
    q = (q or "").lower()
    location = (location or "").lower()
    cats = _category_set(category)
    sevs = {v.lower() for v in _csv_set(severity)}
    dtypes = _csv_set(disaster_type)
    out = []
    for t in tweets:
        if relevant is not None and t["relevant"] != relevant:
            continue
        if cats and t["category"] not in cats:
            continue
        if sevs and t.get("severity") not in sevs:
            continue
        if dtypes and t.get("disaster_type", "none") not in dtypes:
            continue
        if t["confidence"] < min_confidence:
            continue
        if q and q not in t["text"].lower():
            continue
        if location and not any(location in l["name"].lower() for l in t["locations"]):
            continue
        if has_location is not None and bool(t["locations"]) != has_location:
            continue
        out.append(t)
    return out


def _sort(rows: List[Dict], sort: str) -> List[Dict]:
    if sort == "severity":
        return sorted(rows, key=lambda t: (SEVERITY_ORDER.get(t.get("severity"), 9), -t["confidence"]))
    if sort == "confidence":
        return sorted(rows, key=lambda t: -t["confidence"])
    if sort == "time":
        return sorted(rows, key=lambda t: t.get("ts") or "")
    return rows


def _public(t: Dict) -> Dict:
    return {k: t.get(k) for k in ("id", "text", "created_at", "ts", "relevant", "confidence",
                                   "category", "severity", "disaster_type", "reasoning", "ai_source", "locations",
                                   "meta")}


class FilterParams(BaseModel):
    relevant: Optional[bool] = True
    category: Optional[str] = None
    severity: Optional[str] = None
    disaster_type: Optional[str] = None
    q: Optional[str] = None
    location: Optional[str] = None
    min_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ai/status")
def ai_status():
    """Is Gemini actually in use? Use this for the UI's "Gemini Live" badge."""
    return ai.llm_status()


@app.get("/api/categories")
def categories():
    return {"categories": ai.CATEGORIES, "severities": list(SEVERITY_ORDER),
            "disaster_types": ai.DISASTER_TYPES}


@app.post("/api/datasets", status_code=202)
async def upload_dataset(
    file: UploadFile = File(...),
    scope: str = Query("auto", pattern="^(auto|regional|world)$",
                       description="Map scope; auto-detected from place spread by default"),
):
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_MB} MB)")
    try:
        tweets = parse_tweets_csv(raw)
    except CSVError as e:
        raise HTTPException(400, str(e))
    job = pipeline.start(file.filename or "upload.csv", tweets, scope=scope)
    return {"dataset_id": job["dataset_id"], "job_id": job["id"], "total": len(tweets)}


@app.get("/api/datasets")
def list_datasets():
    """Default dataset first, then other built-ins, then uploads (newest first)."""
    return {"default_id": DEFAULT_DATASET_ID, "datasets": store.list_datasets()}


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    """Delete a dataset from memory and disk."""
    if not store.delete_dataset(dataset_id):
        raise HTTPException(404, "Dataset not found")
    return {"status": "deleted", "dataset_id": dataset_id}



@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/datasets/{dataset_id}/tweets")
def get_tweets(
    dataset_id: str,
    relevant: str = Query("true", description="true | false | all"),
    category: Optional[str] = Query(None, description="Comma-separated categories"),
    severity: Optional[str] = Query(None, description="Comma-separated: critical,high,medium,low"),
    disaster_type: Optional[str] = Query(None, description="Comma-separated, e.g. explosion,storm"),
    q: Optional[str] = None,
    location: Optional[str] = None,
    min_confidence: float = 0.0,
    has_location: Optional[bool] = None,
    sort: str = Query("original", pattern="^(original|severity|confidence|time)$"),
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    ds = _get_dataset_or_404(dataset_id)
    rows = _filter(ds["tweets"], _relevant_param(relevant), category, q, location,
                   min_confidence, has_location, severity, disaster_type)
    rows = _sort(rows, sort)
    return {"total": len(rows), "offset": offset, "limit": limit,
            "tweets": [_public(t) for t in rows[offset:offset + limit]]}


@app.get("/api/datasets/{dataset_id}/stats")
def get_stats(dataset_id: str):
    ds = _get_dataset_or_404(dataset_id)
    tweets = ds["tweets"]
    rel = [t for t in tweets if t["relevant"]]
    places = Counter(l["name"] for t in rel for l in t["locations"])
    job = store.find_job_for_dataset(dataset_id)
    return {
        "name": ds["name"],
        "processing": ds.get("processing", False),  # True while map points are still being added
        "job": job,
        "total": len(tweets),
        "relevant": len(rel),
        "unrelated": len(tweets) - len(rel),
        "with_location": sum(1 for t in rel if t["locations"]),
        "by_category": dict(Counter(t["category"] for t in rel).most_common()),
        "by_severity": {s: n for s, n in sorted(Counter(t.get("severity") for t in rel).items(),
                                                key=lambda kv: SEVERITY_ORDER.get(kv[0], 9))},
        "top_locations": [{"name": n, "count": c} for n, c in places.most_common(15)],
        "has_timestamps": any(t.get("ts") for t in tweets),
        "ai_sources": dict(Counter(t.get("ai_source", "rules") for t in tweets)),  # gemini vs rules
        "by_disaster_type": dict(Counter(t.get("disaster_type", "none") for t in tweets).most_common()),
        "scope": ds.get("scope", "regional"),  # "world" -> start the map zoomed out
        "builtin": ds.get("builtin", False),
        "anchor": ds.get("anchor"),  # [lat, lon] centre of activity — good initial map view
    }


@app.get("/api/datasets/{dataset_id}/geojson")
def get_geojson(
    dataset_id: str,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    q: Optional[str] = None,
    location: Optional[str] = None,
    min_confidence: float = 0.0,
):
    """One Point feature per (tweet, location). Drop straight into Leaflet / Mapbox."""
    ds = _get_dataset_or_404(dataset_id)
    rows = _filter(ds["tweets"], True, category, q, location, min_confidence, True, severity)
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [loc["lon"], loc["lat"]]},
            "properties": {"tweet_id": t["id"], "text": t["text"], "category": t["category"],
                           "severity": t.get("severity"), "confidence": t["confidence"],
                           "disaster_type": t.get("disaster_type"),
                           "place": loc["name"], "created_at": t["created_at"], "ts": t.get("ts"),
                           # city = only the town was named (draw as an area, not a precise pin)
                           "precision": loc.get("precision", "local"),
                           # tweets naming several places: weights sum to 1 per tweet (heatmaps)
                           "weight": round(1 / len(t["locations"]), 3),
                           "primary": i == 0},
        }
        for t in rows for i, loc in enumerate(t["locations"])
    ]
    return {"type": "FeatureCollection", "features": features}


@app.get("/api/datasets/{dataset_id}/timeline")
def get_timeline(
    dataset_id: str,
    interval: str = Query("hour", pattern="^(hour|day)$"),
    category: Optional[str] = None,
    severity: Optional[str] = None,
):
    """Tweet counts per hour/day. `available` is false if the CSV had no usable dates."""
    ds = _get_dataset_or_404(dataset_id)
    cut = 13 if interval == "hour" else 10  # ISO prefix: "2013-06-21T10" / "2013-06-21"
    cats, sevs = _category_set(category), {v.lower() for v in _csv_set(severity)}
    buckets: Dict[str, Dict] = defaultdict(lambda: {"total": 0, "relevant": 0, "by_category": Counter()})
    for t in ds["tweets"]:
        if not t.get("ts"):
            continue
        b = buckets[t["ts"][:cut]]
        b["total"] += 1
        if t["relevant"] and (not cats or t["category"] in cats) and (not sevs or t.get("severity") in sevs):
            b["relevant"] += 1
            b["by_category"][t["category"]] += 1
    return {
        "available": bool(buckets),
        "interval": interval,
        "buckets": [{"t": k + (":00:00Z" if interval == "hour" else "T00:00:00Z"),
                     "total": v["total"], "relevant": v["relevant"],
                     "by_category": dict(v["by_category"])}
                    for k, v in sorted(buckets.items())],
    }


@app.get("/api/datasets/{dataset_id}/export.csv")
def export_csv(
    dataset_id: str,
    relevant: str = Query("all", description="true | false | all"),
    category: Optional[str] = None,
    severity: Optional[str] = None,
    disaster_type: Optional[str] = None,
    q: Optional[str] = None,
    location: Optional[str] = None,
    min_confidence: float = 0.0,
):
    """Classified tweets as CSV (all tweets by default). Link to it directly for a download."""
    ds = _get_dataset_or_404(dataset_id)
    rows = _filter(ds["tweets"], _relevant_param(relevant), category, q, location, min_confidence,
                   None, severity, disaster_type)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "text", "created_at", "relevant", "confidence", "category", "severity",
                "disaster_type", "reasoning", "places", "lat", "lon"])
    for t in rows:
        first = t["locations"][0] if t["locations"] else {}
        w.writerow([t["id"], t["text"], t["created_at"] or "", t["relevant"], t["confidence"],
                    t["category"] or "", t.get("severity") or "", t.get("disaster_type") or "",
                    t.get("reasoning") or "",
                    "; ".join(l["name"] for l in t["locations"]), first.get("lat", ""), first.get("lon", "")])
    filename = f"living_flood_map_{dataset_id}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.post("/api/datasets/{dataset_id}/summary")
def get_summary(dataset_id: str, filters: FilterParams):
    ds = _get_dataset_or_404(dataset_id)
    rows = _filter(ds["tweets"], filters.relevant, filters.category, filters.q,
                   filters.location, filters.min_confidence, None, filters.severity,
                   filters.disaster_type)
    # Most urgent and most confident first so the summary is based on the strongest signal.
    rows = _sort(rows, "severity")[:MAX_SUMMARY_TWEETS]
    try:
        summary = ai.summarize([t["text"] for t in rows])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Summary failed: {e}")
    return {"summary": summary, "tweet_count": len(rows)}


class SPAStaticFiles(StaticFiles):
    """Serve index.html for unknown non-API paths so client routes (/map) survive refreshes."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            # Client routes only: never mask missing API calls or asset files.
            last = path.rsplit("/", 1)[-1]
            if e.status_code == 404 and not path.startswith("api") and "." not in last:
                return await super().get_response("index.html", scope)
            raise


# Serve the built frontend at "/" (must be registered after the API routes).
if FRONTEND_DIST.is_dir():
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
