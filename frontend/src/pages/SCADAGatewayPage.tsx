import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import {
  Server,
  Key,
  Plus,
  Trash2,
  Upload,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Eye,
  EyeOff,
  Copy,
  AlertTriangle,
  Wifi,
  Database,
} from 'lucide-react'
import clsx from 'clsx'

// ─── Types ────────────────────────────────────────────────────────────────────

interface SCADAEndpoint {
  id: string
  name: string
  protocol: string
  target_url: string
  is_active: boolean
  push_interval_seconds: number
  push_lv_voltages: boolean
  push_feeder_loading: boolean
  push_der_outputs: boolean
  push_oe_limits: boolean
  push_flex_events: boolean
  last_push_at: string | null
  last_push_status: string | null
  last_push_error: string | null
  created_at: string
}

interface DaaSKey {
  id: string
  name: string
  client_name: string
  key_prefix: string
  is_active: boolean
  rate_limit_per_hour: number
  total_requests: number
  last_used_at: string | null
  expires_at: string | null
  can_read_lv_voltages: boolean
  can_read_feeder_loading: boolean
  can_read_der_outputs: boolean
  can_read_oe_limits: boolean
  can_read_flex_events: boolean
  created_at: string
}

interface DaaSKeyCreated extends DaaSKey {
  api_key: string
}

const PROTOCOL_COLORS: Record<string, string> = {
  REST_JSON: 'bg-blue-900/50 text-blue-300 border-blue-800',
  MODBUS_TCP: 'bg-orange-900/50 text-orange-300 border-orange-800',
  DNP3: 'bg-purple-900/50 text-purple-300 border-purple-800',
  'OPC-UA': 'bg-teal-900/50 text-teal-300 border-teal-800',
  MQTT: 'bg-green-900/50 text-green-300 border-green-800',
}

function ProtocolBadge({ protocol }: { protocol: string }) {
  const cls = PROTOCOL_COLORS[protocol] ?? 'bg-gray-800 text-gray-300 border-gray-700'
  return (
    <span className={clsx('px-2 py-0.5 rounded text-xs font-mono border', cls)}>
      {protocol}
    </span>
  )
}

function StatusDot({ ok }: { ok: boolean | null }) {
  if (ok === null) return <span className="text-gray-500 text-xs">—</span>
  return ok ? (
    <CheckCircle className="w-4 h-4 text-green-400" />
  ) : (
    <XCircle className="w-4 h-4 text-red-400" />
  )
}

// ─── SCADA Endpoints Tab ──────────────────────────────────────────────────────

