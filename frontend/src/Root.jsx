import App from './App.jsx'
import LandingPage from './components/landing/LandingPage.jsx'
import { ROUTES, usePathname } from './router.js'

/** "/" = landing page, "/map" = dashboard. */
export default function Root() {
  const path = usePathname()
  return path.startsWith(ROUTES.map) ? <App /> : <LandingPage />
}
