/**
 * Minimal pathname router (no dependency): "/" = landing page, "/map" = dashboard.
 * The backend serves index.html for unknown non-API paths, so deep links and
 * refreshes on /map work in production too.
 */
import { useEffect, useState } from 'react';

export const ROUTES = { landing: '/', map: '/map' };

export function navigate(to) {
  if (window.location.pathname === to) return;
  window.history.pushState({}, '', to);
  window.dispatchEvent(new PopStateEvent('popstate'));
  window.scrollTo(0, 0);
}

export function usePathname() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onChange = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onChange);
    return () => window.removeEventListener('popstate', onChange);
  }, []);
  return path;
}