function EndpointsTab() {
  const [endpoints, setEndpoints] = useState<SCADAEndpoint[]>([])
  const [loading, setLoading] = useState(true)
  const [pushing, setPushing] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [newEp, setNewEp] = useState({
    name: '',
    protocol: 'REST_JSON',
    target_url: '',
    push_interval_seconds: 60,
  })

  const load = async () => {
    try {
      const r = await api.scadaEndpoints()
      setEndpoints(r.data)
    } catch {
      setEndpoints([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handlePush = async (id: string) => {
    setPushing(id)
    try {
      await api.pushScadaEndpoint(id)
      await load()
    } finally {
      setPushing(null)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this SCADA endpoint?')) return
    try {
      await api.deleteScadaEndpoint(id)
      await load()
    } catch {/* ignore */}
  }

  const handleAdd = async () => {
    try {
      await api.createScadaEndpoint(newEp)
      setShowAdd(false)
      setNewEp({ name: '', protocol: 'REST_JSON', target_url: '', push_interval_seconds: 60 })
      await load()
    } catch {/* ignore */}
  }

  if (loading) return <div className="text-gray-500 text-sm p-4">Loading endpoints…</div>

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">SCADA Push Endpoints</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Configure external SCADA systems to receive real-time LV DERMS data
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-3 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Endpoint
        </button>
      </div>

      {/* Architecture note */}
      <div className="bg-amber-900/20 border border-amber-800/40 rounded-lg p-3 flex gap-3">
        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-amber-300/80">
          <strong className="text-amber-300">Hardware gateway note:</strong> MODBUS_TCP, DNP3, and OPC-UA protocols
          require the L&T DERMS Edge Agent hardware gateway. REST_JSON and MQTT operate directly over IP.
          In simulation mode, non-REST protocols will return a test acknowledgement without physical transmission.
        </p>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
          <h3 className="text-sm font-medium text-white">New SCADA Endpoint</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Name</label>
              <input
                value={newEp.name}
                onChange={(e) => setNewEp({ ...newEp, name: e.target.value })}
                placeholder="e.g. Primary SCADA"
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Protocol</label>
              <select
                value={newEp.protocol}
                onChange={(e) => setNewEp({ ...newEp, protocol: e.target.value })}
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {Object.keys(PROTOCOL_COLORS).map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs text-gray-400 block mb-1">Target URL / Address</label>
              <input
                value={newEp.target_url}
                onChange={(e) => setNewEp({ ...newEp, target_url: e.target.value })}
                placeholder="https://scada.example.com/api/push"
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Push Interval (seconds)</label>
              <input
                type="number"
                min={10}
                max={3600}
                value={newEp.push_interval_seconds}
                onChange={(e) =>
                  setNewEp({ ...newEp, push_interval_seconds: parseInt(e.target.value) || 60 })
                }
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowAdd(false)}
              className="text-sm text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleAdd}
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-1.5 rounded-lg transition-colors"
            >
              Create
            </button>
          </div>
        </div>
      )}

      {/* Endpoints list */}
      {endpoints.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <Server className="w-8 h-8 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No SCADA endpoints configured yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {endpoints.map((ep) => (
            <div key={ep.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className={clsx(
                    'w-2 h-2 rounded-full mt-2 flex-shrink-0',
                    ep.is_active ? 'bg-green-400' : 'bg-gray-600'
                  )} />
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-white text-sm">{ep.name}</span>
                      <ProtocolBadge protocol={ep.protocol} />
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5 font-mono truncate max-w-xs">
                      {ep.target_url}
                    </div>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Every {ep.push_interval_seconds}s
                      </span>
                      {ep.last_push_at && (
                        <span>Last push: {new Date(ep.last_push_at).toLocaleTimeString()}</span>
                      )}
                    </div>

                    {/* Data flags */}
                    <div className="flex flex-wrap gap-1 mt-2">
                      {[
                        { key: 'push_lv_voltages', label: 'LV Voltages' },
                        { key: 'push_feeder_loading', label: 'Feeder Load' },
                        { key: 'push_der_outputs', label: 'DER Outputs' },
                        { key: 'push_oe_limits', label: 'OE Limits' },
                        { key: 'push_flex_events', label: 'Flex Events' },
                      ].map(({ key, label }) => (
                        <span
                          key={key}
                          className={clsx(
                            'px-1.5 py-0.5 rounded text-xs',
                            (ep as unknown as Record<string, unknown>)[key]
                              ? 'bg-green-900/40 text-green-400'
                              : 'bg-gray-800 text-gray-600 line-through'
                          )}
                        >
                          {label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  <StatusDot
                    ok={
                      ep.last_push_status === null
                        ? null
                        : ep.last_push_status === 'ok'
                    }
                  />
                  <button
                    onClick={() => handlePush(ep.id)}
                    disabled={pushing === ep.id}
                    className="flex items-center gap-1.5 bg-blue-700/50 hover:bg-blue-700 text-blue-300 hover:text-white text-xs px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {pushing === ep.id ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Upload className="w-3.5 h-3.5" />
                    )}
                    Push Now
                  </button>
                  <button
                    onClick={() => handleDelete(ep.id)}
                    className="text-gray-600 hover:text-red-400 transition-colors p-1"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {ep.last_push_error && (
                <div className="mt-2 text-xs text-red-400 bg-red-900/20 rounded px-3 py-1.5">
                  {ep.last_push_error}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── DaaS API Keys Tab ────────────────────────────────────────────────────────

function DaaSTab() {
  const [keys, setKeys] = useState<DaaSKey[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newKeyPlain, setNewKeyPlain] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [newKey, setNewKey] = useState({
    name: '',
    client_name: '',
    rate_limit_per_hour: 1000,
    can_read_lv_voltages: true,
    can_read_feeder_loading: true,
    can_read_der_outputs: true,
    can_read_oe_limits: true,
    can_read_flex_events: true,
  })

  const load = async () => {
    try {
      const r = await api.daasKeys()
      setKeys(r.data)
    } catch {
      setKeys([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    try {
      const r = await api.createDaasKey(newKey)
      const created: DaaSKeyCreated = r.data
      setNewKeyPlain(created.api_key)
      setShowAdd(false)
      await load()
    } catch {/* ignore */}
  }

  const handleRevoke = async (id: string) => {
    if (!confirm('Revoke this API key? This action cannot be undone.')) return
    try {
      await api.revokeDaasKey(id)
      await load()
    } catch {/* ignore */}
  }

  const handleCopy = () => {
    if (newKeyPlain) {
      navigator.clipboard.writeText(newKeyPlain)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (loading) return <div className="text-gray-500 text-sm p-4">Loading keys…</div>

  const PERMISSIONS = [
    { key: 'can_read_lv_voltages', label: 'LV Voltages' },
    { key: 'can_read_feeder_loading', label: 'Feeder Loading' },
    { key: 'can_read_der_outputs', label: 'DER Outputs' },
    { key: 'can_read_oe_limits', label: 'OE Limits' },
    { key: 'can_read_flex_events', label: 'Flex Events' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">DaaS API Keys</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            L&T Data-as-a-Service — issue scoped API keys to SCADA operators who pull LV DERMS data
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-3 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Issue New Key
        </button>
      </div>

      {/* Key reveal dialog */}
      {newKeyPlain && (
        <div className="bg-green-900/20 border border-green-700/50 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-300 mb-1">API key created — copy it now</p>
              <p className="text-xs text-green-400/70 mb-3">
                This key will not be shown again. Store it securely.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-gray-950 text-green-300 text-xs font-mono px-3 py-2 rounded-lg border border-green-800/50 break-all">
                  {newKeyPlain}
                </code>
                <button
                  onClick={handleCopy}
                  className="bg-green-800/50 hover:bg-green-700/60 text-green-300 p-2 rounded-lg transition-colors flex-shrink-0"
                >
                  {copied ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
              <button
                onClick={() => setNewKeyPlain(null)}
                className="text-xs text-gray-500 hover:text-gray-300 mt-2 transition-colors"
              >
                I've saved it — dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add form */}
      {showAdd && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
          <h3 className="text-sm font-medium text-white">Issue New DaaS API Key</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Key Name</label>
              <input
                value={newKey.name}
                onChange={(e) => setNewKey({ ...newKey, name: e.target.value })}
                placeholder="e.g. SCADA Operator Read"
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Client / Organisation</label>
              <input
                value={newKey.client_name}
                onChange={(e) => setNewKey({ ...newKey, client_name: e.target.value })}
                placeholder="e.g. SSEN Operations"
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Rate Limit (req/hour)</label>
              <input
                type="number"
                min={1}
                max={10000}
                value={newKey.rate_limit_per_hour}
                onChange={(e) =>
                  setNewKey({ ...newKey, rate_limit_per_hour: parseInt(e.target.value) || 1000 })
                }
                className="w-full bg-gray-900 border border-gray-700 text-white text-sm px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-2">Data Permissions</label>
            <div className="flex flex-wrap gap-2">
              {PERMISSIONS.map(({ key, label }) => (
                <label key={key} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={(newKey as Record<string, unknown>)[key] as boolean}
                    onChange={(e) => setNewKey({ ...newKey, [key]: e.target.checked })}
                    className="accent-indigo-500"
                  />
                  <span className="text-xs text-gray-300">{label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowAdd(false)}
              className="text-sm text-gray-400 hover:text-gray-200 px-3 py-1.5 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm px-4 py-1.5 rounded-lg transition-colors"
            >
              Generate Key
            </button>
          </div>
        </div>
      )}

      {/* Keys list */}
      {keys.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <Key className="w-8 h-8 mx-auto mb-3 opacity-40" />
          <p className="text-sm">No DaaS keys issued yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {keys.map((k) => (
            <div
              key={k.id}
              className={clsx(
                'bg-gray-900 rounded-xl border p-4',
                k.is_active ? 'border-gray-800' : 'border-red-900/40 opacity-60'
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-white text-sm">{k.name}</span>
                    {!k.is_active && (
                      <span className="text-xs bg-red-900/50 text-red-400 border border-red-800 px-2 py-0.5 rounded">
                        Revoked
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">{k.client_name}</div>
                  <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                    <span className="font-mono bg-gray-800 px-2 py-0.5 rounded">{k.key_prefix}…</span>
                    <span>{k.rate_limit_per_hour.toLocaleString()} req/hr</span>
                    <span>{k.total_requests.toLocaleString()} total calls</span>
                    {k.last_used_at && (
                      <span>Last: {new Date(k.last_used_at).toLocaleString()}</span>
                    )}
                  </div>

                  {/* Permission chips */}
                  <div className="flex flex-wrap gap-1 mt-2">
                    {PERMISSIONS.map(({ key, label }) => (
                      <span
                        key={key}
                        className={clsx(
                          'px-1.5 py-0.5 rounded text-xs',
                          (k as unknown as Record<string, unknown>)[key]
                            ? 'bg-indigo-900/40 text-indigo-300'
                            : 'bg-gray-800 text-gray-600 line-through'
                        )}
                      >
                        {label}
                      </span>
                    ))}
                  </div>
                </div>

                {k.is_active && (
                  <button
                    onClick={() => handleRevoke(k.id)}
                    className="text-gray-600 hover:text-red-400 transition-colors p-1 flex-shrink-0"
                    title="Revoke key"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Snapshot Preview Tab ─────────────────────────────────────────────────────

function SnapshotTab() {
  const [snapshot, setSnapshot] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [section, setSection] = useState<'grid' | 'lv_network' | 'assets' | 'oe_limits'>('grid')

  const SECTIONS = [
    { key: 'grid', label: 'Grid', icon: Wifi },
    { key: 'lv_network', label: 'LV Network', icon: Server },
    { key: 'assets', label: 'DER Assets', icon: Database },
    { key: 'oe_limits', label: 'OE Limits', icon: AlertTriangle },
  ] as const

  const FETCHERS = {
    grid: api.scadaSnapshotGrid,
    lv_network: api.scadaSnapshotLvNetwork,
    assets: api.scadaSnapshotAssets,
    oe_limits: api.scadaSnapshotOeLimits,
  }

  const fetchSection = async (s: typeof section) => {
    setSection(s)
    setLoading(true)
    try {
      const r = await FETCHERS[s]()
      setSnapshot(r.data)
    } catch (e: unknown) {
      setSnapshot({ error: (e as { message?: string })?.message || 'Failed to fetch snapshot' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Live Data Snapshot</h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Preview the JSON payload that SCADA operators receive via DaaS API or push endpoints
        </p>
      </div>

      <div className="flex gap-2">
        {SECTIONS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => fetchSection(key)}
            className={clsx(
              'flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors border',
              section === key && snapshot !== null
                ? 'bg-indigo-600 text-white border-indigo-500'
                : 'bg-gray-800 text-gray-400 border-gray-700 hover:text-white hover:bg-gray-700'
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <RefreshCw className="w-4 h-4 animate-spin" />
          Fetching snapshot…
        </div>
      )}

      {!loading && snapshot && (
        <pre className="bg-gray-950 rounded-xl border border-gray-800 p-4 text-xs text-green-300 font-mono overflow-auto max-h-[60vh] whitespace-pre-wrap">
          {JSON.stringify(snapshot, null, 2)}
        </pre>
      )}

      {!loading && !snapshot && (
        <div className="text-center py-12 text-gray-600">
          <Database className="w-8 h-8 mx-auto mb-3 opacity-30" />
          <p className="text-sm">Select a section above to preview the snapshot payload</p>
        </div>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type Tab = 'endpoints' | 'daas' | 'snapshot'

export default function SCADAGatewayPage() {
  const [tab, setTab] = useState<Tab>('endpoints')

  const TABS: { key: Tab; label: string; icon: React.FC<{ className?: string }> }[] = [
    { key: 'endpoints', label: 'Push Endpoints', icon: Server },
    { key: 'daas', label: 'DaaS API Keys', icon: Key },
    { key: 'snapshot', label: 'Live Snapshot', icon: Database },
  ]

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-white">SCADA Gateway</h1>
        <p className="text-sm text-gray-400 mt-1">
          L&T LV DERMS Data-as-a-Service — connect LV network data to external SCADA, DMS, and MDM systems.
          Push real-time LV voltages, feeder loading, DER outputs, and operating envelope limits.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'DaaS Snapshot Endpoints', value: '5', sub: 'REST + partial snapshots' },
          { label: 'Supported Protocols', value: '5', sub: 'REST / MODBUS / DNP3 / OPC-UA / MQTT' },
          { label: 'Auth Methods', value: '2', sub: 'JWT Bearer + X-DaaS-Key' },
          { label: 'Permission Scopes', value: '5', sub: 'Per-field access control' },
        ].map(({ label, value, sub }) => (
          <div key={label} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
            <div className="text-2xl font-bold text-white">{value}</div>
            <div className="text-sm text-gray-300 mt-0.5">{label}</div>
            <div className="text-xs text-gray-500 mt-0.5">{sub}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800">
        <div className="flex gap-1">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={clsx(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                tab === key
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              )}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div>
        {tab === 'endpoints' && <EndpointsTab />}
        {tab === 'daas' && <DaaSTab />}
        {tab === 'snapshot' && <SnapshotTab />}
      </div>
    </div>
  )
}
