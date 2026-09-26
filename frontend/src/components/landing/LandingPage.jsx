import React, { useEffect, useState } from 'react';
import DisasterFeed from './DisasterFeed';
import { getLandingFeed } from '../../data/landingFeed';
import { navigate, ROUTES } from '../../router';

// Entrance order (ms after mount): wordmark, tagline, feed, launch button.
const ENTRANCE = { wordmark: 80, tagline: 350, feed: 900, launch: 1500 };

export default function LandingPage() {
  const [items, setItems] = useState([]);
  const [shown, setShown] = useState({});

  useEffect(() => {
    getLandingFeed().then(setItems);
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
