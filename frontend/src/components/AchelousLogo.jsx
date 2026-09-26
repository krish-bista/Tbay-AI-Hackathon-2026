import React from 'react';

/**
 * Achelous Logo — Clean, minimalist water crest emblem.
 * Perfectly styled for a modern, utilitarian emergency GIS interface.
 */
export default function AchelousLogo({ size = 32, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 ${className}`}
    >
      <defs>
        <linearGradient id="achelous-base-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0284c7" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="achelous-wave-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
      </defs>

      {/* Outer Circle Ring */}
      <circle
        cx="50"
        cy="50"
        r="46"
        fill="url(#achelous-base-grad)"
        stroke="#0284c7"
        strokeWidth="2"
      />

      {/* Stream Flow Waves */}
      <path
        d="M26 66 C 24 48, 36 34, 46 26 C 42 36, 36 46, 38 58 C 40 66, 32 70, 26 66 Z"
        fill="url(#achelous-wave-grad)"
      />
      <path
        d="M74 66 C 76 48, 64 34, 54 26 C 58 36, 64 46, 62 58 C 60 66, 68 70, 74 66 Z"
        fill="url(#achelous-wave-grad)"
      />

      {/* Center Flow Peak */}
      <path
        d="M50 18 L53 32 L47 32 Z"
        fill="#ffffff"
      />
      <path
        d="M50 22 L55 42 C 55 56, 45 62, 50 76 C 47 68, 48 55, 45 42 Z"
        fill="#38bdf8"
      />

      {/* Lower Basin */}
      <path
        d="M34 70 C 42 64, 48 74, 54 68 C 60 64, 66 70, 70 66 C 64 74, 56 76, 50 80 C 44 76, 38 76, 34 70 Z"
        fill="#e0f2fe"
        opacity="0.8"
      />

      {/* Center Node */}
      <circle cx="50" cy="46" r="3" fill="#ffffff" />
    </svg>
  );
}
