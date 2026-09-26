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
    <div className="grid grid-cols-4 divide-x divide-zinc-200 bg-white">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="p-2 sm:px-2.5 sm:py-2.5 flex flex-col justify-between min-w-0"
        >
          <div className="text-[10px] sm:text-[11px] uppercase tracking-tight text-zinc-500 font-mono font-semibold leading-tight whitespace-normal break-words">
            {m.label}
          </div>
          <div className="mt-1 flex flex-col min-w-0">
            <span className={`text-lg sm:text-xl lg:text-2xl font-bold font-mono tabular-nums ${m.valColor} leading-tight`}>
              {m.value}
            </span>
            {m.sub && (
              <span className="text-[10px] sm:text-[11px] text-zinc-500 font-mono tabular-nums font-medium leading-tight mt-0.5 whitespace-normal break-words">
                {m.sub}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
