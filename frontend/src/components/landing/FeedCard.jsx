import React, { forwardRef } from 'react';
import { MapPin } from 'lucide-react';
import { getMarkerColor } from '../../utils/categories';

// Short labels so "FLOOD · …" fits beside the severity badge on a card.
const CATEGORY_LABELS = {
  rescue_help: 'Rescue',
  infrastructure_damage: 'Damage',
  evacuation: 'Evacuation',
  weather_water_levels: 'Water level',
  donations_volunteering: 'Relief',
  sympathy_support: 'Support',
  other_related: 'Report',
};

const OTHER_LABELS = {
  wildfire: 'Wildfire',
  earthquake: 'Earthquake',
  explosion: 'Explosion',
  storm: 'Storm',
  shooting: 'Shooting',
  haze: 'Haze',
  transport_accident: 'Transport',
};

const SEVERITY = {
  critical: { label: 'Critical', className: 'text-red-800 bg-red-50 border-red-200' },
  high: { label: 'High', className: 'text-orange-800 bg-orange-50 border-orange-200' },
  medium: { label: 'Medium', className: 'text-zinc-700 bg-zinc-100 border-zinc-200' },
  low: { label: 'Low', className: 'text-zinc-600 bg-zinc-50 border-zinc-200' },
};

/** One post in the landing feed. Positioned and animated by DisasterFeed via the ref. */
const FeedCard = forwardRef(function FeedCard({ item, width }, ref) {
  const isFlood = item.kind === 'flood';
  const dot = isFlood ? getMarkerColor(item.category).fill : '#a1a1aa';
  const label = isFlood
    ? `Flood · ${CATEGORY_LABELS[item.category] || 'Report'}`
    : OTHER_LABELS[item.kind] || 'Other';
  const severity = isFlood ? SEVERITY[item.severity] : null;

  return (
    <article ref={ref} className="landing-card" style={{ width }}>
      <div className="flex items-center justify-between gap-2 mb-2.5">
        <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-zinc-600 flex items-center gap-[7px] min-w-0">
          <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: dot }} />
          <span className="truncate">{label}</span>
        </span>
        {severity ? (
          <span className={`text-[11px] px-2 py-0.5 rounded border shrink-0 ${severity.className}`}>
            {severity.label}
          </span>
        ) : (
          <span className="font-mono text-[10px] tracking-[0.06em] text-zinc-400 shrink-0">NOT FLOOD</span>
        )}
      </div>
      <div className="text-zinc-900 text-sm font-medium mb-1.5 flex items-center gap-[5px] min-w-0">
        <MapPin className="w-3.5 h-3.5 text-zinc-500 shrink-0" aria-hidden="true" />
        <span className="truncate">{item.location}</span>
      </div>
      <p className="text-zinc-600 text-[12.5px] leading-[1.5] h-[57px] overflow-hidden m-0">{item.message}</p>
      <div className="font-mono text-[10.5px] text-zinc-400 mt-3 pt-[9px] border-t border-zinc-100">{item.source}</div>
    </article>
  );
});

export default FeedCard;
