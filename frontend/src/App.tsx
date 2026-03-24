import React, { useEffect, Component, ReactNode } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useGridStore } from './stores/gridStore'
import { useWebSocket } from './hooks/useWebSocket'
import { api } from './api/client'
import Layout from './components/Layout'
import LoadingSpinner from './components/ui/LoadingSpinner'

import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import GridPage from './pages/GridPage'
import DispatchPage from './pages/DispatchPage'
import ProgramsPage from './pages/ProgramsPage'
import ContractsPage from './pages/ContractsPage'
import CounterpartiesPage from './pages/CounterpartiesPage'
import SettlementPage from './pages/SettlementPage'
import ForecastingPage from './pages/ForecastingPage'
import OptimizationPage from './pages/OptimizationPage'
import ReportsPage from './pages/ReportsPage'
import AdminPage from './pages/AdminPage'
import IntegrationsPage from './pages/IntegrationsPage'
import SCADAGatewayPage from './pages/SCADAGatewayPage'
import GlossaryPage from './pages/GlossaryPage'
import OperatorConsolePage from './pages/OperatorConsolePage'

// ─── Error boundary — prevents a crashed page from blanking the whole app ────
class PageErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
          <div className="text-4xl">⚠️</div>
          <p className="text-sm font-medium text-gray-300">Page failed to render</p>
          <p className="text-xs text-gray-500 max-w-sm text-center">
            {(this.state.error as Error).message}
          </p>
          <button
            className="text-xs text-indigo-400 underline mt-2"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// ─── Protected route guard ────────────────────────────────────────────────────
// Wait for Zustand localStorage hydration before deciding to redirect.
// Without _hasHydrated, the store briefly starts with token=null even when
// a valid token is stored, causing every page load to flash the login screen.
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, _hasHydrated } = useAuthStore()

  // Still reading from localStorage — show a full-page spinner, not a redirect
  if (!_hasHydrated) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-950">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-500 text-sm">Loading Neural Grid…</p>
        </div>
      </div>
    )
  }

  if (!token) return <Navigate to="/login" replace />
  return <Layout><PageErrorBoundary>{children}</PageErrorBoundary></Layout>
}

// ─── App initialiser (runs once on login, re-runs only if token changes) ─────
function AppInit() {
  const { token, setUser, setDeployments } = useAuthStore()
  const { setAlerts, setGridState, setForecasts } = useGridStore()

  useWebSocket()

  useEffect(() => {
    if (!token) return

    // Fetch user profile — 401 auto-handled by Axios interceptor (calls logout)
    api.me().then((r) => setUser(r.data)).catch(() => {})

    // Fetch deployments — fall back to hardcoded list on failure (handled in store)
    api.deployments().then((r) => {
      if (Array.isArray(r.data) && r.data.length > 0) setDeployments(r.data)
    }).catch(() => {})

    // Fetch initial dashboard data — failures are non-fatal
    api.gridDashboard().then((r) => {
      if (r.data?.grid_state) setGridState(r.data.grid_state)
      if (r.data?.active_alerts) setAlerts(r.data.active_alerts)
    }).catch(() => {})

    api.forecastAll().then((r) => { if (r.data) setForecasts(r.data) }).catch(() => {})
    api.gridAlerts().then((r) => { if (Array.isArray(r.data)) setAlerts(r.data) }).catch(() => {})
  }, [token]) // Only re-runs when token actually changes (login / logout)

  return null
}

// ─── Root app ─────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <>
      <AppInit />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
        <Route path="/grid" element={<ProtectedRoute><GridPage /></ProtectedRoute>} />
        <Route path="/dispatch" element={<ProtectedRoute><DispatchPage /></ProtectedRoute>} />
        <Route path="/programs" element={<ProtectedRoute><ProgramsPage /></ProtectedRoute>} />
        <Route path="/contracts" element={<ProtectedRoute><ContractsPage /></ProtectedRoute>} />
        <Route path="/counterparties" element={<ProtectedRoute><CounterpartiesPage /></ProtectedRoute>} />
        <Route path="/settlement" element={<ProtectedRoute><SettlementPage /></ProtectedRoute>} />
        <Route path="/forecasting" element={<ProtectedRoute><ForecastingPage /></ProtectedRoute>} />
        <Route path="/optimization" element={<ProtectedRoute><OptimizationPage /></ProtectedRoute>} />
        <Route path="/reports" element={<ProtectedRoute><ReportsPage /></ProtectedRoute>} />
        <Route path="/integrations" element={<ProtectedRoute><IntegrationsPage /></ProtectedRoute>} />
        <Route path="/operator-console" element={<ProtectedRoute><OperatorConsolePage /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
        <Route path="/scada" element={<ProtectedRoute><SCADAGatewayPage /></ProtectedRoute>} />
        <Route path="/glossary" element={<ProtectedRoute><GlossaryPage /></ProtectedRoute>} />

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  )
}
