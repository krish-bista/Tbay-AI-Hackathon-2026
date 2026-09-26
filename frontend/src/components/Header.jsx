import React, { useRef } from 'react';
import { Loader2, Trash2 } from 'lucide-react';

export default function Header({
  datasetId,
  datasets = [],
  removedDatasetIds = new Set(),
  onSelectDataset,
  onRemoveDataset,
  onUploadCSV,
  onExportGeoJSON,
  onExportCSV,
  isLoading,
  hasData,
}) {
  const fileInputRef = useRef(null);

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onUploadCSV(file);
      e.target.value = '';
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files?.[0];
    if (file && file.name.endsWith('.csv')) {
      onUploadCSV(file);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Build clean list of datasets including built-ins (filtering out removed ones)
  const datasetOptions = [
    { id: 'sample', label: 'Alberta Floods 2013' },
    { id: 'bonus', label: 'World Disasters (Bonus)' },
  ].filter((d) => !removedDatasetIds?.has(d.id));

  // Merge any dynamically registered / uploaded datasets from backend
  datasets.forEach((d) => {
    if (!removedDatasetIds?.has(d.id) && !datasetOptions.some((opt) => opt.id === d.id)) {
      datasetOptions.push({
        id: d.id,
        label: d.name || `Dataset: ${d.id}`,
        count: d.total,
      });
    }
  });

  return (
    <header className="border-b border-zinc-200 bg-white sticky top-0 z-50 shrink-0">
      <div className="max-w-[1920px] mx-auto px-4 py-2.5">
        <div className="flex items-center justify-between gap-4">
          {/* Brand - Achelous (Clean title, no subtitle, no green dot) */}
          <div className="flex items-center gap-2 shrink-0 select-none">
            <h1 className="text-xl sm:text-2xl font-black text-zinc-900 tracking-wider font-mono leading-none uppercase">
              Achelous
            </h1>
          </div>

          {/* Data Actions - Clean, icon-free minimalist buttons */}
          <div
            className="flex items-center gap-2 flex-wrap justify-end"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
          >
            {/* Dataset Switcher Dropdown with Remove Button */}
            <div className="flex items-center gap-1.5 bg-zinc-50 border border-zinc-300 rounded px-2.5 py-1.5">
              <span className="text-[10px] uppercase font-mono font-semibold text-zinc-500">Dataset:</span>
              <select
                id="select-dataset"
                value={datasetId || ''}
                onChange={(e) => onSelectDataset(e.target.value)}
                disabled={isLoading}
                className="bg-transparent text-xs font-semibold text-zinc-900 focus:outline-none cursor-pointer"
              >
                {datasetOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label} {opt.count ? `(${opt.count.toLocaleString()})` : ''}
                  </option>
                ))}
              </select>
              {isLoading && <Loader2 className="w-3 h-3 animate-spin text-zinc-500 ml-1" />}

              {/* Remove Dataset from Dropdown Button */}
              {onRemoveDataset && datasetOptions.length > 0 && (
                <button
                  id="btn-remove-dataset"
                  type="button"
                  onClick={() => onRemoveDataset(datasetId)}
                  disabled={isLoading}
                  title="Remove this dataset from dropdown"
                  className="ml-1 p-0.5 rounded text-zinc-400 hover:text-red-600 hover:bg-zinc-200/60 transition-colors cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Upload Custom CSV */}
            <button
              id="btn-upload-csv"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
              className="px-3 py-1.5 rounded bg-white hover:bg-zinc-50 border border-zinc-300 text-zinc-700 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              Upload CSV
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleFileSelect}
            />

            {/* Export CSV */}
            <button
              id="btn-export-csv"
              type="button"
              onClick={onExportCSV}
              disabled={!hasData}
              className="px-3 py-1.5 rounded bg-white hover:bg-zinc-50 border border-zinc-300 text-zinc-700 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              title="Download currently filtered tweets as CSV"
            >
              Export CSV
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
