/**
 * Operator Console — guided workflow for ADMS fault response.
 *
 * Step 1: Review ADMS faults / grid alerts
 * Step 2: Select CMZ and time window
 * Step 3: Run power flow — verify network health
 * Step 4: Generate Operating Envelope (D4G IEC 62746-4)
 * Step 5: Send OE to DER Aggregator
 */
import React, { useEffect, useState, useCallback } from 'react'
import {
  AlertTriangle, CheckCircle2, ChevronRight, Zap, Activity,
  Radio, Send, RefreshCw, Settings, Clock, BarChart3,
  Network, FileText, ArrowRight, Info, Copy, TrendingDown, TrendingUp,
} from 'lucide-react'
import { format, addMinutes } from 'date-fns'
import { api } from '../api/client'
import { useGridStore } from '../stores/gridStore'
import { useAuthStore } from '../stores/authStore'
import LoadingSpinner from '../components/ui/LoadingSpinner'

// ── Types ──────────────────────────────────────────────────────────────────────

interface StepState {
  active: boolean
  done: boolean
}

interface PowerFlowResult {
  converged: boolean
  iterations: number
  max_voltage_pu: number
  min_voltage_pu: number
  total_gen_kw: number
  total_load_kw: number
  violations: Array<{ bus_id: string; voltage_pu: number; type: string }>
}

interface OESeriesPoint {
  position: number
  quantity?: number
  quantity_import?: number
  quantity_export?: number
  quality?: string
}

interface OESeries {
  mRID?: string
  FlowDirection?: { direction: string }
  Period?: {
    timeInterval?: { start: string; end: string }
    resolution?: string
    Point?: OESeriesPoint[]
  }
}

interface OEMessage {
  MessageDocumentHeader?: { messageId: string; messageType: string; timestamp: string }
  ReferenceEnergyCurveOperatingEnvelope_MarketDocument?: {
    mRID: string
    type?: string
    Series?: OESeries[]
    period?: {
      timeInterval?: { start: string; end: string }
    }
  }
}

const CMZ_OPTIONS: { value: string; label: string; deployment: string }[] = [
  { value: 'CMZ-LERWICK-01',    label: 'CMZ-LERWICK-01 — Lerwick North Feeder',     deployment: 'ssen'   },
  { value: 'CMZ-LERWICK-02',    label: 'CMZ-LERWICK-02 — Lerwick South Feeder',     deployment: 'ssen'   },
  { value: 'CMZ-ORKNEY-01',     label: 'CMZ-ORKNEY-01  — Orkney Wind Zone',          deployment: 'ssen'   },
  { value: 'CMZ-VARANASI-N1',   label: 'CMZ-VARANASI-N1 — North Varanasi',          deployment: 'puvvnl' },
  { value: 'CMZ-VARANASI-S1',   label: 'CMZ-VARANASI-S1 — South Varanasi',          deployment: 'puvvnl' },
]

const WINDOW_OPTIONS = [
  { value: '30',  label: 'Next 30 minutes' },
  { value: '60',  label: 'Next 1 hour'     },
  { value: '120', label: 'Next 2 hours'    },
  { value: '240', label: 'Next 4 hours'    },
  { value: '480', label: 'Next 8 hours'    },
]

// ── Step header ────────────────────────────────────────────────────────────────

