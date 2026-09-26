import React, { useState, useMemo, useEffect, useRef } from 'react';
import L from 'leaflet';
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Circle,
  Popup,
  Tooltip,
  useMap,
} from 'react-leaflet';
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import { getMarkerColor, getCategoryBadge, getCategoryDisplay } from '../utils/categories';

// Ensure L is on window for leaflet plugins if needed
if (typeof window !== 'undefined' && !window.L) {
  window.L = L;
}

/** Fly the map to given coords */
function FlyToHandler({ flyTo }) {
  const map = useMap();
  useEffect(() => {
    if (flyTo && flyTo.lat != null && flyTo.lng != null) {
      map.flyTo([flyTo.lat, flyTo.lng], 13, { duration: 1.0 });
    }
  }, [flyTo, map]);
  return null;
}

/** Invalidate map size on container resize to prevent gray gaps */
function InvalidateSizeHandler() {
  const map = useMap();
  useEffect(() => {
    const timer = setTimeout(() => {
      map.invalidateSize();
    }, 150);

    const container = map.getContainer();
    let resizeObserver;
    if (typeof ResizeObserver !== 'undefined' && container) {
      resizeObserver = new ResizeObserver(() => {
        map.invalidateSize();
      });
      resizeObserver.observe(container);
    }

    return () => {
      clearTimeout(timer);
      if (resizeObserver) resizeObserver.disconnect();
    };
  }, [map]);
  return null;
}

/** Auto-fit bounds ONLY once when dataset loads, so manual zooming/panning is preserved */
function FitBoundsToData({ geojson, stats, datasetId }) {
  const map = useMap();
  const lastFittedDatasetId = useRef(null);

  useEffect(() => {
    // Only fit bounds if we haven't already fitted for this dataset
    if (lastFittedDatasetId.current === datasetId) return;
    // Wait for the dataset's real stats: before they load, the map may still be showing
    // demo fallback points (Kashechewan / Thunder Bay) and would lock onto those bounds.
    if (!datasetId || !stats) return;

    const isWorld = stats?.scope === 'world';

    if (!geojson?.features || geojson.features.length === 0) {
      if (isWorld) {
        lastFittedDatasetId.current = datasetId;
        map.setView([20, 0], 2);
      } else if (stats?.anchor) {
        lastFittedDatasetId.current = datasetId;
        map.setView(stats.anchor, 10);
      }
      return;
    }

    try {
      const geoLayer = L.geoJSON(geojson);
      const bounds = geoLayer.getBounds();
      if (bounds && bounds.isValid()) {
        lastFittedDatasetId.current = datasetId;
        map.fitBounds(bounds, {
          padding: [30, 30],
          maxZoom: isWorld ? 6 : 14,
        });
      }
    } catch (err) {
      console.warn('Could not fit bounds to geojson:', err);
    }
  }, [datasetId, geojson, stats?.scope, stats?.anchor, map]);

  return null;
}

