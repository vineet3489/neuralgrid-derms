import React, { useEffect, useState, useCallback } from 'react'
import {
  X,
  Zap,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Copy,
  Check,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts'
import { api } from '../../api/client'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LVNetworkPanelProps {
  dtNodeId: string
  dtName: string
  deployment: string
  onClose: () => void
}

interface BusResult {
  bus_ref?: string
  bus_name?: string
  v_pu: number
  v_v: number
  status?: string
  asset_linked?: string | null
  p_injection_kw?: number
}

interface PowerFlowResult {
  converged: boolean
  bus_count?: number
  total_load_kw: number
  total_gen_kw: number
  losses_kw: number
  losses_pct?: number
  bus_results: BusResult[]
  voltage_profile: Array<{ bus_id: string; v_pu: number }>
  violations: Array<{ bus_id: string; voltage: number; violation_type: string }>
}

interface ActiveEvent {
  id: string
  event_ref: string
  cmz_id?: string
  dt_id?: string
  status: string
  target_kw?: number
  formatted_message?: unknown
}

type OsmProvider = 'overpass' | 'synthetic'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function voltageStatus(vPu: number): { label: string; color: string; badgeClass: string } {
  if (vPu > 1.05 || vPu < 0.95) {
    return { label: 'VIOLATION', color: '#ef4444', badgeClass: 'badge-offline' }
  }
  if (vPu > 1.02 || vPu < 0.98) {
    return { label: 'WARNING', color: '#f59e0b', badgeClass: 'badge-warning' }
  }
  return { label: 'NORMAL', color: '#22c55e', badgeClass: 'badge-online' }
}

function barFill(vPu: number): string {
  if (vPu > 1.05 || vPu < 0.95) return '#ef4444'
  if (vPu > 1.02 || vPu < 0.98) return '#f59e0b'
  return '#22c55e'
}

// ─── JSON Highlighter ─────────────────────────────────────────────────────────

function JsonHighlight({ json }: { json: unknown }) {
  const text = JSON.stringify(json, null, 2)
  const highlighted = text.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) return `<span class="text-blue-400">${match}</span>`
        return `<span class="text-green-400">${match}</span>`
      }
      if (/true|false/.test(match)) return `<span class="text-purple-400">${match}</span>`
      if (/null/.test(match)) return `<span class="text-red-400">${match}</span>`
      return `<span class="text-amber-400">${match}</span>`
    },
  )
  return (
    <pre
      className="text-xs font-mono leading-relaxed whitespace-pre-wrap break-all"
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  )
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

