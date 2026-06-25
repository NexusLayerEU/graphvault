import { useEffect } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import Nav from './components/Nav.jsx'
import Dashboard from './pages/Dashboard.jsx'
import UploadPage from './pages/UploadPage.jsx'
import ProjectPage from './pages/ProjectPage.jsx'

const IDENTITY_URL = import.meta.env.VITE_IDENTITY_URL || 'https://identity.nexuslayer.eu'
const APP_URL = 'https://graph.nexuslayer.eu'

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    // Read token from URL param on SSO redirect back
    const params = new URLSearchParams(location.search)
    const urlToken = params.get('sso_token') || params.get('token')
    if (urlToken) {
      localStorage.setItem('gv_token', urlToken)
      // Remove token from URL without adding to history
      const clean = location.pathname
      navigate(clean, { replace: true })
      return
    }

    // Check for existing token
    const stored = localStorage.getItem('gv_token')
    if (!stored) {
      const redirect = encodeURIComponent(APP_URL)
      window.location.href = `${IDENTITY_URL}/login?redirect=${redirect}`
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/project/:id" element={<ProjectPage />} />
      </Routes>
    </>
  )
}