/** Smooth Marker Clustering Layer using leaflet.markercluster displaying number count badges */
function ClusterLayer({ geojson, onSelectLocation }) {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    if (!geojson?.features || geojson.features.length === 0) return;

    // Create marker cluster group with number count badge
    const clusterGroup = L.markerClusterGroup({
      maxClusterRadius: 40,
      showCoverageOnHover: false,
      chunkedLoading: true,
      spiderfyOnMaxZoom: true,
      iconCreateFunction: (cluster) => {
        const count = cluster.getChildCount();
        const display = count > 999 ? `${(count / 1000).toFixed(1)}k` : count;
        return L.divIcon({
          html: `<div style="background-color: rgba(24, 24, 27, 0.92); color: #ffffff; width: 32px; height: 32px; border-radius: 9999px; display: flex; align-items: center; justify-content: center; font-family: monospace; font-size: 11px; font-weight: 700; border: 2px solid #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.25);">${display}</div>`,
          className: 'gis-cluster-marker',
          iconSize: L.point(32, 32),
        });
      },
    });

    geojson.features.forEach((feature) => {
      if (!feature.geometry?.coordinates) return;
      const [lng, lat] = feature.geometry.coordinates;
      if (lat == null || lng == null) return;

      const p = feature.properties || {};
      // City-level points (tweet only named the town) are drawn as a CityAreaLayer, not pins.
      if (p.precision === 'city') return;
      const colors = getMarkerColor(p.category);
      const categoryBadge = getCategoryBadge(p.category);
      const categoryLabel = getCategoryDisplay(p.category);
      const severity = p.severity?.toLowerCase();
      const place = p.place || p.location_name || 'Ground Location';

      // Severity badge colors
      let sevClass = 'bg-zinc-100 text-zinc-700 border-zinc-200';
      if (severity === 'critical') sevClass = 'bg-red-950 text-red-200 border-red-800';
      else if (severity === 'high') sevClass = 'bg-red-100 text-red-800 border-red-300';
      else if (severity === 'medium') sevClass = 'bg-amber-100 text-amber-800 border-amber-300';
      else if (severity === 'low') sevClass = 'bg-zinc-100 text-zinc-600 border-zinc-200';

      const marker = L.circleMarker([lat, lng], {
        radius: 6,
        fillColor: colors.fill,
        fillOpacity: 0.9,
        color: '#ffffff',
        weight: 1.5,
        opacity: 1,
      });

      const popupDiv = document.createElement('div');
      popupDiv.className = 'space-y-1.5 text-zinc-900 font-sans';
      popupDiv.innerHTML = `
        <div class="flex items-center gap-1.5 border-b border-zinc-200 pb-1">
          <span class="w-2 h-2 rounded-full shrink-0" style="background-color: ${colors.fill}"></span>
          <span class="font-semibold text-xs text-zinc-900">${place}</span>
        </div>
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="text-[10px] font-mono px-1.5 py-0.2 rounded border ${categoryBadge}">${categoryLabel}</span>
          ${severity ? `<span class="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded border font-semibold ${sevClass}">${severity}</span>` : ''}
          ${p.confidence != null ? `<span class="text-[10px] font-mono text-zinc-500">${(p.confidence * 100).toFixed(0)}% conf</span>` : ''}
        </div>
        <p class="text-xs text-zinc-700 leading-normal pt-0.5">${p.text || p.tweet_text || ''}</p>
        <div class="pt-1 border-t border-zinc-100 flex items-center justify-between gap-1 text-[10px] font-mono">
          <span class="text-zinc-400">${p.created_at ? new Date(p.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
          <button type="button" class="filter-btn text-zinc-700 hover:text-zinc-900 underline font-medium hover:bg-zinc-100 px-1 py-0.5 rounded cursor-pointer">
            Filter feed to this location
          </button>
        </div>
      `;

      const btn = popupDiv.querySelector('.filter-btn');
      if (btn && onSelectLocation) {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          onSelectLocation(place);
        });
      }

      marker.bindPopup(popupDiv, { maxWidth: 300, minWidth: 220 });
      clusterGroup.addLayer(marker);
    });

    map.addLayer(clusterGroup);

    return () => {
      map.removeLayer(clusterGroup);
    };
  }, [geojson, map, onSelectLocation]);

  return null;
}

/**
 * Reports that only name a town/city (precision: "city") have no precise location.
 * Instead of stacking hundreds of pins on the city centre, show one soft area per city
 * with the number of reports.
 */
function CityAreaLayer({ features, isWorld, onSelectLocation }) {
  const areas = useMemo(() => {
    const byPlace = {};
    features.forEach((f) => {
      const p = f.properties || {};
      if (p.precision !== 'city' || !f.geometry?.coordinates) return;
      const [lng, lat] = f.geometry.coordinates;
      if (lat == null || lng == null) return;
      const key = p.place || 'City';
      if (!byPlace[key]) byPlace[key] = { place: key, lat, lng, count: 0, critical: 0 };
      byPlace[key].count += 1;
      if (p.severity === 'critical') byPlace[key].critical += 1;
    });
    return Object.values(byPlace);
  }, [features]);

  return areas.map((a) => {
    const radius = Math.min((isWorld ? 12000 : 3500) + Math.sqrt(a.count) * (isWorld ? 1500 : 450), isWorld ? 60000 : 16000);
    const hasCritical = a.critical > 0;
    return (
      <Circle
        key={`city-${a.place}`}
        center={[a.lat, a.lng]}
        radius={radius}
        pathOptions={{
          color: hasCritical ? '#b91c1c' : '#52525b',
          weight: 1,
          dashArray: '4 4',
          fillColor: hasCritical ? '#ef4444' : '#71717a',
          fillOpacity: 0.08,
        }}
      >
        <Tooltip direction="center" permanent className="city-area-label" opacity={1}>
          {a.count.toLocaleString()}
        </Tooltip>
        <Popup>
          <div className="space-y-1.5 text-zinc-900 font-sans">
            <div className="font-semibold text-xs border-b border-zinc-200 pb-1">{a.place}</div>
            <p className="text-xs text-zinc-700 leading-normal m-0">
              {a.count.toLocaleString()} report{a.count === 1 ? '' : 's'} name only this city, not a precise
              place, so they're shown as an area rather than pins.
              {hasCritical ? ` ${a.critical} marked critical.` : ''}
            </p>
            {onSelectLocation && (
              <button
                type="button"
                className="text-[10px] font-mono text-zinc-700 hover:text-zinc-900 underline font-medium hover:bg-zinc-100 px-1 py-0.5 rounded cursor-pointer"
                onClick={() => onSelectLocation(a.place)}
              >
                Filter feed to this location
              </button>
            )}
          </div>
        </Popup>
      </Circle>
    );
  });
}