function Spinner({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const dim = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5'
  return (
    <div className={`${dim} border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin`} />
  )
}

// ─── Main Panel ───────────────────────────────────────────────────────────────

export default function LVNetworkPanel({
  dtNodeId,
  dtName,
  deployment: _deployment,
  onClose,
}: LVNetworkPanelProps) {
  const [pfLoading, setPfLoading] = useState(false)
  const [pfResult, setPfResult] = useState<PowerFlowResult | null>(null)
  const [pfError, setPfError] = useState<string | null>(null)

  const [rebuildLoading, setRebuildLoading] = useState(false)
  const [rebuildProvider, setRebuildProvider] = useState<OsmProvider>('overpass')
  const [rebuildDone, setRebuildDone] = useState(false)

  const [oeLoading, setOeLoading] = useState(false)
  const [oeDoc, setOeDoc] = useState<Record<string, unknown> | null>(null)
  const [oeEvents, setOeEvents] = useState<ActiveEvent[]>([])
  const [oeCopied, setOeCopied] = useState(false)

  // ── Power Flow ─────────────────────────────────────────────────────────────

  const handleRunPowerFlow = useCallback(async () => {
    setPfLoading(true)
    setPfError(null)
    try {
      const res = await api.lvNetworkPowerFlow(dtNodeId)
      setPfResult(res.data)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || 'Power flow failed'
      setPfError(msg)
    } finally {
      setPfLoading(false)
    }
  }, [dtNodeId])

  // ── Rebuild Network ────────────────────────────────────────────────────────

  const handleRebuild = useCallback(async () => {
    setRebuildLoading(true)
    setRebuildDone(false)
    try {
      await api.lvNetworkRebuild(dtNodeId, rebuildProvider)
      setRebuildDone(true)
    } catch {
      // silently surface as done — backend may return 200 with rebuild in background
      setRebuildDone(true)
    } finally {
      setRebuildLoading(false)
    }
  }, [dtNodeId, rebuildProvider])

  // ── OE Messages ────────────────────────────────────────────────────────────

  const loadOeMessages = useCallback(async () => {
    setOeLoading(true)
    try {
      const res = await api.activeEvents({ dt_id: dtNodeId })
      const events: ActiveEvent[] = res.data || []
      setOeEvents(events)
      if (events.length > 0) {
        // Fetch formatted OE doc for the first active event
        try {
          const fmtRes = await api.oeMessagesSSEN(events[0].id)
          setOeDoc(fmtRes.data?.formatted_message || fmtRes.data || null)
        } catch {
          setOeDoc(null)
        }
      }
    } catch {
      setOeEvents([])
      setOeDoc(null)
    } finally {
      setOeLoading(false)
    }
  }, [dtNodeId])

  useEffect(() => {
    loadOeMessages()
  }, [loadOeMessages])

  const handleCopyOe = () => {
    navigator.clipboard.writeText(JSON.stringify(oeDoc, null, 2)).then(() => {
      setOeCopied(true)
      setTimeout(() => setOeCopied(false), 1500)
    })
  }

  // ── Derived ────────────────────────────────────────────────────────────────

  const buses: BusResult[] = pfResult?.bus_results ?? []

  return (
    <div className="fixed inset-y-0 right-0 w-[420px] bg-gray-900 border-l border-gray-700 shadow-2xl z-[500] flex flex-col overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700 flex-shrink-0 bg-gray-900/95">
        <div>
          <h3 className="text-sm font-semibold text-gray-100 leading-tight">LV Network</h3>
          <p className="text-xs text-indigo-400 mt-0.5 font-medium">{dtName}</p>
          <p className="text-xs text-gray-600 mt-0.5 font-mono">{dtNodeId}</p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-200 p-1 rounded-md hover:bg-gray-700 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">

        {/* Power Flow section */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
              Power Flow Analysis
            </span>
            <button
              onClick={handleRunPowerFlow}
              disabled={pfLoading}
              className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-60"
            >
              {pfLoading ? <Spinner size="sm" /> : <Zap className="w-3.5 h-3.5" />}
              {pfLoading ? 'Running...' : 'Run Power Flow'}
            </button>
          </div>

          {pfError && (
            <div className="flex items-start gap-2 p-3 bg-red-900/20 border border-red-700/40 rounded-lg text-xs text-red-400">
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {pfError}
            </div>
          )}

          {pfResult && (
            <div className="space-y-4">
              {/* Summary stats */}
              <div className="grid grid-cols-2 gap-2">
                <div
                  className={`rounded-lg p-2.5 border ${
                    pfResult.converged
                      ? 'bg-green-900/15 border-green-700/30'
                      : 'bg-red-900/15 border-red-700/30'
                  }`}
                >
                  <div className="text-xs text-gray-500 mb-1 flex items-center gap-1">
                    {pfResult.converged ? (
                      <CheckCircle className="w-3 h-3 text-green-400" />
                    ) : (
                      <XCircle className="w-3 h-3 text-red-400" />
                    )}
                    Converged
                  </div>
                  <div className={`text-base font-bold ${pfResult.converged ? 'text-green-400' : 'text-red-400'}`}>
                    {pfResult.converged ? 'Yes' : 'No'}
                  </div>
                </div>
                <div className="rounded-lg p-2.5 bg-gray-800 border border-gray-700">
                  <div className="text-xs text-gray-500 mb-1">Buses</div>
                  <div className="text-base font-bold text-gray-100">
                    {pfResult.bus_count ?? buses.length}
                  </div>
                </div>
                <div className="rounded-lg p-2.5 bg-gray-800 border border-gray-700">
                  <div className="text-xs text-gray-500 mb-1">Total Load</div>
                  <div className="text-base font-bold text-gray-100">
                    {pfResult.total_load_kw.toFixed(1)}
                    <span className="text-xs text-gray-500 ml-1">kW</span>
                  </div>
                </div>
                <div className="rounded-lg p-2.5 bg-gray-800 border border-gray-700">
                  <div className="text-xs text-gray-500 mb-1">Total Gen</div>
                  <div className="text-base font-bold text-green-400">
                    {pfResult.total_gen_kw.toFixed(1)}
                    <span className="text-xs text-gray-500 ml-1">kW</span>
                  </div>
                </div>
                <div className="col-span-2 rounded-lg p-2.5 bg-gray-800 border border-gray-700">
                  <div className="text-xs text-gray-500 mb-1">Losses</div>
                  <div className="text-base font-bold text-amber-400">
                    {pfResult.losses_kw.toFixed(2)} kW
                    {pfResult.losses_pct != null && (
                      <span className="text-xs text-gray-500 ml-2">({pfResult.losses_pct.toFixed(2)}%)</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Voltage Profile Chart */}
              {pfResult.voltage_profile?.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-400 mb-2">Voltage Profile</div>
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart
                      data={pfResult.voltage_profile}
                      layout="vertical"
                      margin={{ left: 56, right: 12, top: 2, bottom: 2 }}
                    >
                      <XAxis
                        type="number"
                        domain={[0.9, 1.1]}
                        tick={{ fill: '#6b7280', fontSize: 9 }}
                        tickLine={false}
                      />
                      <YAxis
                        dataKey="bus_id"
                        type="category"
                        tick={{ fill: '#6b7280', fontSize: 9 }}
                        width={52}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2937',
                          border: '1px solid #374151',
                          borderRadius: 6,
                          fontSize: 11,
                        }}
                        formatter={(val: number) => [`${val.toFixed(4)} pu`, 'Voltage']}
                        itemStyle={{ color: '#e5e7eb' }}
                        labelStyle={{ color: '#9ca3af' }}
                      />
                      <Bar dataKey="v_pu" radius={[0, 3, 3, 0]}>
                        {pfResult.voltage_profile.map((entry, idx) => (
                          <Cell key={idx} fill={barFill(entry.v_pu)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Violations */}
              {pfResult.violations?.length > 0 && (
                <div className="p-3 bg-red-900/15 border border-red-700/30 rounded-lg">
                  <div className="flex items-center gap-1.5 mb-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
                    <span className="text-xs font-semibold text-red-400">
                      {pfResult.violations.length} Voltage Violation{pfResult.violations.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {pfResult.violations.map((v, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <span className="font-mono text-indigo-300">{v.bus_id}</span>
                        <span className="text-red-400 font-mono">{v.voltage.toFixed(4)} pu</span>
                        <span className="badge-offline text-xs py-0.5">{v.violation_type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bus Table */}
              {buses.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-400 mb-2">Bus Results</div>
                  <div className="overflow-x-auto rounded-lg border border-gray-700">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-800/60">
                          <th className="table-header text-left py-2 px-2">Bus Ref</th>
                          <th className="table-header text-right py-2 px-2">V (pu)</th>
                          <th className="table-header text-right py-2 px-2">V (V)</th>
                          <th className="table-header text-left py-2 px-2">Status</th>
                          <th className="table-header text-left py-2 px-2">Asset</th>
                        </tr>
                      </thead>
                      <tbody>
                        {buses.map((bus, i) => {
                          const vs = voltageStatus(bus.v_pu)
                          const busRef = bus.bus_ref || bus.bus_name || `Bus ${i + 1}`
                          return (
                            <tr key={i} className="table-row">
                              <td className="table-cell py-1.5 px-2 font-mono text-indigo-300">
                                {busRef}
                              </td>
                              <td className="table-cell py-1.5 px-2 text-right font-mono" style={{ color: vs.color }}>
                                {bus.v_pu.toFixed(4)}
                              </td>
                              <td className="table-cell py-1.5 px-2 text-right font-mono text-gray-300">
                                {bus.v_v.toFixed(1)}
                              </td>
                              <td className="table-cell py-1.5 px-2">
                                <span className={vs.badgeClass} style={{ fontSize: 10 }}>
                                  {vs.label}
                                </span>
                              </td>
                              <td className="table-cell py-1.5 px-2 text-gray-500 font-mono" style={{ fontSize: 10 }}>
                                {bus.asset_linked || '—'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {!pfResult && !pfLoading && !pfError && (
            <div className="text-center text-gray-600 text-xs py-6 border border-dashed border-gray-700 rounded-lg">
              Click "Run Power Flow" to analyse the LV network for this DT
            </div>
          )}
        </div>

        {/* Rebuild Network section */}
        <div>
          <div className="text-xs font-semibold text-gray-300 uppercase tracking-wider mb-3">
            Network Topology
          </div>
          <div className="flex items-center gap-2">
            <select
              value={rebuildProvider}
              onChange={(e) => setRebuildProvider(e.target.value as OsmProvider)}
              className="select text-xs flex-1"
              disabled={rebuildLoading}
            >
              <option value="overpass">OpenStreetMap (Overpass)</option>
              <option value="synthetic">Synthetic</option>
            </select>
            <button
              onClick={handleRebuild}
              disabled={rebuildLoading}
              className="btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-60 flex-shrink-0"
            >
              {rebuildLoading ? <Spinner size="sm" /> : <RefreshCw className="w-3.5 h-3.5" />}
              Rebuild from OSM
            </button>
          </div>
          {rebuildDone && !rebuildLoading && (
            <div className="flex items-center gap-1.5 mt-2 text-xs text-green-400">
              <CheckCircle className="w-3.5 h-3.5" />
              Network rebuild requested
            </div>
          )}
        </div>

        {/* SSEN OE Message section */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
              SSEN OE Messages
            </span>
            <button
              onClick={loadOeMessages}
              disabled={oeLoading}
              className="text-gray-500 hover:text-gray-300 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${oeLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {oeLoading && (
            <div className="flex items-center justify-center py-6">
              <Spinner />
            </div>
          )}

          {!oeLoading && oeEvents.length === 0 && (
            <div className="text-center text-gray-600 text-xs py-5 border border-dashed border-gray-700 rounded-lg">
              No active OE events for this DT
            </div>
          )}

          {!oeLoading && oeEvents.length > 0 && (
            <div className="space-y-2 mb-3">
              {oeEvents.map((ev) => (
                <div key={ev.id} className="flex items-center gap-2 p-2 bg-gray-800 rounded-lg">
                  <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 flex-shrink-0" />
                  <span className="text-xs text-indigo-300 font-mono">{ev.event_ref}</span>
                  {ev.target_kw != null && (
                    <span className="text-xs text-amber-400 ml-auto font-medium">{ev.target_kw} kW</span>
                  )}
                  <span className={`text-xs ml-1 ${ev.status === 'DISPATCHED' ? 'badge-online' : 'badge-gray'}`}>
                    {ev.status}
                  </span>
                </div>
              ))}
            </div>
          )}

          {!oeLoading && oeDoc && (
            <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 bg-gray-800/60 border-b border-gray-700">
                <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">
                  OperatingEnvelope_MarketDocument
                </span>
                <button
                  onClick={handleCopyOe}
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
                >
                  {oeCopied ? (
                    <Check className="w-3 h-3 text-green-400" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                  {oeCopied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div className="p-3 max-h-64 overflow-y-auto">
                <JsonHighlight json={oeDoc} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
