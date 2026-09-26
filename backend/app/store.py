"""
In-memory storage for datasets and jobs, with finished datasets persisted to
data/datasets/<id>.json so they survive restarts.
"""
import json
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

from .config import DATASETS_DIR, DEFAULT_DATASET_ID

_lock = threading.Lock()
datasets: Dict[str, Dict] = {}  # id -> {"id", "name", "created_at", "tweets": [...]}
jobs: Dict[str, Dict] = {}      # id -> {"id", "dataset_id", "status", "stage", "processed", "total", "error"}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def publish_dataset(ds: Dict):
    """Make a dataset queryable (in memory) before it is finished."""
    with _lock:
        datasets[ds["id"]] = ds


def save_dataset(ds: Dict):
    publish_dataset(ds)
    path = DATASETS_DIR / f"{ds['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ds))
    os.replace(tmp, path)


def get_dataset(dataset_id: str) -> Optional[Dict]:
    return datasets.get(dataset_id)


def list_datasets() -> List[Dict]:
    return [
        {"id": d["id"], "name": d["name"], "created_at": d["created_at"],
         "processing": d.get("processing", False), "builtin": d.get("builtin", False),
         "default": d["id"] == DEFAULT_DATASET_ID,
         "scope": d.get("scope", "regional"),
         "total": len(d["tweets"]), "relevant": sum(1 for t in d["tweets"] if t.get("relevant"))}
        for d in sorted(datasets.values(), key=lambda d: (d["id"] != DEFAULT_DATASET_ID,
                                                          not d.get("builtin"), -d["created_at"]))
    ]


def load_persisted():
    for path in DATASETS_DIR.glob("*.json"):
        try:
            ds = json.loads(path.read_text())
            datasets[ds["id"]] = ds
        except (ValueError, KeyError):
            continue


def create_job(dataset_id: str, total: int) -> Dict:
    job = {"id": new_id(), "dataset_id": dataset_id, "status": "queued", "stage": "queued",
           "processed": 0, "total": total, "ai_failed": 0, "dataset_ready": False,
           "places_done": 0, "places_total": 0, "error": None, "started_at": time.time()}
    with _lock:
        jobs[job["id"]] = job
    return job


def update_job(job_id: str, **fields):
    with _lock:
        jobs[job_id].update(fields)


def find_job_for_dataset(dataset_id: str) -> Optional[Dict]:
    for j in jobs.values():
        if j["dataset_id"] == dataset_id and j["status"] in ("queued", "running"):
            return j
    return None


def delete_dataset(dataset_id: str) -> bool:
    with _lock:
        removed = datasets.pop(dataset_id, None)
        path = DATASETS_DIR / f"{dataset_id}.json"
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        return removed is not None

