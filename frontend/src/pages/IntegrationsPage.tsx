import React, { useEffect, useState, useCallback } from 'react'
import {
  Plug,
  Radio,
  BarChart2,
  CloudLightning,
  Database,
  Sun,
  RefreshCw,
  Settings,
  CheckCircle,
  XCircle,
  Clock,
  Plus,
  Copy,
  Check,
  Zap,
  AlertTriangle,
  ChevronDown,
  MapPin,
  X,
  SlidersHorizontal,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { api } from '../api/client'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

// ─── Local types ──────────────────────────────────────────────────────────────

type IntegrationTab = 'connections' | 'oe-inspector' | 'aggregators' | 'sim-params'
type IntType = 'ADMS' | 'DER_AGGREGATOR' | 'SCADA' | 'MDMS' | 'WEATHER' | 'GIS_PROVIDER'
type AuthType = 'NONE' | 'API_KEY' | 'BASIC' | 'OAUTH2'
type OEProtocol = 'IEEE 2030.5' | 'OpenADR 2.0b' | 'IEC 62746-4' | 'Raw'

interface IntegrationConfig {
  id: string
  name: string
  description?: string
  integration_type: IntType
  mode: 'SIMULATION' | 'LIVE'
  base_url?: string
  auth_type: AuthType
  api_key?: string
  username?: string
  polling_interval_seconds: number
  timeout_seconds: number
  last_test_status?: 'OK' | 'FAILED'
  last_tested_at?: string
}

interface SimParams {
  [key: string]: number | string
}

interface AggregatorDevice {
  id: string
  aggregator_ref: string
  protocol: string
  status: string
  last_seen?: string
  assets_linked: number
  endpoint_url?: string
  ven_id?: string
}

interface PowerFlowResult {
  converged: boolean
  total_gen_kw: number
  total_load_kw: number
  losses_kw: number
  losses_pct: number
  bus_results: Array<{
    bus_name: string
    v_pu: number
    v_v: number
    p_injection_kw: number
  }>
  voltage_profile: Array<{ bus_id: string; v_pu: number }>
  violations: Array<{ bus_id: string; voltage: number; violation_type: string }>
}

interface OEMessage {
  asset_ref: string
  direction: string
  export_limit_kw: number
  import_limit_kw: number
  channel: string
  ack_status: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<IntType, React.ComponentType<{ className?: string }>> = {
  ADMS: BarChart2,
  DER_AGGREGATOR: Radio,
  SCADA: Database,
  MDMS: Database,
  WEATHER: CloudLightning,
  GIS_PROVIDER: MapPin,
}

const TYPE_COLOR: Record<IntType, string> = {
  ADMS: 'text-indigo-400 bg-indigo-900/30',
  DER_AGGREGATOR: 'text-emerald-400 bg-emerald-900/30',
  SCADA: 'text-amber-400 bg-amber-900/30',
  MDMS: 'text-blue-400 bg-blue-900/30',
  WEATHER: 'text-sky-400 bg-sky-900/30',
  GIS_PROVIDER: 'text-teal-400 bg-teal-900/30',
}

function relativeTime(iso?: string) {
  if (!iso) return 'Never'
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return '—'
  }
}

// ─── JSON syntax highlighter ──────────────────────────────────────────────────

function JsonHighlight({ json }: { json: unknown }) {
  const text = JSON.stringify(json, null, 2)
  const highlighted = text.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          return `<span class="text-blue-400">${match}</span>`
        }
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

// ─── Toast ────────────────────────────────────────────────────────────────────

interface Toast {
  id: number
  message: string
  type: 'success' | 'error'
}

let toastId = 0

function ToastContainer({ toasts, remove }: { toasts: Toast[]; remove: (id: number) => void }) {
  return (
    <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-[100]">
      {toasts.map((t) => (
        <div
          key={t.id}
          onClick={() => remove(t.id)}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium shadow-xl cursor-pointer transition-all
            ${t.type === 'success' ? 'bg-green-800 text-green-100 border border-green-600' : 'bg-red-800 text-red-100 border border-red-600'}`}
        >
          {t.type === 'success' ? <Check className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          {t.message}
        </div>
      ))}
    </div>
  )
}

// ─── Sim Params forms ─────────────────────────────────────────────────────────

function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <label className="text-xs font-medium text-gray-400">{label}</label>
        <span className="text-xs text-indigo-400 font-mono">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-indigo-500"
      />
      <div className="flex justify-between text-xs text-gray-600 mt-0.5">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

function AdmsSimParamsForm({
  params,
  onChange,
}: {
  params: SimParams
  onChange: (k: string, v: number | string) => void
}) {
  return (
    <div className="space-y-4">
      <SliderField
        label="Solar Peak Factor"
        value={Number(params.solar_peak_factor ?? 0.8)}
        min={0}
        max={1.5}
        step={0.05}
        onChange={(v) => onChange('solar_peak_factor', v)}
      />
      <SliderField
        label="Cloud Noise Factor"
        value={Number(params.cloud_noise_factor ?? 0.1)}
        min={0}
        max={0.3}
        step={0.01}
        onChange={(v) => onChange('cloud_noise_factor', v)}
      />
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Feeder Loading Warn %
        </label>
        <input
          type="number"
          min={50}
          max={100}
          className="input w-full"
          value={Number(params.feeder_loading_warn_pct ?? 80)}
          onChange={(e) => onChange('feeder_loading_warn_pct', parseFloat(e.target.value))}
        />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Voltage Nominal V</label>
          <input
            type="number"
            className="input w-full"
            value={Number(params.voltage_nominal_v ?? 230)}
            onChange={(e) => onChange('voltage_nominal_v', parseFloat(e.target.value))}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">High Warn V</label>
          <input
            type="number"
            className="input w-full"
            value={Number(params.voltage_high_warn_v ?? 253)}
            onChange={(e) => onChange('voltage_high_warn_v', parseFloat(e.target.value))}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Low Warn V</label>
          <input
            type="number"
            className="input w-full"
            value={Number(params.voltage_low_warn_v ?? 207)}
            onChange={(e) => onChange('voltage_low_warn_v', parseFloat(e.target.value))}
          />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          ADMS Poll Interval (seconds)
        </label>
        <input
          type="number"
          className="input w-full"
          value={Number(params.adms_poll_interval_seconds ?? 30)}
          onChange={(e) => onChange('adms_poll_interval_seconds', parseInt(e.target.value))}
        />
      </div>
    </div>
  )
}

function DerAggSimParamsForm({
  params,
  onChange,
}: {
  params: SimParams
  onChange: (k: string, v: number | string) => void
}) {
  return (
    <div className="space-y-4">
      <SliderField
        label="Aggregator Poll Interval (seconds)"
        value={Number(params.aggregator_poll_interval_seconds ?? 15)}
        min={5}
        max={120}
        step={5}
        onChange={(v) => onChange('aggregator_poll_interval_seconds', v)}
      />
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">OE ACK Timeout (seconds)</label>
        <input
          type="number"
          className="input w-full"
          value={Number(params.oe_ack_timeout_seconds ?? 60)}
          onChange={(e) => onChange('oe_ack_timeout_seconds', parseInt(e.target.value))}
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Default Response Time (seconds)
        </label>
        <input
          type="number"
          className="input w-full"
          value={Number(params.default_response_time_seconds ?? 300)}
          onChange={(e) => onChange('default_response_time_seconds', parseInt(e.target.value))}
        />
      </div>
    </div>
  )
}

function MdmsSimParamsForm({
  params,
  onChange,
}: {
  params: SimParams
  onChange: (k: string, v: number | string) => void
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Baseline Lookback Days
        </label>
        <input
          type="number"
          className="input w-full"
          value={Number(params.baseline_lookback_days ?? 30)}
          onChange={(e) => onChange('baseline_lookback_days', parseInt(e.target.value))}
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">
          Meter Read Interval (minutes)
        </label>
        <select
          className="select w-full"
          value={String(params.meter_read_interval_minutes ?? '30')}
          onChange={(e) => onChange('meter_read_interval_minutes', parseInt(e.target.value))}
        >
          <option value="5">5 minutes</option>
          <option value="15">15 minutes</option>
          <option value="30">30 minutes</option>
          <option value="60">60 minutes</option>
        </select>
      </div>
    </div>
  )
}

// ─── GIS Provider Card ────────────────────────────────────────────────────────

type GisOsmProvider = 'OpenStreetMap' | 'Synthetic'

function GISProviderCard({
  integration,
  onConfigure,
  onTest,
  testing,
}: {
  integration: IntegrationConfig
  onConfigure: () => void
  onTest: () => void
  testing: boolean
}) {
  const [gisProvider, setGisProvider] = useState<GisOsmProvider>('OpenStreetMap')
  const [previewOpen, setPreviewOpen] = useState(false)

  const statusOk = integration.last_test_status === 'OK'
  const statusFailed = integration.last_test_status === 'FAILED'
  const isLive = integration.mode === 'LIVE'

  return (
    <>
      <div className="card flex flex-col gap-3 hover:border-teal-700/40 transition-colors border-teal-800/20">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 text-teal-400 bg-teal-900/30">
              <MapPin className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-100 leading-tight">{integration.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">GIS Provider</div>
            </div>
          </div>
          <span
            className={`flex-shrink-0 px-2 py-0.5 rounded-full text-xs font-bold tracking-wide border
              ${isLive
                ? 'bg-green-900/50 text-green-400 border-green-700/50'
                : 'bg-gray-700/60 text-gray-400 border-gray-600/50'}`}
          >
            {isLive ? 'LIVE' : 'SIM'}
          </span>
        </div>

        {integration.description && (
          <p className="text-xs text-gray-500 leading-relaxed">{integration.description}</p>
        )}

        {/* Provider selector */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">Map Provider</label>
          <div className="flex gap-1 bg-gray-800 rounded-lg p-0.5 w-fit">
            {(['OpenStreetMap', 'Synthetic'] as GisOsmProvider[]).map((p) => (
              <button
                key={p}
                onClick={() => setGisProvider(p)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  gisProvider === p
                    ? 'bg-teal-700 text-white'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${
              statusOk ? 'bg-green-500' : statusFailed ? 'bg-red-500' : 'bg-gray-600'
            }`}
          />
          <span>{statusOk ? 'Connected' : statusFailed ? 'Failed' : 'Untested'}</span>
          <span className="ml-auto flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {relativeTime(integration.last_tested_at)}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 pt-1 border-t border-gray-700">
          <button
            onClick={onConfigure}
            className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1"
          >
            <Settings className="w-3 h-3" />
            Configure
          </button>
          <button
            onClick={onTest}
            disabled={testing}
            className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1 disabled:opacity-50"
          >
            {testing ? (
              <div className="w-3 h-3 border-2 border-gray-400/30 border-t-gray-400 rounded-full animate-spin" />
            ) : (
              <CheckCircle className="w-3 h-3" />
            )}
            Test
          </button>
          <button
            onClick={() => setPreviewOpen(true)}
            className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1 ml-auto text-teal-400 hover:text-teal-300"
          >
            <MapPin className="w-3 h-3" />
            Preview Map
          </button>
        </div>
      </div>

      {/* Preview Map Modal */}
      {previewOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
              <div>
                <span className="text-sm font-semibold text-gray-100">Map Provider Preview</span>
                <span className="ml-2 text-xs text-teal-400">{gisProvider}</span>
              </div>
              <button
                onClick={() => setPreviewOpen(false)}
                className="text-gray-400 hover:text-gray-200 p-1 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Integration Name</div>
                  <div className="text-sm text-gray-200 font-medium">{integration.name}</div>
                </div>
                <div className="bg-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Active Provider</div>
                  <div className="text-sm text-teal-400 font-medium">{gisProvider}</div>
                </div>
                <div className="bg-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Status</div>
                  <div className={`text-sm font-medium ${statusOk ? 'text-green-400' : statusFailed ? 'text-red-400' : 'text-gray-400'}`}>
                    {statusOk ? 'Connected' : statusFailed ? 'Failed' : 'Untested'}
                  </div>
                </div>
                <div className="bg-gray-800 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">Mode</div>
                  <div className={`text-sm font-medium ${isLive ? 'text-green-400' : 'text-gray-400'}`}>
                    {integration.mode}
                  </div>
                </div>
              </div>
              {gisProvider === 'OpenStreetMap' && (
                <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3 text-xs text-gray-400 space-y-1">
                  <div className="text-xs font-medium text-gray-300 mb-1.5">OpenStreetMap / Overpass API</div>
                  <div>Tile source: <span className="text-teal-400 font-mono">tile.openstreetmap.org</span></div>
                  <div>LV topology: <span className="text-teal-400 font-mono">overpass-api.de</span></div>
                  <div>Attribution: <span className="text-gray-300">© OpenStreetMap contributors</span></div>
                </div>
              )}
              {gisProvider === 'Synthetic' && (
                <div className="bg-gray-800/60 border border-gray-700 rounded-lg p-3 text-xs text-gray-400 space-y-1">
                  <div className="text-xs font-medium text-gray-300 mb-1.5">Synthetic GIS Provider</div>
                  <div>Topology: <span className="text-amber-400 font-mono">Algorithmically generated</span></div>
                  <div>Tile source: <span className="text-gray-500">No external tile dependency</span></div>
                  <div>Use case: <span className="text-gray-300">Offline / development / privacy-sensitive deployments</span></div>
                </div>
              )}
            </div>
            <div className="flex justify-end px-4 pb-4">
              <button onClick={() => setPreviewOpen(false)} className="btn-secondary text-xs px-4 py-2">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─── Integration Card ─────────────────────────────────────────────────────────

function IntegrationCard({
  integration,
  onConfigure,
  onSimParams,
  onToggleMode,
  onTest,
  testing,
}: {
  integration: IntegrationConfig
  onConfigure: () => void
  onSimParams: () => void
  onToggleMode: () => void
  onTest: () => void
  testing: boolean
}) {
  const Icon = TYPE_ICONS[integration.integration_type] || Plug
  const colorClass = TYPE_COLOR[integration.integration_type] || 'text-gray-400 bg-gray-700/30'
  const isLive = integration.mode === 'LIVE'
  const statusOk = integration.last_test_status === 'OK'
  const statusFailed = integration.last_test_status === 'FAILED'

  return (
    <div className="card flex flex-col gap-3 hover:border-gray-600 transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${colorClass}`}>
            <Icon className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-100 leading-tight">
              {integration.name}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              {integration.integration_type.replace(/_/g, ' ')}
            </div>
          </div>
        </div>
        {/* Mode badge */}
        <button
          onClick={onToggleMode}
          title="Click to toggle SIMULATION / LIVE"
          className={`flex-shrink-0 px-2 py-0.5 rounded-full text-xs font-bold tracking-wide border transition-colors
            ${isLive
              ? 'bg-green-900/50 text-green-400 border-green-700/50 hover:bg-green-800/50'
              : 'bg-gray-700/60 text-gray-400 border-gray-600/50 hover:bg-gray-600/60'}`}
        >
          {isLive ? 'LIVE' : 'SIM'}
        </button>
      </div>

      {/* Description */}
      {integration.description && (
        <p className="text-xs text-gray-500 leading-relaxed">{integration.description}</p>
      )}

      {/* Status row */}
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            statusOk ? 'bg-green-500' : statusFailed ? 'bg-red-500' : 'bg-gray-600'
          }`}
        />
        <span>
          {statusOk ? 'Connected' : statusFailed ? 'Failed' : 'Untested'}
        </span>
        <span className="ml-auto flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {relativeTime(integration.last_tested_at)}
        </span>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 pt-1 border-t border-gray-700">
        <button
          onClick={onConfigure}
          className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1"
        >
          <Settings className="w-3 h-3" />
          Configure
        </button>
        <button
          onClick={onTest}
          disabled={testing}
          className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1 disabled:opacity-50"
        >
          {testing ? (
            <div className="w-3 h-3 border-2 border-gray-400/30 border-t-gray-400 rounded-full animate-spin" />
          ) : (
            <CheckCircle className="w-3 h-3" />
          )}
          Test
        </button>
        <button
          onClick={onSimParams}
          className="btn-secondary text-xs py-1.5 px-2.5 flex items-center gap-1 ml-auto"
        >
          <BarChart2 className="w-3 h-3" />
          Sim Params
        </button>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function IntegrationsPage() {
  const [activeTab, setActiveTab] = useState<IntegrationTab>('connections')

  // Toast state
  const [toasts, setToasts] = useState<Toast[]>([])
  const addToast = useCallback((message: string, type: 'success' | 'error') => {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000)
  }, [])
  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // ── Tab 1: Integration Connections ─────────────────────────────────────────
  const [integrations, setIntegrations] = useState<IntegrationConfig[]>([])
  const [intLoading, setIntLoading] = useState(true)
  const [testingId, setTestingId] = useState<string | null>(null)

  // Configure modal
  const [configOpen, setConfigOpen] = useState(false)
  const [configTarget, setConfigTarget] = useState<IntegrationConfig | null>(null)
  const [configForm, setConfigForm] = useState({
    name: '',
    base_url: '',
    auth_type: 'NONE' as AuthType,
    api_key: '',
    username: '',
    password: '',
    polling_interval_seconds: 30,
    timeout_seconds: 10,
  })
  const [configSaving, setConfigSaving] = useState(false)

  // Sim params modal
  const [simOpen, setSimOpen] = useState(false)
  const [simTarget, setSimTarget] = useState<IntegrationConfig | null>(null)
  const [simParams, setSimParams] = useState<SimParams>({})
  const [simLoading, setSimLoading] = useState(false)
  const [simSaving, setSimSaving] = useState(false)

  const loadIntegrations = async () => {
    setIntLoading(true)
    try {
      const res = await api.integrations()
      setIntegrations(res.data || [])
    } catch {
      // silently fail — backend may not have data yet
    } finally {
      setIntLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'connections') loadIntegrations()
  }, [activeTab])

  const handleToggleMode = async (integration: IntegrationConfig) => {
    // Optimistic update
    setIntegrations((prev) =>
      prev.map((i) =>
        i.id === integration.id
          ? { ...i, mode: i.mode === 'SIMULATION' ? 'LIVE' : 'SIMULATION' }
          : i,
      ),
    )
    try {
      const res = await api.toggleIntegrationMode(integration.id)
      setIntegrations((prev) =>
        prev.map((i) => (i.id === integration.id ? { ...i, mode: res.data.mode } : i)),
      )
      addToast(`Switched to ${res.data.mode} mode`, 'success')
    } catch {
      // Revert
      setIntegrations((prev) =>
        prev.map((i) =>
          i.id === integration.id ? { ...i, mode: integration.mode } : i,
        ),
      )
      addToast('Failed to toggle mode', 'error')
    }
  }

  const handleTest = async (integration: IntegrationConfig) => {
    setTestingId(integration.id)
    try {
      const res = await api.testIntegration(integration.id)
      const ok = res.data?.status === 'OK'
      setIntegrations((prev) =>
        prev.map((i) =>
          i.id === integration.id
            ? { ...i, last_test_status: ok ? 'OK' : 'FAILED', last_tested_at: new Date().toISOString() }
            : i,
        ),
      )
      addToast(ok ? 'Connection test passed' : 'Connection test failed', ok ? 'success' : 'error')
    } catch {
      setIntegrations((prev) =>
        prev.map((i) =>
          i.id === integration.id
            ? { ...i, last_test_status: 'FAILED', last_tested_at: new Date().toISOString() }
            : i,
        ),
      )
      addToast('Connection test failed', 'error')
    } finally {
      setTestingId(null)
    }
  }

  const openConfigure = (integration: IntegrationConfig) => {
    setConfigTarget(integration)
    setConfigForm({
      name: integration.name,
      base_url: integration.base_url || '',
      auth_type: integration.auth_type,
      api_key: integration.api_key || '',
      username: integration.username || '',
      password: '',
      polling_interval_seconds: integration.polling_interval_seconds,
      timeout_seconds: integration.timeout_seconds,
    })
    setConfigOpen(true)
  }

  const handleSaveConfig = async () => {
    if (!configTarget) return
    setConfigSaving(true)
    try {
      const payload = { ...configForm }
      const res = await api.updateIntegration(configTarget.id, payload)
      setIntegrations((prev) =>
        prev.map((i) => (i.id === configTarget.id ? { ...i, ...res.data } : i)),
      )
      setConfigOpen(false)
      addToast('Integration updated', 'success')
    } catch {
      addToast('Failed to save integration', 'error')
    } finally {
      setConfigSaving(false)
    }
  }

  const openSimParams = async (integration: IntegrationConfig) => {
    setSimTarget(integration)
    setSimOpen(true)
    setSimLoading(true)
    try {
      const res = await api.getSimParams(integration.id)
      setSimParams(res.data || {})
    } catch {
      setSimParams({})
    } finally {
      setSimLoading(false)
    }
  }

  const handleSaveSimParams = async () => {
    if (!simTarget) return
    setSimSaving(true)
    try {
      await api.updateSimParams(simTarget.id, simParams)
      setSimOpen(false)
      addToast('Sim params saved', 'success')
    } catch {
      addToast('Failed to save sim params', 'error')
    } finally {
      setSimSaving(false)
    }
  }

  // ── Tab 2: OE Message Inspector ────────────────────────────────────────────
  const [dispatchedEvents, setDispatchedEvents] = useState<Array<{ id: string; event_ref: string; target_kw: number; cmz_id: string }>>([])
  const [selectedEventId, setSelectedEventId] = useState('')
  const [protocol, setProtocol] = useState<OEProtocol>('IEEE 2030.5')
  const [oeMessage, setOeMessage] = useState<unknown>(null)
  const [oeRows, setOeRows] = useState<OEMessage[]>([])
  const [oeLoading, setOeLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [eventsLoading, setEventsLoading] = useState(false)

  const loadDispatchedEvents = async () => {
    setEventsLoading(true)
    try {
      const res = await api.events('DISPATCHED')
      setDispatchedEvents(res.data || [])
    } catch {
      setDispatchedEvents([])
    } finally {
      setEventsLoading(false)
    }
  }

  const loadOeMessages = useCallback(async () => {
    if (!selectedEventId) return
    setOeLoading(true)
    try {
      const res = await api.oeMessagesFormatted(selectedEventId, protocol)
      setOeMessage(res.data?.formatted_message || null)
      setOeRows(res.data?.asset_messages || [])
    } catch {
      // Show example data if backend returns nothing
      setOeMessage({
        mRID: 'EVT-SSEN-0001-AST-V1G-001',
        description: 'Peak reduction curtailment — CMZ-SHETLAND',
        DERControlBase: {
          opModMaxLimW: { value: 7000, multiplier: -3, unit: 'W' },
        },
        interval: { start: 1711098000, duration: 1800 },
      })
      setOeRows([])
    } finally {
      setOeLoading(false)
    }
  }, [selectedEventId, protocol])

  useEffect(() => {
    if (activeTab === 'oe-inspector') {
      loadDispatchedEvents()
    }
  }, [activeTab])

  useEffect(() => {
    if (selectedEventId) loadOeMessages()
  }, [selectedEventId, protocol, loadOeMessages])

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(oeMessage, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const selectedEvent = dispatchedEvents.find((e) => e.id === selectedEventId)

  // ── Tab 3: Connected Aggregators ───────────────────────────────────────────
  const [aggregators, setAggregators] = useState<AggregatorDevice[]>([])
  const [aggLoading, setAggLoading] = useState(true)
  const [aggRegOpen, setAggRegOpen] = useState(false)
  const [regForm, setRegForm] = useState({
    aggregator_ref: '',
    protocol: 'IEEE 2030.5',
    ven_id: '',
    endpoint_url: '',
  })
  const [regSaving, setRegSaving] = useState(false)

  const [powerFlowResult, setPowerFlowResult] = useState<PowerFlowResult | null>(null)
  const [pfRunning, setPfRunning] = useState(false)

  const loadAggregators = async () => {
    setAggLoading(true)
    try {
      const res = await api.aggregatorDevices()
      setAggregators(res.data || [])
    } catch {
      setAggregators([])
    } finally {
      setAggLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab === 'aggregators') loadAggregators()
  }, [activeTab])

  const handleRegisterAggregator = async () => {
    setRegSaving(true)
    try {
      const res = await api.registerAggregator(regForm)
      setAggregators((prev) => [res.data, ...prev])
      setAggRegOpen(false)
      setRegForm({ aggregator_ref: '', protocol: 'IEEE 2030.5', ven_id: '', endpoint_url: '' })
      addToast('Aggregator registered', 'success')
    } catch {
      addToast('Failed to register aggregator', 'error')
    } finally {
      setRegSaving(false)
    }
  }

  const handleRunPowerFlow = async () => {
    setPfRunning(true)
    try {
      const res = await api.runPowerFlow()
      setPowerFlowResult(res.data)
      addToast('Power flow converged', 'success')
    } catch {
      addToast('Power flow failed to run', 'error')
    } finally {
      setPfRunning(false)
    }
  }

  // ─── Render ─────────────────────────────────────────────────────────────────

  const TABS: { id: IntegrationTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'connections',  label: 'Integration Connections', icon: Plug             },
    { id: 'oe-inspector', label: 'OE Message Inspector',    icon: Radio            },
    { id: 'aggregators',  label: 'Connected Aggregators',   icon: Database         },
    { id: 'sim-params',   label: 'Simulation Parameters',   icon: SlidersHorizontal },
  ]

  return (
    <div className="space-y-6">
      <ToastContainer toasts={toasts} remove={removeToast} />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Integrations</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Configure external system connections, inspect OE messages and manage aggregators
          </p>
        </div>
        <button
          onClick={() => {
            if (activeTab === 'connections') loadIntegrations()
            if (activeTab === 'aggregators') loadAggregators()
          }}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={
              activeTab === id
                ? 'tab-active flex items-center gap-1.5'
                : 'tab-inactive flex items-center gap-1.5'
            }
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab 1: Integration Connections ──────────────────────────────────── */}
      {activeTab === 'connections' && (
        <>
          {intLoading ? (
            <LoadingSpinner fullPage label="Loading integrations..." />
          ) : integrations.length === 0 ? (
            <div className="card text-center py-16">
              <Plug className="w-10 h-10 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400 font-medium">No integrations configured</p>
              <p className="text-sm text-gray-600 mt-1">
                Integrations will appear here once created via the API or seeder.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {integrations.map((intg) =>
                intg.integration_type === 'GIS_PROVIDER' ? (
                  <GISProviderCard
                    key={intg.id}
                    integration={intg}
                    onConfigure={() => openConfigure(intg)}
                    onTest={() => handleTest(intg)}
                    testing={testingId === intg.id}
                  />
                ) : (
                  <IntegrationCard
                    key={intg.id}
                    integration={intg}
                    onConfigure={() => openConfigure(intg)}
                    onSimParams={() => openSimParams(intg)}
                    onToggleMode={() => handleToggleMode(intg)}
                    onTest={() => handleTest(intg)}
                    testing={testingId === intg.id}
                  />
                ),
              )}
            </div>
          )}
        </>
      )}

      {/* ── Tab 2: OE Message Inspector ──────────────────────────────────────── */}
      {activeTab === 'oe-inspector' && (
        <div className="space-y-4">
          {/* Controls row */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-400 whitespace-nowrap">Event</label>
              <div className="relative">
                <select
                  className="select pr-8 min-w-[220px]"
                  value={selectedEventId}
                  onChange={(e) => setSelectedEventId(e.target.value)}
                  disabled={eventsLoading}
                >
                  <option value="">— select dispatched event —</option>
                  {dispatchedEvents.map((ev) => (
                    <option key={ev.id} value={ev.id}>
                      {ev.event_ref} ({ev.target_kw} kW)
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-400 whitespace-nowrap">Protocol</label>
              <div className="flex gap-1 bg-gray-800 rounded-lg p-0.5">
                {(['IEEE 2030.5', 'OpenADR 2.0b', 'IEC 62746-4', 'Raw'] as OEProtocol[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => setProtocol(p)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      protocol === p
                        ? 'bg-indigo-600 text-white'
                        : 'text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Summary */}
          {selectedEvent && (
            <div className="card flex flex-wrap gap-4 text-xs">
              <div>
                <span className="text-gray-500">Event Ref</span>
                <span className="ml-2 font-mono text-indigo-300">{selectedEvent.event_ref}</span>
              </div>
              <div>
                <span className="text-gray-500">Target</span>
                <span className="ml-2 text-amber-400 font-semibold">{selectedEvent.target_kw} kW</span>
              </div>
              <div>
                <span className="text-gray-500">CMZ</span>
                <span className="ml-2 text-gray-300">{selectedEvent.cmz_id}</span>
              </div>
              <div>
                <span className="text-gray-500">Protocol</span>
                <span className="ml-2 text-green-400">{protocol}</span>
              </div>
            </div>
          )}

          {/* Message viewer */}
          <div className="card bg-gray-900 p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-700 bg-gray-800/60">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Formatted Message
              </span>
              <button
                onClick={handleCopy}
                disabled={!oeMessage}
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 disabled:opacity-40 transition-colors"
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5 text-green-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <div className="p-4 min-h-[200px]">
              {oeLoading ? (
                <div className="flex items-center justify-center py-10">
                  <div className="w-6 h-6 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
                </div>
              ) : oeMessage ? (
                <JsonHighlight json={oeMessage} />
              ) : (
                <div className="text-center py-10 text-gray-600 text-sm">
                  {selectedEventId
                    ? 'No message data returned.'
                    : 'Select a dispatched event above to inspect its OE messages.'}
                </div>
              )}
            </div>
          </div>

          {/* Per-asset message table */}
          {oeRows.length > 0 && (
            <div className="card p-0">
              <div className="px-4 py-3 border-b border-gray-700">
                <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                  Asset Messages
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-800/50">
                      {['Asset Ref', 'Direction', 'Export Limit kW', 'Import Limit kW', 'Channel', 'ACK Status'].map((h) => (
                        <th key={h} className="table-header text-left">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {oeRows.map((row, i) => (
                      <tr key={i} className="table-row">
                        <td className="table-cell font-mono text-indigo-300 text-xs">{row.asset_ref}</td>
                        <td className="table-cell text-xs">{row.direction}</td>
                        <td className="table-cell text-xs text-amber-400">{row.export_limit_kw ?? '—'}</td>
                        <td className="table-cell text-xs text-blue-400">{row.import_limit_kw ?? '—'}</td>
                        <td className="table-cell text-xs text-gray-400">{row.channel}</td>
                        <td className="table-cell text-xs">
                          <span
                            className={
                              row.ack_status === 'ACK'
                                ? 'badge-online'
                                : row.ack_status === 'NACK'
                                ? 'badge-offline'
                                : 'badge-gray'
                            }
                          >
                            {row.ack_status || 'PENDING'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Tab 3: Connected Aggregators ─────────────────────────────────────── */}
      {activeTab === 'aggregators' && (
        <div className="space-y-6">
          <div className="flex justify-end">
            <button
              onClick={() => setAggRegOpen(true)}
              className="btn-primary flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Register Aggregator
            </button>
          </div>

          {/* Aggregators table */}
          {aggLoading ? (
            <LoadingSpinner fullPage label="Loading aggregators..." />
          ) : (
            <div className="card p-0">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-800/50">
                      {['Aggregator Ref', 'Protocol', 'Status', 'Last Seen', 'Assets Linked', 'Actions'].map((h) => (
                        <th key={h} className="table-header text-left">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {aggregators.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="text-center py-12 text-gray-500">
                          No aggregators registered yet
                        </td>
                      </tr>
                    ) : (
                      aggregators.map((agg) => (
                        <tr key={agg.id} className="table-row">
                          <td className="table-cell font-mono text-indigo-300 text-xs">{agg.aggregator_ref}</td>
                          <td className="table-cell">
                            <span className="badge-info">{agg.protocol}</span>
                          </td>
                          <td className="table-cell">
                            <span
                              className={
                                agg.status === 'ACTIVE'
                                  ? 'badge-online'
                                  : agg.status === 'INACTIVE'
                                  ? 'badge-offline'
                                  : 'badge-gray'
                              }
                            >
                              {agg.status}
                            </span>
                          </td>
                          <td className="table-cell text-xs text-gray-400">
                            {relativeTime(agg.last_seen)}
                          </td>
                          <td className="table-cell text-xs text-gray-300">{agg.assets_linked}</td>
                          <td className="table-cell">
                            <span className="text-xs text-indigo-400 hover:text-indigo-300 cursor-pointer">
                              View
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Power Flow section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-gray-100">Power Flow Analysis</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Run AC power flow across the active grid topology
                </p>
              </div>
              <button
                onClick={handleRunPowerFlow}
                disabled={pfRunning}
                className="btn-primary flex items-center gap-2 disabled:opacity-50"
              >
                {pfRunning ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                {pfRunning ? 'Running...' : 'Run Power Flow'}
              </button>
            </div>

            {powerFlowResult && (
              <div className="space-y-4">
                {/* Summary cards */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <div className={`card-sm ${powerFlowResult.converged ? 'border-green-700/40 bg-green-900/10' : 'border-red-700/40 bg-red-900/10'}`}>
                    <div className="text-xs text-gray-500 mb-1">Converged</div>
                    <div className={`text-lg font-bold ${powerFlowResult.converged ? 'text-green-400' : 'text-red-400'}`}>
                      {powerFlowResult.converged ? 'Yes' : 'No'}
                    </div>
                  </div>
                  <div className="card-sm">
                    <div className="text-xs text-gray-500 mb-1">Total Generation</div>
                    <div className="text-lg font-bold text-gray-100">
                      {powerFlowResult.total_gen_kw.toFixed(1)}
                      <span className="text-xs text-gray-500 ml-1">kW</span>
                    </div>
                  </div>
                  <div className="card-sm">
                    <div className="text-xs text-gray-500 mb-1">Total Load</div>
                    <div className="text-lg font-bold text-gray-100">
                      {powerFlowResult.total_load_kw.toFixed(1)}
                      <span className="text-xs text-gray-500 ml-1">kW</span>
                    </div>
                  </div>
                  <div className="card-sm">
                    <div className="text-xs text-gray-500 mb-1">Losses</div>
                    <div className="text-lg font-bold text-amber-400">
                      {powerFlowResult.losses_kw.toFixed(2)}
                      <span className="text-xs text-gray-500 ml-1">kW</span>
                    </div>
                  </div>
                  <div className="card-sm">
                    <div className="text-xs text-gray-500 mb-1">Losses %</div>
                    <div className="text-lg font-bold text-amber-400">
                      {powerFlowResult.losses_pct.toFixed(2)}%
                    </div>
                  </div>
                </div>

                {/* Voltage Profile chart */}
                {powerFlowResult.voltage_profile?.length > 0 && (
                  <div className="card">
                    <div className="text-sm font-semibold text-gray-200 mb-3">Voltage Profile</div>
                    <ResponsiveContainer width="100%" height={160}>
                      <BarChart
                        data={powerFlowResult.voltage_profile}
                        layout="vertical"
                        margin={{ left: 60, right: 20, top: 0, bottom: 0 }}
                      >
                        <XAxis
                          type="number"
                          domain={[0.9, 1.1]}
                          tick={{ fill: '#9ca3af', fontSize: 10 }}
                          tickLine={false}
                        />
                        <YAxis
                          dataKey="bus_id"
                          type="category"
                          tick={{ fill: '#9ca3af', fontSize: 10 }}
                          width={55}
                          tickLine={false}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: '#1f2937',
                            border: '1px solid #374151',
                            borderRadius: 6,
                            fontSize: 11,
                          }}
                          itemStyle={{ color: '#e5e7eb' }}
                          labelStyle={{ color: '#9ca3af' }}
                          formatter={(val: number) => [`${val.toFixed(4)} pu`, 'Voltage']}
                        />
                        <Bar dataKey="v_pu" radius={[0, 3, 3, 0]}>
                          {powerFlowResult.voltage_profile.map((entry, idx) => (
                            <Cell
                              key={idx}
                              fill={
                                entry.v_pu > 1.05 || entry.v_pu < 0.95
                                  ? '#ef4444'
                                  : entry.v_pu > 1.02 || entry.v_pu < 0.98
                                  ? '#f59e0b'
                                  : '#6366f1'
                              }
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Violations table */}
                {powerFlowResult.violations?.length > 0 && (
                  <div className="card p-0">
                    <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700">
                      <AlertTriangle className="w-4 h-4 text-red-400" />
                      <span className="text-sm font-semibold text-red-400">
                        Voltage Violations ({powerFlowResult.violations.length})
                      </span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="bg-gray-800/50">
                            <th className="table-header text-left">Bus ID</th>
                            <th className="table-header text-left">Voltage (pu)</th>
                            <th className="table-header text-left">Violation Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {powerFlowResult.violations.map((v, i) => (
                            <tr key={i} className="table-row">
                              <td className="table-cell font-mono text-xs text-indigo-300">{v.bus_id}</td>
                              <td className="table-cell text-xs text-red-400 font-mono">{v.voltage.toFixed(4)}</td>
                              <td className="table-cell text-xs">
                                <span className="badge-offline">{v.violation_type}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Bus Results table */}
                {powerFlowResult.bus_results?.length > 0 && (
                  <div className="card p-0">
                    <div className="px-4 py-3 border-b border-gray-700">
                      <span className="text-sm font-semibold text-gray-200">Bus Results</span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead>
                          <tr className="bg-gray-800/50">
                            <th className="table-header text-left">Bus Name</th>
                            <th className="table-header text-left">V (pu)</th>
                            <th className="table-header text-left">V (V)</th>
                            <th className="table-header text-left">P Injection kW</th>
                          </tr>
                        </thead>
                        <tbody>
                          {powerFlowResult.bus_results.map((bus, i) => (
                            <tr key={i} className="table-row">
                              <td className="table-cell text-xs text-gray-200">{bus.bus_name}</td>
                              <td className="table-cell text-xs font-mono text-indigo-300">
                                {bus.v_pu.toFixed(4)}
                              </td>
                              <td className="table-cell text-xs font-mono text-gray-300">
                                {bus.v_v.toFixed(1)}
                              </td>
                              <td className="table-cell text-xs font-mono text-amber-400">
                                {bus.p_injection_kw.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Simulation Parameters tab ────────────────────────────────────────── */}
      {activeTab === 'sim-params' && (
        <div className="space-y-4">
          <div className="p-3 bg-indigo-900/20 border border-indigo-800/30 rounded-lg text-xs text-indigo-300 flex items-start gap-2">
            <SlidersHorizontal className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <div>
              These parameters control what the platform simulates when an integration is in <strong>SIMULATION</strong> mode.
              When switched to <strong>LIVE</strong>, the platform reads from the real external endpoint instead.
              Changes take effect on the next simulation cycle (every 30 s for ADMS, every 15 min for forecasts).
            </div>
          </div>

          {integrations.length === 0 ? (
            <div className="card text-center py-12 text-gray-500 text-sm">No integrations loaded — refresh the page.</div>
          ) : (
            integrations.map((intg) => {
              let params: Record<string, any> = {}
              try { params = JSON.parse((intg as any).sim_params || '{}') } catch {}
              const entries = Object.entries(params)
              if (entries.length === 0) return null
              return (
                <div key={intg.id} className="card">
                  <div className="flex items-center gap-2 mb-3">
                    <Settings className="w-4 h-4 text-gray-400" />
                    <h3 className="text-sm font-semibold text-gray-200">{intg.name}</h3>
                    <span className="text-xs text-gray-500">({intg.integration_type})</span>
                    <span className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
                      intg.mode === 'LIVE'
                        ? 'bg-green-900/40 text-green-400'
                        : 'bg-amber-900/40 text-amber-400'
                    }`}>{intg.mode}</span>
                  </div>
                  {intg.mode === 'LIVE' && (
                    <div className="mb-3 text-xs text-green-400 flex items-center gap-1.5">
                      <CheckCircle className="w-3 h-3" />
                      Live mode — using real endpoint: <span className="font-mono">{(intg as any).base_url || 'not set'}</span>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-2">
                    {entries.map(([key, val]) => (
                      <div key={key} className="bg-gray-800/50 rounded-lg p-2.5">
                        <div className="text-xs text-gray-500 font-mono mb-0.5">{key}</div>
                        <div className="text-xs text-gray-200 font-mono">{String(val)}</div>
                        <div className="text-xs text-gray-600 mt-0.5">
                          {/* human-readable hints */}
                          {key.includes('voltage') && 'Volts'}
                          {key.includes('factor') && '× multiplier'}
                          {key.includes('pct') && '%'}
                          {key.includes('interval') && 'seconds'}
                          {key.includes('timeout') && 'seconds'}
                          {key.includes('minutes') && 'minutes'}
                        </div>
                      </div>
                    ))}
                  </div>
                  <button
                    className="btn-secondary text-xs mt-3 flex items-center gap-1.5"
                    onClick={() => { setConfigTarget(intg as any); setSimOpen(true) }}
                  >
                    <SlidersHorizontal className="w-3 h-3" />
                    Edit Simulation Parameters
                  </button>
                </div>
              )
            })
          )}
        </div>
      )}

      {/* ── Configure Modal ──────────────────────────────────────────────────── */}
      <Modal
        isOpen={configOpen}
        onClose={() => setConfigOpen(false)}
        title={`Configure — ${configTarget?.name || ''}`}
        size="md"
        footer={
          <>
            <button onClick={() => setConfigOpen(false)} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleSaveConfig}
              disabled={configSaving}
              className="btn-primary flex items-center gap-2"
            >
              {configSaving && (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              Save
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Integration Name</label>
            <input
              className="input w-full"
              value={configForm.name}
              onChange={(e) => setConfigForm((p) => ({ ...p, name: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Base URL</label>
            <input
              className="input w-full"
              placeholder="https://adms.utility.com/api/v1"
              value={configForm.base_url}
              onChange={(e) => setConfigForm((p) => ({ ...p, base_url: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Auth Type</label>
            <select
              className="select w-full"
              value={configForm.auth_type}
              onChange={(e) =>
                setConfigForm((p) => ({ ...p, auth_type: e.target.value as AuthType }))
              }
            >
              <option value="NONE">None</option>
              <option value="API_KEY">API Key</option>
              <option value="BASIC">Basic (Username / Password)</option>
              <option value="OAUTH2">OAuth 2.0</option>
            </select>
          </div>
          {configForm.auth_type === 'API_KEY' && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">API Key</label>
              <input
                className="input w-full"
                type="password"
                value={configForm.api_key}
                onChange={(e) => setConfigForm((p) => ({ ...p, api_key: e.target.value }))}
              />
            </div>
          )}
          {configForm.auth_type === 'BASIC' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Username</label>
                <input
                  className="input w-full"
                  value={configForm.username}
                  onChange={(e) => setConfigForm((p) => ({ ...p, username: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Password</label>
                <input
                  className="input w-full"
                  type="password"
                  value={configForm.password}
                  onChange={(e) => setConfigForm((p) => ({ ...p, password: e.target.value }))}
                />
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Polling Interval (seconds)
              </label>
              <input
                type="number"
                className="input w-full"
                value={configForm.polling_interval_seconds}
                onChange={(e) =>
                  setConfigForm((p) => ({
                    ...p,
                    polling_interval_seconds: parseInt(e.target.value) || 0,
                  }))
                }
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                className="input w-full"
                value={configForm.timeout_seconds}
                onChange={(e) =>
                  setConfigForm((p) => ({
                    ...p,
                    timeout_seconds: parseInt(e.target.value) || 0,
                  }))
                }
              />
            </div>
          </div>
        </div>
      </Modal>

      {/* ── Sim Params Modal ─────────────────────────────────────────────────── */}
      <Modal
        isOpen={simOpen}
        onClose={() => setSimOpen(false)}
        title={`Sim Parameters — ${simTarget?.name || ''}`}
        size="md"
        footer={
          <>
            <button onClick={() => setSimOpen(false)} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleSaveSimParams}
              disabled={simSaving}
              className="btn-primary flex items-center gap-2"
            >
              {simSaving && (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              Save Params
            </button>
          </>
        }
      >
        {simLoading ? (
          <div className="flex justify-center py-8">
            <div className="w-6 h-6 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin" />
          </div>
        ) : simTarget?.integration_type === 'ADMS' ? (
          <AdmsSimParamsForm
            params={simParams}
            onChange={(k, v) => setSimParams((p) => ({ ...p, [k]: v }))}
          />
        ) : simTarget?.integration_type === 'DER_AGGREGATOR' ? (
          <DerAggSimParamsForm
            params={simParams}
            onChange={(k, v) => setSimParams((p) => ({ ...p, [k]: v }))}
          />
        ) : simTarget?.integration_type === 'MDMS' ? (
          <MdmsSimParamsForm
            params={simParams}
            onChange={(k, v) => setSimParams((p) => ({ ...p, [k]: v }))}
          />
        ) : (
          <div className="text-center py-8 text-gray-500 text-sm">
            No sim params available for this integration type.
          </div>
        )}
      </Modal>

      {/* ── Register Aggregator Modal ────────────────────────────────────────── */}
      <Modal
        isOpen={aggRegOpen}
        onClose={() => setAggRegOpen(false)}
        title="Register Aggregator"
        size="md"
        footer={
          <>
            <button onClick={() => setAggRegOpen(false)} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleRegisterAggregator}
              disabled={regSaving || !regForm.aggregator_ref}
              className="btn-primary flex items-center gap-2 disabled:opacity-50"
            >
              {regSaving && (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              Register
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Aggregator Reference *
            </label>
            <input
              className="input w-full"
              placeholder="AGG-NORTH-001"
              value={regForm.aggregator_ref}
              onChange={(e) => setRegForm((p) => ({ ...p, aggregator_ref: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Protocol</label>
            <select
              className="select w-full"
              value={regForm.protocol}
              onChange={(e) => setRegForm((p) => ({ ...p, protocol: e.target.value }))}
            >
              <option value="IEEE 2030.5">IEEE 2030.5</option>
              <option value="OpenADR 2.0b">OpenADR 2.0b</option>
              <option value="REST">REST</option>
            </select>
          </div>
          {regForm.protocol === 'OpenADR 2.0b' && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">VEN ID</label>
              <input
                className="input w-full"
                placeholder="VEN-001"
                value={regForm.ven_id}
                onChange={(e) => setRegForm((p) => ({ ...p, ven_id: e.target.value }))}
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Endpoint URL
            </label>
            <input
              className="input w-full"
              placeholder="https://aggregator.example.com/oe-receive"
              value={regForm.endpoint_url}
              onChange={(e) => setRegForm((p) => ({ ...p, endpoint_url: e.target.value }))}
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}
