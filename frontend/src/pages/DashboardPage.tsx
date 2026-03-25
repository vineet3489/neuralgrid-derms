import React, { useEffect, useState, useCallback } from 'react'
import {
  Zap,
  Activity,
  AlertTriangle,
  Wind,
  TrendingUp,
  RefreshCw,
  CheckCircle2,
  ShieldAlert,
} from 'lucide-react'
import { useGridStore } from '../stores/gridStore'
import { useAuthStore } from '../stores/authStore'
import { api } from '../api/client'
import StatCard from '../components/ui/StatCard'
import AlertBanner from '../components/ui/AlertBanner'
import LoadingSpinner from '../components/ui/LoadingSpinner'

export default function DashboardPage() {
  const { gridState, alerts, setGridState, setAlerts, acknowledgeAlert } =
    useGridStore()
  const { currentDeployment } = useAuthStore()
  const [loading, setLoading] = useState(!gridState)
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

  const loadDashboard = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    else setRefreshing(true)
    try {
      const [dashRes, alertRes] = await Promise.all([
        api.gridDashboard(),
        api.gridAlerts(),
      ])
      if (dashRes.data.grid_state) setGridState(dashRes.data.grid_state)
      setAlerts(alertRes.data || [])
      setLastRefresh(new Date())
    } catch {
      // silently fail — WebSocket will keep data fresh
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [setGridState, setAlerts])

  useEffect(() => {
    loadDashboard(false)
    const interval = setInterval(() => loadDashboard(true), 30000)
    return () => clearInterval(interval)
  }, [loadDashboard, currentDeployment])

  const handleAcknowledge = async (id: string) => {
    try {
      await api.acknowledgeAlert(id)
      acknowledgeAlert(id)
    } catch {
      acknowledgeAlert(id) // optimistic
    }
  }

  const gs = gridState
  const unackAlerts = alerts.filter((a) => !a.is_acknowledged)
  const criticalCount = unackAlerts.filter((a) => a.severity === 'CRITICAL').length

  if (loading && !gs) {
    return <LoadingSpinner fullPage label="Loading dashboard..." />
  }

  const netKw = gs?.net_kw ?? 0
  const netLabel = netKw >= 0 ? 'Net Export' : 'Net Import'
  const netAbs = Math.abs(netKw)

  // Compute constraint violations inline
  const overloadedNodes = (gs?.nodes || []).filter((n) => n.current_loading_pct > 75)
  const overloadedAssets = (gs?.assets || []).filter(
    (a) => a.doe_export_max_kw != null && a.current_kw < 0 && Math.abs(a.current_kw) > a.doe_export_max_kw * 1.05
  )
  const violations = [
    ...overloadedNodes.map((n) => ({
      id: n.node_id,
      type: n.current_loading_pct >= 100 ? 'CRITICAL' : 'WARNING',
      label: n.name,
      detail: `${n.node_type === 'FEEDER' ? 'Feeder' : 'DT'} loading ${n.current_loading_pct?.toFixed(0)}%`,
      limit: '≤75%',
    })),
    ...overloadedAssets.map((a) => ({
      id: a.id,
      type: 'WARNING',
      label: a.name,
      detail: `Export ${Math.abs(a.current_kw).toFixed(0)} kW exceeds DOE ${a.doe_export_max_kw?.toFixed(0)} kW`,
      limit: `${a.doe_export_max_kw?.toFixed(0)} kW`,
    })),
  ]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Operations Dashboard</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Real-time grid overview ·{' '}
            {lastRefresh.toLocaleTimeString('en-GB')}
          </p>
        </div>
        <button
          onClick={() => loadDashboard(true)}
          disabled={refreshing}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        <StatCard
          title="Total Generation"
          value={(gs?.total_gen_kw ?? 0).toFixed(1)}
          unit="kW"
          icon={<Zap className="w-5 h-5" />}
          color="green"
          trend="up"
          trendValue={`${((gs?.solar_factor ?? 0) * 100).toFixed(0)}% solar`}
        />
        <StatCard
          title="Assets Online"
          value={gs?.assets_online ?? 0}
          unit={`/ ${(gs?.assets_online ?? 0) + (gs?.assets_curtailed ?? 0) + (gs?.assets_offline ?? 0)}`}
          icon={<Activity className="w-5 h-5" />}
          color="blue"
          subtitle={`${gs?.assets_curtailed ?? 0} curtailed · ${gs?.assets_offline ?? 0} offline`}
        />
        <StatCard
          title="Active Alerts"
          value={unackAlerts.length}
          unit={criticalCount > 0 ? `(${criticalCount} critical)` : undefined}
          icon={<AlertTriangle className="w-5 h-5" />}
          color={criticalCount > 0 ? 'red' : unackAlerts.length > 0 ? 'amber' : 'green'}
        />
        <StatCard
          title="Total Load"
          value={(gs?.total_load_kw ?? 0).toFixed(1)}
          unit="kW"
          icon={<TrendingUp className="w-5 h-5" />}
          color="indigo"
          trend="stable"
          trendValue={`${((gs?.load_factor ?? 0) * 100).toFixed(0)}% factor`}
        />
        <StatCard
          title={netLabel}
          value={netAbs.toFixed(1)}
          unit="kW"
          icon={<Wind className="w-5 h-5" />}
          color={netKw >= 0 ? 'green' : 'amber'}
          subtitle={netKw >= 0 ? 'Exporting to grid' : 'Importing from grid'}
        />
      </div>

      {/* Two-column: Grid Health (2/3) + Active Alerts (1/3) */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">

        {/* Left 2/3: Grid Health card */}
        <div className="xl:col-span-2 card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-200">Grid Health</h2>
            <span className="text-xs text-gray-500">{gs?.nodes?.length ?? 0} nodes · {gs?.assets?.length ?? 0} assets</span>
          </div>

          {/* Node loading strip — up to 6 nodes */}
          {gs?.nodes && gs.nodes.length > 0 ? (
            <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
              {gs.nodes.slice(0, 6).map((node) => (
                <div
                  key={node.node_id}
                  className="bg-gray-800/60 rounded-lg p-2 border border-gray-700/50"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-gray-400 truncate leading-tight">{node.name}</span>
                  </div>
                  <div
                    className={`text-sm font-bold mb-1 ${
                      node.current_loading_pct > 90 ? 'text-red-400'
                        : node.current_loading_pct > 75 ? 'text-amber-400'
                        : 'text-green-400'
                    }`}
                  >
                    {node.current_loading_pct?.toFixed(0)}%
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        node.current_loading_pct > 90 ? 'bg-red-500'
                          : node.current_loading_pct > 75 ? 'bg-amber-500'
                          : 'bg-green-500'
                      }`}
                      style={{ width: `${Math.min(node.current_loading_pct, 100)}%` }}
                    />
                  </div>
                  <div className="text-[9px] text-gray-600 mt-1 truncate">
                    {node.node_type.replace(/_/g, ' ')}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center text-gray-600 text-xs py-4 border border-dashed border-gray-700 rounded-lg">
              No node data available
            </div>
          )}

          {/* Constraint violations — inline table */}
          {violations.length > 0 ? (
            <div className="border-t border-gray-700 pt-3">
              <div className="flex items-center gap-2 mb-2">
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-semibold text-amber-300">
                  Constraint Violations ({violations.length})
                </span>
                <span className="ml-auto text-[10px] text-gray-500">
                  {violations.filter((v) => v.type === 'CRITICAL').length} critical ·{' '}
                  {violations.filter((v) => v.type === 'WARNING').length} warning
                </span>
              </div>
              <table className="w-full text-xs">
                <tbody className="divide-y divide-gray-800">
                  {violations.slice(0, 5).map((v) => (
                    <tr key={v.id}>
                      <td className="py-1.5 pr-3">
                        <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          v.type === 'CRITICAL' ? 'bg-red-900/40 text-red-400' : 'bg-amber-900/40 text-amber-400'
                        }`}>{v.type}</span>
                      </td>
                      <td className="py-1.5 pr-3 text-gray-300 font-medium truncate max-w-[120px]">{v.label}</td>
                      <td className="py-1.5 pr-3 text-gray-400 truncate">{v.detail}</td>
                      <td className="py-1.5 text-gray-500 text-right">{v.limit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="border-t border-gray-700 pt-3 flex items-center gap-2 text-xs text-green-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              No constraint violations
            </div>
          )}
        </div>

        {/* Right 1/3: Active Alerts */}
        <div className="card flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-200">Active Alerts</h2>
            <span className="text-xs text-gray-500">{unackAlerts.length} unacknowledged</span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2 max-h-[340px] pr-1">
            {unackAlerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-center">
                <CheckCircle2 className="w-8 h-8 text-green-500 mb-2" />
                <span className="text-sm text-gray-400">All clear</span>
              </div>
            ) : (
              unackAlerts.slice(0, 20).map((alert) => (
                <AlertBanner
                  key={alert.id}
                  alert={alert}
                  onAcknowledge={handleAcknowledge}
                  compact
                />
              ))
            )}
          </div>
          {alerts.filter((a) => a.is_acknowledged).length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                {alerts.filter((a) => a.is_acknowledged).length} acknowledged
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
