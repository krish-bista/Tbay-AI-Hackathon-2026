import React, { useState, useMemo, useCallback, useEffect } from 'react';
import Header from './components/Header';
import KPIStrip from './components/KPIStrip';
import FloodMap from './components/FloodMap';
import TweetFeed from './components/TweetFeed';
import {
  checkHealth,
  fetchAIStatus,
  fetchCategories,
  fetchDatasets,
  fetchStats,
  fetchTweets,
  fetchGeoJSON,
  fetchTimeline,
  getExportCSVUrl,
  fetchSummary,
  uploadAndWait,
  downloadGeoJSON,
  deleteDataset,
} from './api';
import { FALLBACK_TWEETS, FALLBACK_SUMMARY } from './data/fallbackData';
import { Loader2 } from 'lucide-react';
import { matchesCategory } from './utils/categories';

/** Default dataset id the backend auto-creates from the provided CSV. */
const SAMPLE_DATASET_ID = 'sample';

export default function App() {
  // ── Connection & loading state ──
  const [backendOnline, setBackendOnline] = useState(null); // null = checking
  const [aiActive, setAiActive] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [jobProgress, setJobProgress] = useState(null); // {status, stage, processed, total, places_done, places_total, dataset_ready}

  // ── Active dataset ──
  const [datasetId, setDatasetId] = useState(SAMPLE_DATASET_ID);
  const [datasets, setDatasets] = useState([]);
  const [removedDatasetIds, setRemovedDatasetIds] = useState(new Set());
  const [dataSource, setDataSource] = useState('fallback'); // 'backend' | 'upload' | 'fallback'

  // ── Data from backend ──
  const [stats, setStats] = useState(null);
  const [signalTweets, setSignalTweets] = useState([]);
  const [noiseTweets, setNoiseTweets] = useState([]);
  const [signalTotal, setSignalTotal] = useState(0);
  const [noiseTotal, setNoiseTotal] = useState(0);
  const [geojson, setGeojson] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [summary, setSummary] = useState(FALLBACK_SUMMARY);
  const [categories, setCategories] = useState([]);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  // ── Active tab (signal vs noise) ──
  const [activeTab, setActiveTab] = useState('signal');

  // ── Filters & pagination ──
  const [filterCategory, setFilterCategory] = useState('');
  const [filterSearch, setFilterSearch] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [filterHasLocation, setFilterHasLocation] = useState(null);
  const [filterDisasterType, setFilterDisasterType] = useState('');
  const [filterSort, setFilterSort] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 200;

  // Auto-reset all filter states back to default
  const resetFilters = useCallback(() => {
    setActiveTab('signal');
    setFilterCategory('');
    setFilterSearch('');
    setFilterLocation('');
    setFilterHasLocation(null);
    setFilterDisasterType('');
    setFilterSort('');
    setOffset(0);
  }, []);

  const handleSelectLocation = useCallback((loc) => {
    setFilterLocation((prev) => (prev === loc ? '' : loc));
    setActiveTab('signal');
    setOffset(0);
  }, []);

  // ── Fallback mode data ──
  const [useFallback, setUseFallback] = useState(true);

  // ── Map state ──
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [flyTo, setFlyTo] = useState(null);

  // ── Toast ──
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = useCallback((msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4500);
  }, []);

  // ── Fallback-mode derived data ──
  const fallbackRelevant = useMemo(() => FALLBACK_TWEETS.filter((t) => t.is_relevant), []);
  const fallbackNoise = useMemo(() => FALLBACK_TWEETS.filter((t) => !t.is_relevant), []);
  const fallbackMapped = useMemo(
    () => fallbackRelevant.filter((t) => t.lat != null && t.lng != null),
    [fallbackRelevant]
  );

  const fallbackFilteredRelevant = useMemo(() => {
    return fallbackRelevant.filter((t) => {
      if (filterLocation && !(t.location_name || '').toLowerCase().includes(filterLocation.toLowerCase())) {
        return false;
      }
      if (filterCategory && !matchesCategory(t.impact_category || '', filterCategory)) {
        return false;
      }
      if (filterSearch.trim()) {
        const q = filterSearch.toLowerCase();
        const text = (t.tweet_text || '').toLowerCase();
        const loc = (t.location_name || '').toLowerCase();
        if (!text.includes(q) && !loc.includes(q)) return false;
      }
      if (filterHasLocation && (t.lat == null || t.lng == null)) {
        return false;
      }
      return true;
    });
  }, [fallbackRelevant, filterLocation, filterCategory, filterSearch, filterHasLocation]);

  const fallbackFilteredMapped = useMemo(() => {
    return fallbackMapped.filter((t) => {
      if (filterLocation && !(t.location_name || '').toLowerCase().includes(filterLocation.toLowerCase())) {
        return false;
      }
      if (filterCategory && !matchesCategory(t.impact_category || '', filterCategory)) {
        return false;
      }
      if (filterSearch.trim()) {
        const q = filterSearch.toLowerCase();
        const text = (t.tweet_text || '').toLowerCase();
        const loc = (t.location_name || '').toLowerCase();
        if (!text.includes(q) && !loc.includes(q)) return false;
      }
      return true;
    });
  }, [fallbackMapped, filterLocation, filterCategory, filterSearch]);

  // Build a client-side GeoJSON from fallback data for export / map
  const fallbackGeoJSON = useMemo(() => ({
    type: 'FeatureCollection',
    features: fallbackFilteredMapped.map((t) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [t.lng, t.lat] },
      properties: {
        tweet_id: t.id,
        text: t.tweet_text,
        category: t.impact_category,
        confidence: 1.0,
        place: t.location_name,
        created_at: t.timestamp,
      },
    })),
  }), [fallbackFilteredMapped]);

  // ── Load a dataset by id from the backend ──
  const loadDataset = useCallback(async (dsId, source = 'backend') => {
    resetFilters();
    setIsLoading(true);
    setUseFallback(false);
    try {
      const [st, signalRes, noiseRes, gj] = await Promise.all([
        fetchStats(dsId),
        fetchTweets(dsId, { relevant: true, limit: 200, offset: 0 }),
        fetchTweets(dsId, { relevant: false, limit: 200, offset: 0 }),
        fetchGeoJSON(dsId),
      ]);
      setStats(st);
      setSignalTweets(signalRes.tweets || []);
      setNoiseTweets(noiseRes.tweets || []);
      setSignalTotal(signalRes.total ?? st.relevant ?? (signalRes.tweets || []).length);
      setNoiseTotal(noiseRes.total ?? st.noise ?? st.unrelated ?? (noiseRes.tweets || []).length);
      setGeojson(gj);
      setDatasetId(dsId);
      setDataSource(source);

      // Load timeline if dataset contains timestamped tweets
      if (st.has_timestamps) {
        fetchTimeline(dsId).then(setTimeline).catch(() => setTimeline(null));
      } else {
        setTimeline(null);
      }

      showToast({ type: 'success', text: `Dataset "${st.name || dsId}" loaded — ${st.total.toLocaleString()} tweets.` });
    } catch (err) {
      if (err.message?.includes('409')) {
        showToast({ type: 'info', text: 'Dataset is still processing in the background.' });
      } else {
        showToast({ type: 'warning', text: `Could not load dataset "${dsId}": ${err.message}` });
      }
    } finally {
      setIsLoading(false);
    }
  }, [resetFilters, showToast]);

  // ── Remove a dataset from dropdown ──
  const handleRemoveDataset = useCallback(async (idToRemove) => {
    if (!idToRemove) return;
    const confirmDelete = window.confirm(`Remove dataset "${idToRemove}" from the dropdown?`);
    if (!confirmDelete) return;

    deleteDataset(idToRemove);

    setDatasets((prev) => prev.filter((d) => d.id !== idToRemove));
    setRemovedDatasetIds((prev) => {
      const updated = new Set(prev);
      updated.add(idToRemove);
      return updated;
    });

    const remainingBuiltins = ['sample', 'bonus'].filter((id) => id !== idToRemove && !removedDatasetIds.has(id));
    const remainingUploads = datasets.filter((d) => d.id !== idToRemove && !removedDatasetIds.has(d.id));
    const nextId = remainingBuiltins[0] || remainingUploads[0]?.id;

    if (nextId) {
      await loadDataset(nextId, 'backend');
    } else {
      setUseFallback(true);
      setDatasetId('');
      setDataSource('fallback');
      setStats(null);
      setSignalTweets([]);
      setNoiseTweets([]);
      setGeojson(null);
    }

    showToast({ type: 'info', text: `Dataset "${idToRemove}" removed from dropdown.` });
  }, [datasets, removedDatasetIds, loadDataset, showToast]);

  // ── Startup: check backend health, AI status, and list datasets ──
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await checkHealth();
      if (cancelled) return;
      setBackendOnline(ok);
      if (ok) {
        // AI status for Gemini Live badge
        try {
          const aiStat = await fetchAIStatus();
          if (!cancelled) setAiActive(aiStat.active === true);
        } catch { /* ignore */ }

        // Categories & datasets list
        try {
          const [cats, dsList] = await Promise.all([
            fetchCategories().catch(() => []),
            fetchDatasets().catch(() => []),
          ]);
          if (!cancelled) {
            setCategories(cats);
            setDatasets(dsList);
          }
        } catch { /* ignore */ }

        // Auto-load sample dataset
        try {
          await loadDataset(SAMPLE_DATASET_ID, 'backend');
        } catch {
          if (!cancelled) {
            setUseFallback(true);
            setDataSource('fallback');
            setSummary(FALLBACK_SUMMARY);
          }
        }
      } else {
        setUseFallback(true);
        setDataSource('fallback');
        setSummary(FALLBACK_SUMMARY);
        showToast({ type: 'warning', text: 'Backend offline — loaded built-in demo dataset.' });
      }
    })();
    return () => { cancelled = true; };
  }, [loadDataset, showToast]);

  // ── LIVE GEOCODING REFRESH: poll every 5s while stats.processing === true ──
  useEffect(() => {
    if (!stats?.processing || !datasetId || useFallback) return;

    const interval = setInterval(async () => {
      try {
        const [newStats, newGj] = await Promise.all([
          fetchStats(datasetId),
          fetchGeoJSON(datasetId, {
            category: filterCategory,
            location: filterLocation,
            disaster_type: filterDisasterType,
            q: filterSearch,
          }),
        ]);
        setStats(newStats);
        setGeojson(newGj);
      } catch {
        /* best-effort live geocoding refresh */
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [stats?.processing, datasetId, useFallback, filterCategory, filterLocation, filterDisasterType, filterSearch]);

  // ── Reload tweets and geojson when filters, disaster type, sort, or pagination change ──
  useEffect(() => {
    if (!datasetId || useFallback) return;
    let cancelled = false;

    const params = {
      relevant: activeTab === 'signal' ? 'true' : 'false',
      limit,
      offset,
    };
    if (filterCategory && activeTab === 'signal') params.category = filterCategory;
    if (filterSearch) params.q = filterSearch;
    if (filterLocation) params.location = filterLocation;
    if (filterHasLocation != null) params.has_location = filterHasLocation;
    if (filterDisasterType && activeTab === 'noise') params.disaster_type = filterDisasterType;
    if (filterSort) params.sort = filterSort;

    const geoParams = {};
    if (filterCategory) geoParams.category = filterCategory;
    if (filterSearch) geoParams.q = filterSearch;
    if (filterLocation) geoParams.location = filterLocation;
    if (filterDisasterType) geoParams.disaster_type = filterDisasterType;

    const reload = async () => {
      try {
        const [tweetsRes, gj] = await Promise.all([
          fetchTweets(datasetId, params),
          fetchGeoJSON(datasetId, geoParams),
        ]);
        if (cancelled) return;
        if (activeTab === 'signal') {
          setSignalTweets(tweetsRes.tweets || []);
          setSignalTotal(tweetsRes.total ?? (tweetsRes.tweets || []).length);
        } else {
          setNoiseTweets(tweetsRes.tweets || []);
          setNoiseTotal(tweetsRes.total ?? (tweetsRes.tweets || []).length);
        }
        setGeojson(gj);
      } catch {
        /* best-effort filter reload */
      }
    };

    const timer = setTimeout(reload, filterSearch ? 250 : 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [datasetId, useFallback, activeTab, filterCategory, filterSearch, filterLocation, filterHasLocation, filterDisasterType, filterSort, offset]);

  // ── Handlers ──

  const handleUploadCSV = async (file) => {
    resetFilters();
    if (!backendOnline) {
      showToast({ type: 'error', text: 'Backend is offline — cannot process CSV. Start the backend first.' });
      return;
    }
    setIsLoading(true);
    setJobProgress({ status: 'uploading', stage: 'uploading', processed: 0, total: 0, places_done: 0, places_total: 0, dataset_ready: false });
    try {
      const dsId = await uploadAndWait(file, (progress) => {
        setJobProgress(progress);
        // If dataset is ready, dismiss blocking overlay early so user can interact
        if (progress.dataset_ready) {
          setIsLoading(false);
        }
      });
      setJobProgress(null);
      await loadDataset(dsId, 'upload');

      // Refresh list of datasets
      fetchDatasets().then(setDatasets).catch(() => {});
      showToast({ type: 'success', text: `CSV "${file.name}" ready!` });
    } catch (err) {
      setJobProgress(null);
      showToast({ type: 'error', text: `CSV upload failed: ${err.message}` });
    } finally {
      setIsLoading(false);
    }
  };

  const handleExportGeoJSON = async () => {
    try {
      let gj;
      if (useFallback) {
        gj = fallbackGeoJSON;
      } else if (datasetId) {
        gj = await fetchGeoJSON(datasetId, {
          category: filterCategory,
          location: filterLocation,
          disaster_type: filterDisasterType,
          q: filterSearch,
        });
      } else {
        gj = fallbackGeoJSON;
      }
      downloadGeoJSON(gj);
      showToast({ type: 'success', text: 'GeoJSON exported for MapAki!' });
    } catch (err) {
      showToast({ type: 'error', text: `Export failed: ${err.message}` });
    }
  };

  const handleExportCSV = () => {
    if (useFallback || !datasetId) {
      showToast({ type: 'info', text: 'CSV export available for active backend datasets.' });
      return;
    }
    const filters = {
      relevant: activeTab === 'signal' ? 'true' : 'false',
      category: filterCategory,
      disaster_type: filterDisasterType,
      location: filterLocation,
      q: filterSearch,
      sort: filterSort,
    };
    const exportUrl = getExportCSVUrl(datasetId, filters);
    window.open(exportUrl, '_blank');
    showToast({ type: 'success', text: 'Downloading filtered tweets as CSV...' });
  };

  // QUOTA RULE: only called on explicit user button click!
  const handleRequestSummary = async () => {
    setIsLoadingSummary(true);
    if (backendOnline && datasetId && !useFallback) {
      try {
        const params = {
          relevant: activeTab === 'signal',
        };
        if (filterCategory) params.category = filterCategory;
        if (filterSearch) params.q = filterSearch;
        if (filterLocation) params.location = filterLocation;
        const res = await fetchSummary(datasetId, params);
        setSummary(res.summary);
        showToast({ type: 'success', text: `AI summary generated from ${res.tweet_count} verified signals.` });
      } catch (err) {
        showToast({ type: 'warning', text: `Summary request: ${err.message}` });
      } finally {
        setIsLoadingSummary(false);
      }
    } else {
      setTimeout(() => {
        setIsLoadingSummary(false);
        setSummary(
          `ACTIVE FLOOD SITUATION OVERVIEW (${new Date().toLocaleTimeString()}) — ` +
          'Kashechewan First Nation, Red Earth Cree Nation, and Peguis First Nation remain under high-priority flood advisories. ' +
          '12 verified signals identify active dike breaching, contaminated water intakes, isolated road washouts, and submerged bridge crossings. ' +
          'Emergency priority: rapid aerial medical evacuation for vulnerable elders and clean water airlift logistics.'
        );
        showToast({ type: 'success', text: 'AI situation summary re-generated from active flood signals!' });
      }, 500);
    }
  };

  const handleFlyTo = useCallback((coords) => {
    setFlyTo({ ...coords, _ts: Date.now() });
  }, []);

  // ── Determine what data to show in each section ──

  const displaySignal = useFallback ? fallbackFilteredRelevant : signalTweets;
  const displayNoise = useFallback ? fallbackNoise : noiseTweets;
  const displaySignalTotal = useFallback ? fallbackRelevant.length : (signalTotal || stats?.relevant || signalTweets.length);
  const displayNoiseTotal = useFallback ? fallbackNoise.length : (noiseTotal || stats?.noise || stats?.unrelated || noiseTweets.length);
  const displayGeoJSON = useFallback ? fallbackGeoJSON : geojson;

  // KPI values
  const kpiTotal = useFallback ? FALLBACK_TWEETS.length : (stats?.total ?? 0);
  const kpiRelevant = useFallback ? fallbackRelevant.length : (stats?.relevant ?? 0);
  const kpiNoise = useFallback ? fallbackNoise.length : (stats?.unrelated ?? 0);
  const kpiWithLocation = useFallback ? fallbackMapped.length : (stats?.with_location ?? 0);
  const kpiTopLocations = useFallback
    ? (() => {
        const c = {};
        fallbackMapped.forEach((t) => { c[t.location_name] = (c[t.location_name] || 0) + 1; });
        return Object.entries(c).sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count }));
      })()
    : (stats?.top_locations ?? []);
  const kpiByCategory = useFallback
    ? (() => {
        const c = {};
        fallbackRelevant.forEach((t) => { if (t.impact_category) c[t.impact_category] = (c[t.impact_category] || 0) + 1; });
        return c;
      })()
    : (stats?.by_category ?? {});

  return (
    <div className="h-screen overflow-hidden bg-zinc-50 text-zinc-900 flex flex-col font-sans selection:bg-zinc-900 selection:text-white">
      {/* Header */}
      <Header
        datasetId={datasetId}
        datasets={datasets}
        removedDatasetIds={removedDatasetIds}
        onSelectDataset={(newId) => loadDataset(newId, 'backend')}
        onRemoveDataset={handleRemoveDataset}
        onUploadCSV={handleUploadCSV}
        onExportCSV={handleExportCSV}
        onExportGeoJSON={handleExportGeoJSON}
        isLoading={isLoading}
        hasData={useFallback || datasetId != null}
      />

      {/* Toast */}
      {toastMessage && (
        <div className="fixed bottom-4 right-4 z-50 animate-fade-in">
          <div
            className={`px-3 py-2 rounded text-xs font-mono border shadow-md flex items-center gap-2 ${
              toastMessage.type === 'success'
                ? 'bg-zinc-900 text-white border-zinc-700'
                : toastMessage.type === 'warning'
                ? 'bg-amber-50 text-amber-900 border-amber-300'
                : toastMessage.type === 'error'
                ? 'bg-red-50 text-red-900 border-red-300'
                : 'bg-zinc-900 text-white border-zinc-700'
            }`}
          >
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}

      {/* Job Progress Overlay (Dismissed immediately once dataset_ready === true) */}
      {jobProgress && jobProgress.status !== 'done' && !jobProgress.dataset_ready && (
        <div className="fixed inset-0 z-40 bg-zinc-900/40 backdrop-blur-[2px] flex items-center justify-center">
          <div className="bg-white rounded border border-zinc-300 p-6 max-w-sm w-full mx-4 shadow-xl text-center space-y-3">
            <Loader2 className="w-8 h-8 text-zinc-700 animate-spin mx-auto" />
            <h3 className="text-base font-bold text-zinc-900">Processing Dataset Pipeline</h3>
            <p className="text-xs text-zinc-600 uppercase tracking-wider font-mono">
              Stage: <strong className="text-zinc-900">{jobProgress.stage || jobProgress.status}</strong>
            </p>
            {jobProgress.total > 0 && (
              <>
                <div className="w-full bg-zinc-100 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-zinc-900 h-1.5 transition-all duration-300"
                    style={{ width: `${Math.round((jobProgress.processed / jobProgress.total) * 100)}%` }}
                  />
                </div>
                <p className="text-[11px] text-zinc-500 font-mono tabular-nums">
                  {jobProgress.processed.toLocaleString()} / {jobProgress.total.toLocaleString()} tweets
                </p>
              </>
            )}
            {jobProgress.places_total > 0 && (
              <p className="text-[10px] text-zinc-400 font-mono tabular-nums">
                Geocoding: {jobProgress.places_done.toLocaleString()} / {jobProgress.places_total.toLocaleString()} places
              </p>
            )}
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="flex-1 min-h-0 overflow-hidden p-2 sm:px-4 max-w-[1920px] w-full mx-auto">
        {/* Split Workspace: Map + Right Panel (KPIs & Tweets) */}
        <div className="h-full min-h-0 overflow-hidden grid grid-cols-12 gap-3">
          {/* Map Panel (Left Column - Extended upwards) */}
          <div className="col-span-12 lg:col-span-7 xl:col-span-8 h-full min-h-0 overflow-hidden flex flex-col gap-1.5">
            {/* Map Toolbar & Legend */}
            <div className="flex items-center justify-between gap-2 text-xs flex-wrap shrink-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-zinc-900 text-xs">
                  {stats?.scope === 'world' ? 'World Disaster Map' : 'Flood Map'}
                </span>
                {displayGeoJSON && (
                  <span className="text-[11px] font-mono tabular-nums text-zinc-500 font-normal">
                    ({displayGeoJSON.features?.length ?? 0} points)
                  </span>
                )}
                {stats?.scope === 'world' && (
                  <span className="text-[10px] font-mono bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.2 rounded">
                    World View
                  </span>
                )}
              </div>

              {/* Map Legend */}
              <div className="flex items-center gap-3 text-[11px] text-zinc-600 bg-white px-2 py-0.5 rounded border border-zinc-200">
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#ef4444]" />
                  <span>Rescue / Help</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#f97316]" />
                  <span>Infrastructure</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#eab308]" />
                  <span>Evacuation</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3b82f6]" />
                  <span>Weather / Water</span>
                </span>
              </div>

              <button
                id="btn-toggle-heatmap"
                type="button"
                onClick={() => setShowHeatmap(!showHeatmap)}
                className={`px-2 py-0.5 rounded border text-[11px] font-mono transition-colors cursor-pointer ${
                  showHeatmap
                    ? 'bg-zinc-900 text-white border-zinc-900'
                    : 'bg-white text-zinc-700 border-zinc-300 hover:bg-zinc-50'
                }`}
              >
                {showHeatmap ? 'Concentration: ON' : 'Concentration: OFF'}
              </button>
            </div>

            {/* Map Canvas */}
            <div className="flex-1 min-h-0 overflow-hidden">
              <FloodMap
                geojson={displayGeoJSON}
                showHeatmap={showHeatmap}
                flyTo={flyTo}
                onSelectLocation={handleSelectLocation}
                stats={stats}
                datasetId={datasetId}
              />
            </div>
          </div>

          {/* Right Column: KPIs above Tweet Feed */}
          <div className="col-span-12 lg:col-span-5 xl:col-span-4 h-full min-h-0 overflow-hidden flex flex-col gap-2">
            {/* KPI Strip */}
            <div className="bg-white border border-zinc-200 rounded shadow-xs shrink-0 overflow-hidden">
              <KPIStrip
                total={kpiTotal}
                relevant={kpiRelevant}
                noise={kpiNoise}
                withLocation={kpiWithLocation}
                topLocations={kpiTopLocations}
              />
            </div>

            {/* Tweet Feed Panel */}
            <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
              <TweetFeed
                signalTweets={displaySignal}
                noiseTweets={displayNoise}
                signalTotal={displaySignalTotal}
                noiseTotal={displayNoiseTotal}
                categories={categories}
                stats={stats}
                useFallback={useFallback}
                onFlyTo={handleFlyTo}
                filterCategory={filterCategory}
                setFilterCategory={setFilterCategory}
                filterSearch={filterSearch}
                setFilterSearch={setFilterSearch}
                filterLocation={filterLocation}
                setFilterLocation={setFilterLocation}
                filterHasLocation={filterHasLocation}
                setFilterHasLocation={setFilterHasLocation}
                filterDisasterType={filterDisasterType}
                setFilterDisasterType={setFilterDisasterType}
                filterSort={filterSort}
                setFilterSort={setFilterSort}
                offset={offset}
                setOffset={setOffset}
                limit={limit}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
              />
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-200 bg-white py-1.5 px-4 text-xs text-zinc-500 font-mono tabular-nums shrink-0">
        <div className="max-w-[1920px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-1">
          <p>&copy; 2026 CE Strategies &bull; ThunderBay AI Emergency Intelligence</p>
        </div>
      </footer>
    </div>
  );
}
