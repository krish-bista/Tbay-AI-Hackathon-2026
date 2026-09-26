import React, { useEffect, useState } from 'react';
import DisasterFeed from './DisasterFeed';
import { fetchDatasets } from '../../api';
import { FALLBACK_POST_COUNT, getLandingFeed } from '../../data/landingFeed';
import { navigate, ROUTES } from '../../router';

// Entrance order (ms after mount): wordmark, tagline, feed, launch button.
const ENTRANCE = { wordmark: 80, tagline: 350, feed: 900, launch: 1500 };

function useUtcClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now.toISOString().slice(11, 19);
}

export default function LandingPage() {
  const [items, setItems] = useState([]);
  const [postCount, setPostCount] = useState(FALLBACK_POST_COUNT);
  const [shown, setShown] = useState({});
  const clock = useUtcClock();

  useEffect(() => {
    getLandingFeed().then(setItems);
    // Total posts across the built-in datasets, if the backend is reachable.
    fetchDatasets()
      .then((datasets) => {
        const total = (datasets || []).filter((d) => d.builtin).reduce((sum, d) => sum + (d.total || 0), 0);
        if (total > 0) setPostCount(total);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const timers = Object.entries(ENTRANCE).map(([part, delay]) =>
      setTimeout(() => setShown((s) => ({ ...s, [part]: true })), delay),
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  const reveal = (part) => `landing-fade ${shown[part] ? 'is-shown' : ''}`;

  return (
    <div className="landing-page">
      <header className="font-mono flex items-center justify-between px-5 sm:px-8 py-3.5 border-b border-zinc-200 text-[11px] tracking-[0.08em] text-zinc-500">
        <span className="flex items-center gap-2 min-w-0">
          <span className="landing-pulse w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" aria-hidden="true" />
          <span className="truncate">REPLAYING {postCount.toLocaleString()} CLASSIFIED POSTS</span>
        </span>
        <span className="shrink-0 ml-3 hidden sm:inline">{clock} UTC</span>
      </header>

      <main className="flex-1 flex flex-col justify-center py-10 sm:py-14">
        <div className="text-center px-5">
          <h1 className={`landing-wordmark ${reveal('wordmark')}`}>ACHELOUS</h1>
          <p className={`font-mono mt-3 text-[11px] tracking-[0.14em] text-zinc-500 ${reveal('tagline')}`}>
            FLOOD INTELLIGENCE FROM THE GROUND UP
          </p>
        </div>

        <div className={`mt-8 sm:mt-10 ${reveal('feed')}`}>
          {items.length > 0 && <DisasterFeed items={items} running={!!shown.feed} />}
        </div>

        <div className={`text-center px-6 pt-8 sm:pt-10 ${reveal('launch')}`}>
          <button type="button" className="landing-launch" onClick={() => navigate(ROUTES.map)}>
            LAUNCH <span className="landing-launch-arrow" aria-hidden="true">&rarr;</span>
          </button>
        </div>
      </main>
    </div>
  );
}
