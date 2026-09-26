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
    <div className="grid grid-cols-2 bg-white">
      {metrics.map((m, idx) => (
        <div
          key={m.label}
          className={`p-3 sm:px-4 sm:py-3 flex flex-col justify-between min-w-0 ${
            idx % 2 === 0 ? 'border-r border-zinc-200' : ''
          } ${idx < 2 ? 'border-b border-zinc-200' : ''}`}
        >
          <div className="text-xs uppercase tracking-wider text-zinc-500 font-mono font-semibold leading-tight break-words">
            {m.label}
          </div>
          <div className="mt-1 flex flex-col min-w-0">
            <span className={`text-2xl sm:text-3xl font-bold font-mono tabular-nums ${m.valColor} leading-tight`}>
              {m.value}
            </span>
            {m.sub && (
              <span className="text-xs text-zinc-500 font-mono tabular-nums font-medium leading-tight mt-0.5 break-words">
                {m.sub}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
