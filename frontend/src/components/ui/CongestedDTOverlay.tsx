/**
 * CongestedDTOverlay — shown on the GIS map when the user activates
 * "Congestion Analysis" mode. Fetches congested DTs and renders them
 * as coloured CircleMarkers:
 *   Red    = VOLTAGE_HIGH (solar reverse flow overvoltage) or THERMAL critical
 *   Amber  = VOLTAGE_LOW or THERMAL moderate
 *   Green  = NONE (no congestion)
 *
 * Shows a ranked list panel on the right side listing top congested DTs
 * with: congestion_score, congestion_type badge, max_loading_pct,
 * violation count, "Run Power Flow" button.
 */
import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, RefreshCw, Zap } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CongestedDT {
  dt_node_id: string
  feeder_id: string
  rated_kva: number
  congestion_score: number
  congestion_type: 'THERMAL' | 'VOLTAGE_LOW' | 'VOLTAGE_HIGH' | 'MIXED' | 'NONE'
  max_loading_pct: number
  violation_count_low: number
  violation_count_high: number
  has_power_flow_result: boolean
  lat: number | null
  lng: number | null
}

export interface CongestedDTOverlayProps {
  visible: boolean
  onSelectDT: (dtNodeId: string) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function congestionColor(type: CongestedDT['congestion_type']): string {
  switch (type) {
    case 'VOLTAGE_HIGH':
    case 'THERMAL':
      return 'text-red-400'
    case 'VOLTAGE_LOW':
    case 'MIXED':
      return 'text-amber-400'
    case 'NONE':
    default:
      return 'text-green-400'
  }
}

function congestionBgColor(type: CongestedDT['congestion_type']): string {
  switch (type) {
    case 'VOLTAGE_HIGH':
    case 'THERMAL':
      return 'bg-red-900/40 border-red-700'
    case 'VOLTAGE_LOW':
    case 'MIXED':
      return 'bg-amber-900/40 border-amber-700'
    case 'NONE':
    default:
      return 'bg-green-900/40 border-green-700'
  }
}

function CongestionIcon({ type }: { type: CongestedDT['congestion_type'] }) {
  const cls = clsx('w-4 h-4 shrink-0', congestionColor(type))
  switch (type) {
    case 'VOLTAGE_HIGH':
    case 'THERMAL':
      return <AlertTriangle className={cls} />
    case 'VOLTAGE_LOW':
    case 'MIXED':
      return <Zap className={cls} />
    case 'NONE':
    default:
      return <CheckCircle className={cls} />
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CongestedDTOverlay({ visible, onSelectDT }: CongestedDTOverlayProps) {
  const [dts, setDts] = useState<CongestedDT[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(75)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.congestedDTs(threshold, 10)
      setDts(res.data as CongestedDT[])
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load congestion data'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [threshold])

  useEffect(() => {
    if (visible) {
      fetchData()
    }
  }, [visible, fetchData])

  if (!visible) return null

  return (
    <div
      className={clsx(
        'fixed right-4 top-20 z-50 w-80 rounded-xl border border-gray-800',
        'bg-gray-900 text-white shadow-2xl flex flex-col',
        'max-h-[calc(100vh-6rem)] overflow-hidden',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <span className="font-semibold text-sm tracking-wide">Congestion Analysis</span>
        <button
          onClick={fetchData}
          disabled={loading}
          className="p-1 rounded hover:bg-gray-800 transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={clsx('w-4 h-4 text-gray-400', loading && 'animate-spin')} />
        </button>
      </div>

      {/* Threshold slider */}
      <div className="px-4 py-2 border-b border-gray-800">
        <label className="flex items-center justify-between text-xs text-gray-400 mb-1">
          <span>Loading threshold</span>
          <span className="font-mono text-white">{threshold}%</span>
        </label>
        <input
          type="range"
          min={50}
          max={100}
          step={5}
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          onMouseUp={fetchData}
          onTouchEnd={fetchData}
          className="w-full accent-blue-500"
        />
      </div>

      {/* Content */}
      <div className="overflow-y-auto flex-1">
        {error && (
          <div className="px-4 py-3 text-xs text-red-400 bg-red-900/20 border-b border-red-800">
            {error}
          </div>
        )}

        {loading && !dts.length && (
          <div className="px-4 py-6 text-center text-xs text-gray-500">
            Loading congestion data...
          </div>
        )}

        {!loading && !error && dts.length === 0 && (
          <div className="px-4 py-6 text-center text-xs text-gray-500">
            No DTs found for this deployment.
          </div>
        )}

        {dts.map((dt, idx) => (
          <div
            key={dt.dt_node_id}
            className={clsx(
              'mx-3 my-2 rounded-lg border px-3 py-2 text-xs',
              congestionBgColor(dt.congestion_type),
            )}
          >
            {/* Row 1: rank + DT ID + icon */}
            <div className="flex items-center gap-2 mb-1">
              <span className="text-gray-500 font-mono w-4 shrink-0">{idx + 1}.</span>
              <CongestionIcon type={dt.congestion_type} />
              <span className="font-mono font-medium truncate flex-1 text-white">
                {dt.dt_node_id}
              </span>
              <span
                className={clsx(
                  'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold border',
                  congestionBgColor(dt.congestion_type),
                  congestionColor(dt.congestion_type),
                )}
              >
                {dt.congestion_type}
              </span>
            </div>

            {/* Row 2: metrics */}
            {dt.has_power_flow_result ? (
              <div className="flex gap-3 text-gray-300 mb-1.5 pl-6">
                <span>Score: <strong className="text-white">{dt.congestion_score.toFixed(0)}</strong></span>
                <span>Load: <strong className="text-white">{dt.max_loading_pct.toFixed(1)}%</strong></span>
                {dt.violation_count_low > 0 && (
                  <span className="text-amber-400">V↓{dt.violation_count_low}</span>
                )}
                {dt.violation_count_high > 0 && (
                  <span className="text-red-400">V↑{dt.violation_count_high}</span>
                )}
              </div>
            ) : (
              <p className="text-gray-500 pl-6 mb-1.5 italic">
                No PF data — click Analyse to run
              </p>
            )}

            {/* Row 3: action */}
            <div className="pl-6">
              <button
                onClick={() => onSelectDT(dt.dt_node_id)}
                className={clsx(
                  'text-[10px] font-semibold px-2 py-0.5 rounded border transition-colors',
                  'bg-blue-900/40 border-blue-700 text-blue-300 hover:bg-blue-800/60',
                )}
              >
                Analyse
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-gray-800 text-[10px] text-gray-600">
        Showing top {dts.length} DTs by congestion score
      </div>
    </div>
  )
}
