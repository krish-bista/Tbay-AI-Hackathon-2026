import React from 'react';

export default function KPIStrip({ total, relevant, noise, withLocation, topLocations }) {
  const relevantPct = total > 0 ? ((relevant / total) * 100).toFixed(1) : '0.0';
  const noisePct = total > 0 ? ((noise / total) * 100).toFixed(1) : '0.0';
  const hotspotLocation = topLocations?.[0]?.name || 'Calgary, AB, Canada';

  const metrics = [
    {
      label: 'Total Tweets',
      value: (total ?? 0).toLocaleString(),
      sub: 'Processed dataset',
      valColor: 'text-zinc-900',
    },
    {
      label: 'Relevant Signal',
      value: (relevant ?? 0).toLocaleString(),
      sub: `${relevantPct}% of total`,
      valColor: 'text-emerald-700',
    },
    {
      label: 'Noise Filtered',
      value: (noise ?? 0).toLocaleString(),
      sub: `${noisePct}% excluded`,
      valColor: 'text-amber-700',
    },
    {
      label: 'Mapped Ground Points',
      value: (withLocation ?? 0).toLocaleString(),
      sub: hotspotLocation,
      valColor: 'text-blue-700',
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-y sm:divide-y-0 divide-zinc-200 bg-white">
      {metrics.map((m) => (
        <div key={m.label} className="p-3 sm:px-3.5 sm:py-3 flex flex-col justify-between min-w-0">
          <div className="text-[11px] sm:text-xs uppercase tracking-wider text-zinc-500 font-mono font-semibold truncate leading-tight">
            {m.label}
          </div>
          <div className="mt-1.5 flex flex-col min-w-0">
            <span className={`text-xl sm:text-2xl lg:text-[26px] font-bold font-mono tabular-nums ${m.valColor} leading-tight`}>
              {m.value}
            </span>
            {m.sub && (
              <span
                className="text-[11px] sm:text-xs text-zinc-500 font-mono tabular-nums font-medium leading-tight mt-1 truncate"
                title={m.label === 'Mapped Ground Points' ? `Top Hotspot: ${m.sub}` : m.sub}
              >
                {m.sub}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