/** 100% Free, No-API-Key Light GIS Tile Configurations */
const MAP_STYLES = {
  osm: {
    id: 'osm',
    label: 'OpenStreetMap',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  topo: {
    id: 'topo',
    label: 'Esri Topo',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
    maxZoom: 19,
  },
  satellite: {
    id: 'satellite',
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
    maxZoom: 19,
  },
};

export default function FloodMap({
  geojson,
  showHeatmap,
  flyTo,
  onSelectLocation,
  stats,
  datasetId,
}) {
  const [mapStyle, setMapStyle] = useState('osm');
  const features = geojson?.features || [];

  const isWorld = stats?.scope === 'world';
  const defaultCenter = isWorld ? [20, 0] : (stats?.anchor || [51.05, -114.07]);
  const defaultZoom = isWorld ? 2 : 10;

  // Cluster locations for heatmap concentration circles
  const heatmapData = useMemo(() => {
    const places = {};
    features.forEach((f) => {
      const place = f.properties?.place || f.properties?.location_name || 'Hotspot';
      if (!f.geometry?.coordinates) return;
      const [lng, lat] = f.geometry.coordinates;
      if (lat == null || lng == null) return;
      if (!places[place]) {
        places[place] = { lat, lng, count: 0 };
      }
      // A tweet naming several places contributes 1/n to each, so it counts once overall.
      places[place].count += f.properties?.weight ?? 1;
    });
    return Object.values(places);
  }, [features]);

  const currentTileConfig = MAP_STYLES[mapStyle] || MAP_STYLES.osm;

  return (
    // `isolate` keeps Leaflet's internal z-indexes (400-1000) inside the map, so page overlays
    // (upload progress, toasts) are drawn above it instead of underneath.
    <div className="relative isolate w-full h-full rounded border border-zinc-200 overflow-hidden bg-zinc-100">
      {/* Map Style Switcher (Top-Right Corner) - Utilitarian GIS tabs */}
      <div className="absolute top-2.5 right-2.5 z-[1000] flex items-center bg-white/95 backdrop-blur-sm p-0.5 rounded border border-zinc-300 shadow-sm text-[11px] font-mono">
        {Object.values(MAP_STYLES).map((style) => (
          <button
            key={style.id}
            id={`btn-map-style-${style.id}`}
            type="button"
            onClick={() => setMapStyle(style.id)}
            className={`px-2 py-0.5 rounded transition-colors ${
              mapStyle === style.id
                ? 'bg-zinc-900 text-white font-medium'
                : 'text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100'
            }`}
          >
            {style.label}
          </button>
        ))}
      </div>

      <MapContainer
        center={defaultCenter}
        zoom={defaultZoom}
        minZoom={2}
        maxZoom={19}
        preferCanvas={true}
        className="w-full h-full"
        scrollWheelZoom={true}
        zoomControl={true}
      >
        <TileLayer
          key={mapStyle}
          attribution={currentTileConfig.attribution}
          url={currentTileConfig.url}
          maxZoom={currentTileConfig.maxZoom}
        />
        <InvalidateSizeHandler />
        <FlyToHandler flyTo={flyTo} />
        <FitBoundsToData geojson={geojson} stats={stats} datasetId={datasetId} />

        {/* Heatmap / Activity Concentration Circles */}
        {showHeatmap &&
          heatmapData.map((c, i) => (
            <CircleMarker
              key={`heatmap-${i}`}
              center={[c.lat, c.lng]}
              radius={Math.min(20 + c.count * 6, 60)}
              pathOptions={{
                fillColor: '#3b82f6',
                fillOpacity: 0.12 + Math.min(c.count * 0.04, 0.2),
                color: '#2563eb',
                weight: 1,
                opacity: 0.4,
              }}
            />
          ))}

        {/* City-level reports as one soft area per city (no precise location) */}
        <CityAreaLayer features={features} isWorld={isWorld} onSelectLocation={onSelectLocation} />

        {/* Clustered Feature Markers with Number Count Badges (precise places only) */}
        <ClusterLayer geojson={geojson} onSelectLocation={onSelectLocation} />
      </MapContainer>
    </div>
  );
}
