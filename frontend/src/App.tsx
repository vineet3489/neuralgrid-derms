import React, { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useGridStore } from './stores/gridStore'
import { useWebSocket } from './hooks/useWebSocket'
import { api } from './api/client'
import Layout from './components/Layout'

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

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token } = useAuthStore()
  if (!token) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

function AppInit() {
  const { token, setUser, setDeployments } = useAuthStore()
  const { setAlerts, setGridState, setForecasts } = useGridStore()

  useWebSocket()

  useEffect(() => {
    if (!token) return

    // Load initial data in parallel, fail gracefully
    api
      .me()
      .then((r) => setUser(r.data))
      .catch(() => {
        // Token may be expired — let interceptor handle 401
      })

    api
      .deployments()
      .then((r) => {
        if (Array.isArray(r.data) && r.data.length > 0) {
          setDeployments(r.data)
        }
      })
      .catch(() => {
        // Use fallback deployments
        setDeployments([
          {
            id: 'dep-ssen-001',
            slug: 'ssen',
            name: 'SSEN — Scotland & Northern Isles',
            country: 'UK',
            currency_code: 'GBP',
            timezone: 'Europe/London',
            regulatory_framework: 'ENA-CPP-2024',
            settlement_cycle: 'HALF_HOURLY',
          },
          {
            id: 'dep-puvvnl-001',
            slug: 'puvvnl',
            name: 'PUVVNL — Varanasi Division',
            country: 'India',
            currency_code: 'INR',
            timezone: 'Asia/Kolkata',
            regulatory_framework: 'UPERC-DR-2025',
            settlement_cycle: 'FIFTEEN_MIN',
          },
        ])
      })

    api
      .gridDashboard()
      .then((r) => {
        if (r.data?.grid_state) setGridState(r.data.grid_state)
        if (r.data?.active_alerts) setAlerts(r.data.active_alerts)
      })
      .catch(() => {})

    api
      .forecastAll()
      .then((r) => {
        if (r.data) setForecasts(r.data)
      })
      .catch(() => {})

    api
      .gridAlerts()
      .then((r) => {
        if (Array.isArray(r.data)) setAlerts(r.data)
      })
      .catch(() => {})
  }, [token])

  return null
}

export default function App() {
  return (
    <>
      <AppInit />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/grid"
          element={
            <ProtectedRoute>
              <GridPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/dispatch"
          element={
            <ProtectedRoute>
              <DispatchPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/programs"
          element={
            <ProtectedRoute>
              <ProgramsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/contracts"
          element={
            <ProtectedRoute>
              <ContractsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/counterparties"
          element={
            <ProtectedRoute>
              <CounterpartiesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settlement"
          element={
            <ProtectedRoute>
              <SettlementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/forecasting"
          element={
            <ProtectedRoute>
              <ForecastingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/optimization"
          element={
            <ProtectedRoute>
              <OptimizationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/reports"
          element={
            <ProtectedRoute>
              <ReportsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute>
              <AdminPage />
            </ProtectedRoute>
          }
        />
        {/* Fallback */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  )
}