function StepHeader({
  n, title, subtitle, state,
}: {
  n: number; title: string; subtitle: string; state: StepState
}) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${
        state.done
          ? 'bg-green-600 text-white'
          : state.active
          ? 'bg-indigo-600 text-white'
          : 'bg-gray-700 text-gray-500'
      }`}>
        {state.done ? <CheckCircle2 className="w-4 h-4" /> : n}
      </div>
      <div>
        <h2 className="text-sm font-semibold text-gray-100">{title}</h2>
        <p className="text-xs text-gray-500">{subtitle}</p>
      </div>
    </div>
  )
}

// ── Reference Energy Curve View ────────────────────────────────────────────────

function ReferencEnergyCurveView({ oeMessage }: { oeMessage: OEMessage }) {
  const [copied, setCopied] = useState(false)

  const doc = oeMessage?.ReferenceEnergyCurveOperatingEnvelope_MarketDocument
  const header = oeMessage?.MessageDocumentHeader
  const mRID = doc?.mRID ?? header?.messageId ?? '—'
  const msgType = header?.messageType ?? doc?.type ?? 'ReferenceEnergyCurveOperatingEnvelope'

  // Gather all time slots from all Series with Points
  interface SlotRow {
    slotLabel: string
    importKw: number | null
    exportKw: number | null
    quality: string
  }

  const slots: SlotRow[] = []

  // Collect period info from first series that has one
  let periodStart: string | null = null
  let periodEnd: string | null = null

  const seriesList: OESeries[] = doc?.Series ?? []

  // Build import/export maps keyed by position
  const importMap: Record<number, OESeriesPoint> = {}
  const exportMap: Record<number, OESeriesPoint> = {}
  let resolution = 'PT30M'
  let intervalStart: Date | null = null

  for (const s of seriesList) {
    const period = s.Period
    if (!period) continue
    if (period.timeInterval?.start && !periodStart) {
      periodStart = period.timeInterval.start
      periodEnd = period.timeInterval.end ?? null
      intervalStart = new Date(period.timeInterval.start)
    }
    if (period.resolution) resolution = period.resolution
    const dir = s.FlowDirection?.direction ?? ''
    const points = period.Point ?? []
    for (const pt of points) {
      if (dir === 'A01' || dir === 'import' || dir.toLowerCase().includes('import')) {
        importMap[pt.position] = pt
      } else if (dir === 'A02' || dir === 'export' || dir.toLowerCase().includes('export')) {
        exportMap[pt.position] = pt
      } else {
        // No direction — treat quantity as export, quantity_import as import
        if (pt.quantity_import != null || pt.quantity != null) {
          importMap[pt.position] = pt
        }
        if (pt.quantity_export != null) {
          exportMap[pt.position] = pt
        }
      }
    }
  }

  // Determine number of slots
  const allPositions = new Set([...Object.keys(importMap), ...Object.keys(exportMap)].map(Number))
  const maxPos = allPositions.size > 0 ? Math.max(...allPositions) : 0

  const resMinutes = resolution === 'PT15M' ? 15 : resolution === 'PT60M' ? 60 : 30

  for (let pos = 1; pos <= (maxPos || 1); pos++) {
    const imp = importMap[pos]
    const exp = exportMap[pos]
    const slotStart = intervalStart ? new Date(intervalStart.getTime() + (pos - 1) * resMinutes * 60000) : null
    const slotEnd = slotStart ? new Date(slotStart.getTime() + resMinutes * 60000) : null
    const slotLabel = slotStart && slotEnd
      ? `${slotStart.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })} – ${slotEnd.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`
      : `Slot ${pos}`
    const importKw = imp?.quantity_import ?? imp?.quantity ?? null
    const exportKw = exp?.quantity_export ?? exp?.quantity ?? null
    const quality = imp?.quality ?? exp?.quality ?? '—'
    slots.push({ slotLabel, importKw, exportKw, quality })
  }

  // If no structured slots found but raw JSON has data, show compact fallback
  const hasSlots = slots.length > 0

  const maxImport = slots.reduce((m, s) => Math.max(m, s.importKw ?? 0), 0.001)
  const maxExport = slots.reduce((m, s) => Math.max(m, s.exportKw ?? 0), 0.001)

  const qualityColor = (q: string) => {
    if (q === 'A04') return 'text-green-400'
    if (q === 'A06') return 'text-amber-400'
    if (q === 'A03') return 'text-red-400'
    return 'text-gray-500'
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(oeMessage, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="space-y-3">
      {/* Header summary */}
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-3">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-semibold text-gray-200">Reference Energy Curve</span>
            <span className="text-xs text-green-400 flex items-center gap-1 ml-1">
              <CheckCircle2 className="w-3 h-3" />
              Generated
            </span>
          </div>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 bg-gray-800 px-2.5 py-1 rounded-lg transition-colors"
          >
            <Copy className="w-3 h-3" />
            {copied ? 'Copied!' : 'Copy JSON'}
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-gray-800/60 rounded-lg p-2">
            <div className="text-gray-500 mb-0.5">mRID</div>
            <div className="font-mono text-indigo-300 truncate text-[10px]">{mRID}</div>
          </div>
          <div className="bg-gray-800/60 rounded-lg p-2">
            <div className="text-gray-500 mb-0.5">Message Type</div>
            <div className="text-gray-200 truncate text-[10px]">{msgType}</div>
          </div>
          <div className="bg-gray-800/60 rounded-lg p-2">
            <div className="text-gray-500 mb-0.5">Period Start</div>
            <div className="font-mono text-gray-200 text-[10px]">
              {periodStart ? new Date(periodStart).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }) : '—'}
            </div>
          </div>
          <div className="bg-gray-800/60 rounded-lg p-2">
            <div className="text-gray-500 mb-0.5">Time Slots</div>
            <div className="text-gray-200 font-bold">{hasSlots ? slots.length : '—'} × {resMinutes}min</div>
          </div>
        </div>
      </div>

      {/* Time-series table */}
      {hasSlots ? (
        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-700 flex items-center gap-2 text-xs">
            <BarChart3 className="w-3.5 h-3.5 text-indigo-400" />
            <span className="font-medium text-gray-300">Operating Envelope — Time Series</span>
            <span className="ml-auto text-gray-500 flex items-center gap-3">
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-blue-500 inline-block" /> Import</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded bg-green-500 inline-block" /> Export</span>
            </span>
          </div>
          <div className="overflow-y-auto max-h-64">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-800/80">
                <tr>
                  <th className="text-left py-2 px-3 text-gray-400 font-medium">Time Slot</th>
                  <th className="text-right py-2 px-3 text-blue-400 font-medium">Import (kW)</th>
                  <th className="py-2 px-2 w-32" />
                  <th className="text-right py-2 px-3 text-green-400 font-medium">Export (kW)</th>
                  <th className="py-2 px-2 w-32" />
                  <th className="text-center py-2 px-3 text-gray-400 font-medium">Quality</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {slots.map((slot, i) => (
                  <tr key={i} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-2 px-3 font-mono text-gray-300">{slot.slotLabel}</td>
                    <td className="py-2 px-3 text-right font-mono text-blue-300">
                      {slot.importKw != null ? slot.importKw.toFixed(1) : '—'}
                    </td>
                    <td className="py-1.5 px-2">
                      {slot.importKw != null && (
                        <div className="h-3 bg-gray-800 rounded-sm overflow-hidden">
                          <div
                            className="h-full bg-blue-500/60 rounded-sm"
                            style={{ width: `${Math.min((slot.importKw / maxImport) * 100, 100)}%` }}
                          />
                        </div>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-green-300">
                      {slot.exportKw != null ? slot.exportKw.toFixed(1) : '—'}
                    </td>
                    <td className="py-1.5 px-2">
                      {slot.exportKw != null && (
                        <div className="h-3 bg-gray-800 rounded-sm overflow-hidden">
                          <div
                            className="h-full bg-green-500/60 rounded-sm"
                            style={{ width: `${Math.min((slot.exportKw / maxExport) * 100, 100)}%` }}
                          />
                        </div>
                      )}
                    </td>
                    <td className={`py-2 px-3 text-center font-mono font-bold text-[10px] ${qualityColor(slot.quality)}`}>
                      {slot.quality}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        // Fallback: show raw JSON if structure not recognised
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-2">Raw OE message (no time-series structure detected)</p>
          <pre className="text-xs text-gray-300 font-mono overflow-auto max-h-56 whitespace-pre-wrap">
            {JSON.stringify(oeMessage, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function OperatorConsolePage() {
  const { alerts, gridState } = useGridStore()
  const { currentDeployment } = useAuthStore()

  // ── Step progression ──
  const [step, setStep] = useState(1)

  // ── Step 2: CMZ + window selection ──
  const [selectedCmz, setSelectedCmz] = useState('')
  const [windowMinutes, setWindowMinutes] = useState('60')

  // ── Step 3: Power flow ──
  const [pfRunning, setPfRunning] = useState(false)
  const [pfResult, setPfResult] = useState<PowerFlowResult | null>(null)
  const [pfError, setPfError] = useState('')

  // ── Step 4: OE generation ──
  const [creatingEvent, setCreatingEvent] = useState(false)
  const [eventId, setEventId] = useState<string | null>(null)
  const [oeMessage, setOeMessage] = useState<OEMessage | null>(null)
  const [oeError, setOeError] = useState('')

  // ── Step 5: Send to aggregator ──
  const [aggregators, setAggregators] = useState<any[]>([])
  const [selectedAgg, setSelectedAgg] = useState('')
  const [sending, setSending] = useState(false)
  const [sendResult, setSendResult] = useState<{ ok: boolean; msg: string } | null>(null)

  // Load aggregators on mount
  useEffect(() => {
    api.aggregatorDevices().then((r) => {
      setAggregators(Array.isArray(r.data) ? r.data : r.data?.items ?? [])
    }).catch(() => {})
  }, [])

  const criticalAlerts = alerts.filter(
    (a) => a.severity === 'CRITICAL' && !a.is_acknowledged
  )
  const warningAlerts = alerts.filter(
    (a) => a.severity === 'WARNING' && !a.is_acknowledged
  )

  const availableCmzs = CMZ_OPTIONS.filter(
    (c) => !currentDeployment || c.deployment === currentDeployment
  )

  // ── Handlers ──────────────────────────────────────────────────────────────────

  const handleRunPowerFlow = async () => {
    setPfRunning(true)
    setPfError('')
    setPfResult(null)
    try {
      const res = await api.runPowerFlow()
      setPfResult(res.data)
      setStep(4)
    } catch (e: any) {
      setPfError(e?.response?.data?.detail || 'Power flow failed. Ensure assets are registered.')
    } finally {
      setPfRunning(false)
    }
  }

  const handleGenerateOE = async () => {
    if (!selectedCmz) return
    setCreatingEvent(true)
    setOeError('')
    setOeMessage(null)
    try {
      const startTime = new Date().toISOString()
      const endTime = addMinutes(new Date(), parseInt(windowMinutes)).toISOString()

      // Create a CURTAILMENT event for the selected CMZ + window
      const evRes = await api.createEvent({
        cmz_id: selectedCmz,
        event_type: 'CURTAILMENT',
        target_kw: pfResult?.total_gen_kw ? pfResult.total_gen_kw * 0.1 : 100,
        duration_minutes: parseInt(windowMinutes),
        start_time: startTime,
        trigger: 'OE_VIOLATION',
        operator_notes: `Operator console: generated from power flow at ${format(new Date(), 'HH:mm dd/MM/yyyy')}`,
      })
      const newEventId = evRes.data?.id
      setEventId(newEventId)

      // Fetch the D4G OE message for this event
      const oeRes = await api.cimDispatch(newEventId)
      setOeMessage(oeRes.data?.d4g_message || oeRes.data)
      setStep(5)
    } catch (e: any) {
      setOeError(e?.response?.data?.detail || 'Failed to generate OE. Check CMZ configuration and assets.')
    } finally {
      setCreatingEvent(false)
    }
  }

  const handleSendToAggregator = async () => {
    if (!eventId) return
    setSending(true)
    setSendResult(null)
    try {
      await api.dispatchEvent(eventId)
      setSendResult({ ok: true, msg: 'Operating Envelope dispatched successfully. D4G message published to Kafka and REST.' })
      setStep(6)
    } catch (e: any) {
      setSendResult({ ok: false, msg: e?.response?.data?.detail || 'Dispatch failed.' })
    } finally {
      setSending(false)
    }
  }

  const stepState = (n: number): StepState => ({
    active: step === n,
    done: step > n,
  })

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Page header */}
      <div>
        <h1 className="page-header flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-400" />
          Operator Console
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">
          ADMS fault response → power flow → operating envelope → DER aggregator dispatch
        </p>
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-1">
        {['ADMS Faults', 'CMZ & Window', 'Power Flow', 'Generate OE', 'Send'].map((label, i) => (
          <React.Fragment key={label}>
            <div className={`flex-1 h-1.5 rounded-full transition-colors ${
              step > i + 1 ? 'bg-green-500' : step === i + 1 ? 'bg-indigo-500' : 'bg-gray-700'
            }`} />
            {i < 4 && <ChevronRight className="w-3 h-3 text-gray-600 flex-shrink-0" />}
          </React.Fragment>
        ))}
      </div>
      <div className="flex items-center gap-1 -mt-4">
        {['ADMS Faults', 'CMZ & Window', 'Power Flow', 'Generate OE', 'Send'].map((label, i) => (
          <div key={label} className="flex-1 text-center">
            <span className={`text-xs ${step === i + 1 ? 'text-indigo-400' : step > i + 1 ? 'text-green-400' : 'text-gray-600'}`}>
              {label}
            </span>
          </div>
        ))}
      </div>

      {/* ── Step 1: ADMS Faults ─────────────────────────────────────────────── */}
      <div className={`card transition-opacity ${step < 1 ? 'opacity-40' : ''}`}>
        <StepHeader
          n={1} title="ADMS Faults & Grid Alerts"
          subtitle="Review current faults from the ADMS before responding"
          state={stepState(1)}
        />

        {criticalAlerts.length === 0 && warningAlerts.length === 0 ? (
          <div className="flex items-center gap-2 p-3 bg-green-900/20 border border-green-800/30 rounded-lg text-sm text-green-400">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            No active alerts — grid is operating normally
          </div>
        ) : (
          <div className="space-y-2">
            {[...criticalAlerts, ...warningAlerts].map((alert) => (
              <div
                key={alert.id}
                className={`flex items-start gap-3 p-3 rounded-lg border ${
                  alert.severity === 'CRITICAL'
                    ? 'bg-red-900/20 border-red-800/40 text-red-300'
                    : 'bg-amber-900/20 border-amber-800/40 text-amber-300'
                }`}
              >
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-bold uppercase tracking-wide">{alert.severity}</span>
                    <span className="text-xs text-gray-400">{alert.alert_type?.replace(/_/g, ' ')}</span>
                    {alert.node_id && (
                      <span className="font-mono text-xs bg-gray-800 px-1.5 py-0.5 rounded">{alert.node_id}</span>
                    )}
                  </div>
                  <p className="text-xs">{alert.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Grid summary */}
        {gridState && (
          <div className="mt-4 grid grid-cols-4 gap-3 text-center">
            {[
              { label: 'Generation', value: `${(gridState.total_gen_kw / 1000).toFixed(1)} MW`, color: 'text-green-400' },
              { label: 'Load',       value: `${(gridState.total_load_kw / 1000).toFixed(1)} MW`, color: 'text-amber-400' },
              { label: 'Assets Live',value: `${gridState.assets_online}`,                         color: 'text-blue-400'  },
              { label: 'Curtailed',  value: `${gridState.assets_curtailed}`,                      color: 'text-red-400'   },
            ].map((s) => (
              <div key={s.label} className="bg-gray-800/50 rounded-lg p-2">
                <div className={`text-base font-bold ${s.color}`}>{s.value}</div>
                <div className="text-xs text-gray-500">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {step === 1 && (
          <button
            className="btn-primary mt-4 flex items-center gap-2"
            onClick={() => setStep(2)}
          >
            Proceed to CMZ Selection
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── Step 2: CMZ & Window ────────────────────────────────────────────── */}
      <div className={`card transition-opacity ${step < 2 ? 'opacity-40 pointer-events-none' : ''}`}>
        <StepHeader
          n={2} title="Select CMZ and Time Window"
          subtitle="Choose the Constraint Management Zone and horizon for the OE"
          state={stepState(2)}
        />

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">
              Constraint Management Zone (CMZ)
            </label>
            <select
              className="select w-full"
              value={selectedCmz}
              onChange={(e) => setSelectedCmz(e.target.value)}
              disabled={step !== 2}
            >
              <option value="">— Select CMZ —</option>
              {availableCmzs.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">
              OE Window
            </label>
            <select
              className="select w-full"
              value={windowMinutes}
              onChange={(e) => setWindowMinutes(e.target.value)}
              disabled={step !== 2}
            >
              {WINDOW_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>

        {selectedCmz && (
          <div className="mt-3 p-3 bg-indigo-900/20 border border-indigo-800/30 rounded-lg text-xs text-indigo-300 flex items-center gap-2">
            <Info className="w-3.5 h-3.5 flex-shrink-0" />
            OE will cover {format(new Date(), 'HH:mm')} → {format(addMinutes(new Date(), parseInt(windowMinutes)), 'HH:mm')} in 30-min slots for <strong>{selectedCmz}</strong>
          </div>
        )}

        {step === 2 && (
          <button
            className="btn-primary mt-4 flex items-center gap-2"
            disabled={!selectedCmz}
            onClick={() => setStep(3)}
          >
            Run Power Flow
            <ArrowRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── Step 3: Power Flow ──────────────────────────────────────────────── */}
      <div className={`card transition-opacity ${step < 3 ? 'opacity-40 pointer-events-none' : ''}`}>
        <StepHeader
          n={3} title="Run Power Flow"
          subtitle="DistFlow backward-forward sweep to compute voltages and thermal loading"
          state={stepState(3)}
        />

        {/* Prereq check */}
        <div className="mb-4 space-y-1.5 text-xs">
          <div className="flex items-center gap-2 text-gray-400">
            <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
            CMZ selected: <span className="font-mono text-gray-200">{selectedCmz}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-400">
            <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
            Window: {WINDOW_OPTIONS.find((o) => o.value === windowMinutes)?.label}
          </div>
          <div className="flex items-center gap-2 text-gray-400">
            <Info className="w-3.5 h-3.5 text-blue-400" />
            Ensure DER assets are registered in Grid & Assets before running
          </div>
        </div>

        {pfError && (
          <div className="mb-3 p-3 bg-red-900/20 border border-red-800/40 rounded-lg text-xs text-red-300 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            {pfError}
          </div>
        )}

        {step === 3 && !pfResult && (
          <button
            className="btn-primary flex items-center gap-2"
            disabled={pfRunning}
            onClick={handleRunPowerFlow}
          >
            {pfRunning ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Activity className="w-4 h-4" />
            )}
            {pfRunning ? 'Running DistFlow…' : 'Run DistFlow Power Flow'}
          </button>
        )}

        {pfResult && (
          <div className="space-y-3">
            {/* Summary */}
            <div className="grid grid-cols-4 gap-3">
              {[
                {
                  label: 'Converged',
                  value: pfResult.converged ? '✓ Yes' : '✗ No',
                  color: pfResult.converged ? 'text-green-400' : 'text-red-400',
                },
                { label: 'Max Voltage', value: `${pfResult.max_voltage_pu?.toFixed(3)} p.u.`,
                  color: pfResult.max_voltage_pu > 1.05 ? 'text-red-400' : 'text-green-400' },
                { label: 'Min Voltage', value: `${pfResult.min_voltage_pu?.toFixed(3)} p.u.`,
                  color: pfResult.min_voltage_pu < 0.95 ? 'text-red-400' : 'text-green-400' },
                { label: 'Violations',  value: `${pfResult.violations?.length ?? 0}`,
                  color: pfResult.violations?.length ? 'text-red-400' : 'text-green-400' },
              ].map((s) => (
                <div key={s.label} className="bg-gray-800/60 rounded-lg p-3 text-center">
                  <div className={`text-base font-bold ${s.color}`}>{s.value}</div>
                  <div className="text-xs text-gray-500">{s.label}</div>
                </div>
              ))}
            </div>

            {/* Violations */}
            {pfResult.violations?.length > 0 && (
              <div className="bg-red-900/20 border border-red-800/40 rounded-lg p-3">
                <div className="text-xs font-medium text-red-300 mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {pfResult.violations.length} Voltage Violation{pfResult.violations.length > 1 ? 's' : ''} — OE Required
                </div>
                <div className="space-y-1">
                  {pfResult.violations.slice(0, 5).map((v, i) => (
                    <div key={i} className="flex items-center justify-between text-xs text-red-300">
                      <span className="font-mono">{v.bus_id}</span>
                      <span>{v.voltage_pu?.toFixed(3)} p.u.</span>
                      <span className="text-red-400">{v.type}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              className="btn-primary flex items-center gap-2"
              onClick={() => setStep(4)}
            >
              Generate Operating Envelope
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* ── Step 4: Generate OE ─────────────────────────────────────────────── */}
      <div className={`card transition-opacity ${step < 4 ? 'opacity-40 pointer-events-none' : ''}`}>
        <StepHeader
          n={4} title="Generate Operating Envelope"
          subtitle="Build D4G IEC 62746-4 ReferenceEnergyCurveOperatingEnvelope_MarketDocument"
          state={stepState(4)}
        />

        <div className="mb-3 grid grid-cols-3 gap-3 text-xs">
          <div className="bg-gray-800/50 rounded-lg p-2.5">
            <div className="text-gray-500 mb-0.5">CMZ</div>
            <div className="font-mono text-gray-200">{selectedCmz}</div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-2.5">
            <div className="text-gray-500 mb-0.5">Window</div>
            <div className="text-gray-200">{WINDOW_OPTIONS.find((o) => o.value === windowMinutes)?.label}</div>
          </div>
          <div className="bg-gray-800/50 rounded-lg p-2.5">
            <div className="text-gray-500 mb-0.5">Format</div>
            <div className="text-indigo-300">D4G IEC 62746-4</div>
          </div>
        </div>

        {oeError && (
          <div className="mb-3 p-3 bg-red-900/20 border border-red-800/40 rounded-lg text-xs text-red-300 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            {oeError}
          </div>
        )}

        {step === 4 && !oeMessage && (
          <button
            className="btn-primary flex items-center gap-2"
            disabled={creatingEvent}
            onClick={handleGenerateOE}
          >
            {creatingEvent ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <FileText className="w-4 h-4" />
            )}
            {creatingEvent ? 'Building OE Message…' : 'Generate OE Message'}
          </button>
        )}

        {oeMessage && (
          <ReferencEnergyCurveView oeMessage={oeMessage} />
        )}
      </div>

      {/* ── Step 5: Send to Aggregator ──────────────────────────────────────── */}
      <div className={`card transition-opacity ${step < 5 ? 'opacity-40 pointer-events-none' : ''}`}>
        <StepHeader
          n={5} title="Send to DER Aggregator"
          subtitle="Dispatch OE via Kafka (dso_operating_envelope) and REST to the connected aggregator"
          state={stepState(5)}
        />

        <div className="mb-4">
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Target Aggregator
          </label>
          {aggregators.length > 0 ? (
            <select
              className="select w-full"
              value={selectedAgg}
              onChange={(e) => setSelectedAgg(e.target.value)}
              disabled={step !== 5}
            >
              <option value="">— All connected aggregators —</option>
              {aggregators.map((a: any) => (
                <option key={a.id || a.aggregator_ref} value={a.id}>
                  {a.aggregator_ref} ({a.protocol})
                </option>
              ))}
            </select>
          ) : (
            <div className="p-3 bg-gray-800 rounded-lg text-xs text-gray-400 flex items-center gap-2">
              <Network className="w-3.5 h-3.5" />
              No aggregators registered — OE will still be published to Kafka topic{' '}
              <span className="font-mono text-indigo-400">dso_operating_envelope</span>
            </div>
          )}
        </div>

        <div className="mb-4 p-3 bg-gray-800/50 rounded-lg text-xs space-y-1.5 text-gray-400">
          <div className="font-medium text-gray-300 mb-2">Delivery channels</div>
          <div className="flex items-center gap-2">
            <Radio className="w-3 h-3 text-indigo-400" />
            Kafka topic: <span className="font-mono text-indigo-300">dso_operating_envelope</span>
          </div>
          <div className="flex items-center gap-2">
            <Send className="w-3 h-3 text-indigo-400" />
            REST: aggregator endpoint URL (configured in Integrations)
          </div>
          <div className="flex items-center gap-2">
            <FileText className="w-3 h-3 text-indigo-400" />
            Format: D4G IEC 62746-4 with quality codes (A04/A06/A03 per slot)
          </div>
        </div>

        {sendResult ? (
          <div className={`p-3 rounded-lg border text-sm flex items-center gap-2 ${
            sendResult.ok
              ? 'bg-green-900/20 border-green-800/40 text-green-300'
              : 'bg-red-900/20 border-red-800/40 text-red-300'
          }`}>
            {sendResult.ok
              ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              : <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            }
            {sendResult.msg}
          </div>
        ) : (
          step === 5 && (
            <button
              className="btn-primary flex items-center gap-2"
              disabled={sending}
              onClick={handleSendToAggregator}
            >
              {sending ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              {sending ? 'Dispatching…' : 'Send Operating Envelope'}
            </button>
          )
        )}

        {step === 6 && (
          <button
            className="btn-secondary mt-3 flex items-center gap-2"
            onClick={() => {
              setStep(1); setPfResult(null); setOeMessage(null); setEventId(null)
              setSendResult(null); setSelectedCmz(''); setPfError(''); setOeError('')
            }}
          >
            <RefreshCw className="w-4 h-4" />
            Start New OE Cycle
          </button>
        )}
      </div>
    </div>
  )
}
