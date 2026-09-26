/**
 * API Service for The Living Flood Map
 *
 * Talks to the real backend API documented in backend/README.md.
 *
 * Endpoints used:
 *   GET  /api/health
 *   GET  /api/categories
 *   POST /api/datasets              (upload CSV → returns dataset_id + job_id)
 *   GET  /api/jobs/{job_id}          (poll progress)
 *   GET  /api/datasets              (list previous datasets)
 *   GET  /api/datasets/{id}/stats   (KPI numbers)
 *   GET  /api/datasets/{id}/tweets  (tweet list with filters)
 *   GET  /api/datasets/{id}/geojson (GeoJSON for Leaflet, with filters)
 *   POST /api/datasets/{id}/summary (AI overview, filtered)
 *
 * Base URL comes from VITE_API_URL. If unset: http://localhost:8000 in `npm run dev`,
 * and same-origin in production (the backend serves the built frontend).
 * Fallback data is used only when the backend is completely unreachable.
 */

const API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

// ── Low-level helpers ──────────────────────────────────────────────

async function get(path, params = {}) {
  const url = new URL(`${API}${path}`, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== '') url.searchParams.set(k, v);
  });
  const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`GET ${path} → ${res.status}: ${body}`);
  }
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30000),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

async function postFile(path, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(60000),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Public API ─────────────────────────────────────────────────────

// ── Public API ─────────────────────────────────────────────────────

/** Quick backend connectivity test. */
export async function checkHealth() {
  try {
    await get('/api/health');
    return true;
  } catch {
    return false;
  }
}

/** Check if Gemini LLM is active (for Gemini Live badge). */
export async function fetchAIStatus() {
  try {
    return await get('/api/ai/status');
  } catch {
    return { active: false, enabled: false };
  }
}

/** Fetch available category strings for filter pills. */
export async function fetchCategories() {
  const data = await get('/api/categories');
  return data.categories; // string[]
}

/** List previously processed datasets. */
export async function fetchDatasets() {
  const data = await get('/api/datasets');
  return data.datasets || []; // [{id, name, total, relevant, processing}]
}

/** Upload a CSV file → kicks off async pipeline, returns ids. */
export async function uploadCSV(file) {
  return postFile('/api/datasets', file);
  // → {dataset_id, job_id, total}
}

/** Poll a background job. Resolves when done, rejects on failure. */
export async function pollJob(jobId) {
  const data = await get(`/api/jobs/${jobId}`);
  return data; // {status, stage, processed, total, places_done, places_total, dataset_ready, error?, dataset_id}
}

/**
 * Upload CSV and poll progress every 1s.
 * Passes full job object to `onProgress`.
 * Resolves as soon as `job.dataset_ready === true` OR `job.status === 'done' || job.status === 'completed'`.
 */
export async function uploadAndWait(file, onProgress) {
  const { dataset_id, job_id, total } = await uploadCSV(file);
  onProgress?.({
    status: 'queued',
    stage: 'classifying',
    processed: 0,
    total,
    places_done: 0,
    places_total: 0,
    dataset_ready: false,
    dataset_id,
  });

  // eslint-disable-next-line no-constant-condition
  while (true) {
    await new Promise((r) => setTimeout(r, 1000));
    const job = await pollJob(job_id);
    onProgress?.({
      stage: job.stage,
      processed: job.processed,
      total: job.total,
      places_done: job.places_done ?? 0,
      places_total: job.places_total ?? 0,
      dataset_ready: job.dataset_ready,
      status: job.status,
      dataset_id,
      ...job,
    });
    if (job.dataset_ready === true || job.status === 'done' || job.status === 'completed') {
      return dataset_id;
    }
    if (job.status === 'failed') {
      throw new Error(job.error || 'Job failed');
    }
  }
}

/** KPI stats for a dataset. */
export async function fetchStats(datasetId) {
  return get(`/api/datasets/${datasetId}/stats`);
  // → {name, total, relevant, unrelated, with_location, by_category, by_severity, top_locations, anchor, scope, has_timestamps, processing}
}

/**
 * Filtered tweets with pagination and sort.
 * filters: { relevant, category, severity, disaster_type, location, q, sort, limit, offset, min_confidence, has_location }
 */
export async function fetchTweets(datasetId, filters = {}) {
  const params = {
    limit: 200,
    ...filters,
  };
  return get(`/api/datasets/${datasetId}/tweets`, params);
  // → {total, offset, limit, tweets: [...]}
}

/**
 * GeoJSON FeatureCollection for Leaflet.
 * filters: { category, severity, disaster_type, location, q, min_confidence }
 */
export async function fetchGeoJSON(datasetId, filters = {}) {
  return get(`/api/datasets/${datasetId}/geojson`, filters);
  // → { type: "FeatureCollection", features: [...] }
}

/**
 * Tweet counts per hour/day for timeline chart.
 * filters: { interval: 'hour' | 'day', category, severity }
 */
export async function fetchTimeline(datasetId, params = {}) {
  return get(`/api/datasets/${datasetId}/timeline`, params);
  // → { available, interval, buckets: [{t, total, relevant, by_category}] }
}

/**
 * Get direct download / export URL for filtered tweets as CSV.
 * filters: { relevant, category, severity, disaster_type, location, q, sort }
 */
export function getExportCSVUrl(datasetId, filters = {}) {
  const base = `${API}/api/datasets/${datasetId}/export.csv`;
  const url = new URL(base, window.location.origin);
  const allowed = ['relevant', 'category', 'severity', 'disaster_type', 'location', 'q', 'sort'];
  Object.entries(filters).forEach(([k, v]) => {
    if (allowed.includes(k) && v != null && v !== '') {
      url.searchParams.set(k, v);
    }
  });
  return url.toString();
}

/**
 * AI summary of filtered tweets.
 * filters: { relevant, category, severity, location, q, min_confidence }
 */
export async function fetchSummary(datasetId, filters = {}) {
  return post(`/api/datasets/${datasetId}/summary`, {
    relevant: true,
    ...filters,
  });
  // → {summary, tweet_count}
}

/**
 * Build a downloadable GeoJSON blob from a FeatureCollection object.
 */
/**
 * Build a downloadable GeoJSON blob from a FeatureCollection object.
 */
export function downloadGeoJSON(featureCollection, filename = 'living_flood_map_export.geojson') {
  const blob = new Blob([JSON.stringify(featureCollection, null, 2)], {
    type: 'application/geo+json',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Delete a dataset from backend storage.
 */
export async function deleteDataset(datasetId) {
  try {
    return await request(`/api/datasets/${datasetId}`, { method: 'DELETE' });
  } catch (err) {
    console.warn(`Could not delete dataset ${datasetId} on backend:`, err);
    return null;
  }
}


