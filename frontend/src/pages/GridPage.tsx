import React, { useEffect, useState, useCallback } from 'react'
import {
  Search,
  Filter,
  Plus,
  ChevronRight,
  X,
  RefreshCw,
  Zap,
  Battery,
  Wind,
  Sun,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  AreaChart,
  Area,
} from 'recharts'
import { useGridStore } from '../stores/gridStore'
import { useAuthStore } from '../stores/authStore'
import { api } from '../api/client'
import GISMap from '../components/ui/GISMap'
import LVNetworkPanel from '../components/ui/LVNetworkPanel'
import CongestedDTOverlay from '../components/ui/CongestedDTOverlay'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { DERAsset, DERAssetLive, GridNode, TelemetryPoint } from '../types'
import type { LVNetworkGeoJSON, LVBusPoint } from '../components/ui/GISMap'

type Tab = 'gis' | 'assets' | 'hosting' | 'nodes'

const ASSET_TYPES = ['ALL', 'BATTERY', 'SOLAR_PV', 'WIND', 'EV_CHARGER', 'HEAT_PUMP', 'FLEXIBLE_LOAD']
const ASSET_STATUSES = ['ALL', 'ONLINE', 'OFFLINE', 'CURTAILED', 'WARNING']

const assetTypeIcon = (type: string) => {
  switch (type) {
    case 'BATTERY': return <Battery className="w-3.5 h-3.5" />
    case 'SOLAR_PV': return <Sun className="w-3.5 h-3.5" />
    case 'WIND': return <Wind className="w-3.5 h-3.5" />
    default: return <Zap className="w-3.5 h-3.5" />
  }
}

interface AssetDetailPanelProps {
  asset: DERAsset
  onClose: () => void
}

function AssetDetailPanel({ asset, onClose }: AssetDetailPanelProps) {
  const [telemetry, setTelemetry] = useState<TelemetryPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .assetTelemetry(asset.id, 24)
      .then((r) => setTelemetry(r.data || []))
      .catch(() => setTelemetry([]))
      .finally(() => setLoading(false))
  }, [asset.id])

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-gray-900 border-l border-gray-700 shadow-2xl z-40 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700 flex-shrink-0">
        <div>
          <h3 className="text-sm font-semibold text-gray-100">{asset.name}</h3>
          <p className="text-xs text-gray-500 mt-0.5">{asset.asset_ref}</p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-200">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Status & Type */}
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={asset.status} />
          <span className="badge-info">{asset.type?.replace(/_/g, ' ')}</span>
          {asset.is_digital_twin && (
            <span className="badge-gray">Digital Twin</span>
          )}
        </div>

        {/* Key fields */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Capacity', value: `${asset.capacity_kw?.toFixed(1)} kW` },
            { label: 'Current Output', value: `${asset.current_kw?.toFixed(1)} kW` },
            ...(asset.capacity_kwh ? [{ label: 'Energy Capacity', value: `${asset.capacity_kwh?.toFixed(1)} kWh` }] : []),
            ...(asset.current_soc_pct != null ? [{ label: 'State of Charge', value: `${asset.current_soc_pct?.toFixed(1)}%` }] : []),
            { label: 'Phase', value: asset.phase },
            { label: 'Comms', value: asset.comm_capability?.replace(/_/g, ' ') },
            { label: 'Feeder', value: asset.feeder_id },
            { label: 'DT', value: asset.dt_id },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-800 rounded-lg p-2.5">
              <div className="text-xs text-gray-500">{label}</div>
              <div className="text-sm text-gray-200 font-medium mt-0.5 truncate">{value}</div>
            </div>
          ))}
        </div>

        {/* DOE values */}
        {(asset.doe_export_max_kw != null || asset.doe_import_max_kw != null) && (
          <div className="bg-indigo-900/20 border border-indigo-800/30 rounded-lg p-3">
            <div className="text-xs font-medium text-indigo-300 mb-2">Operating Envelope</div>
            <div className="flex gap-3">
              <div>
                <div className="text-xs text-gray-500">Max Export</div>
                <div className="text-sm text-green-400 font-medium">
                  {asset.doe_export_max_kw?.toFixed(1) ?? '—'} kW
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Max Import</div>
                <div className="text-sm text-blue-400 font-medium">
                  {asset.doe_import_max_kw?.toFixed(1) ?? '—'} kW
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Telemetry chart */}
        <div>
          <div className="text-xs font-medium text-gray-400 mb-2">24h Telemetry</div>
          {loading ? (
            <LoadingSpinner size="sm" className="py-8" />
          ) : telemetry.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={telemetry} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="telGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(v) => new Date(v).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
                <Tooltip
                  formatter={(v: number) => [`${v.toFixed(1)} kW`, 'Output']}
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                />
                <Area type="monotone" dataKey="kw" stroke="#6366f1" fill="url(#telGrad)" strokeWidth={1.5} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-gray-500 text-xs py-8">No telemetry available</div>
          )}
        </div>

        {/* Last telemetry time */}
        {asset.last_telemetry_at && (
          <div className="text-xs text-gray-500">
            Last telemetry: {new Date(asset.last_telemetry_at).toLocaleString('en-GB')}
          </div>
        )}
      </div>
    </div>
  )
}

interface RegisterAssetForm {
  name: string
  type: string
  phase: string
  capacity_kw: string
  feeder_id: string
  dt_id: string
  comm_capability: string
  counterparty_id: string
}

export default function GridPage() {
  const { gridState } = useGridStore()
  const { currentDeployment } = useAuthStore()
  const [activeTab, setActiveTab] = useState<Tab>('gis')
  const [assets, setAssets] = useState<DERAsset[]>([])
  const [nodes, setNodes] = useState<GridNode[]>([])
  const [hostingData, setHostingData] = useState<{ cmz_id: string; available_kw: number; used_kw: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedAsset, setSelectedAsset] = useState<DERAsset | null>(null)
  const [showCongestion, setShowCongestion] = useState(false)
  const [selectedDT, setSelectedDT] = useState<{ nodeId: string; name: string } | null>(null)
  const [lvNetworkData, setLvNetworkData] = useState<LVNetworkGeoJSON | null>(null)
  const [lvBuses, setLvBuses] = useState<LVBusPoint[]>([])
  const [showRegisterModal, setShowRegisterModal] = useState(false)
  const [registerForm, setRegisterForm] = useState<RegisterAssetForm>({
    name: '', type: 'BATTERY', phase: 'THREE', capacity_kw: '',
    feeder_id: '', dt_id: '', comm_capability: 'SMART_METER', counterparty_id: '',
  })
  const [registering, setRegistering] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [assetsRes, hcRes] = await Promise.all([
        api.assets(),
        api.hostingCapacity().catch(() => ({ data: [] })),
      ])
      setAssets(assetsRes.data || [])
      setHostingData(hcRes.data || [])
      if (gridState?.nodes) setNodes(gridState.nodes)
    } catch {
      // use grid store data
      if (gridState?.assets) setAssets(gridState.assets as unknown as DERAsset[])
      if (gridState?.nodes) setNodes(gridState.nodes)
    } finally {
      setLoading(false)
    }
  }, [currentDeployment, gridState])

  const loadLVNetworkData = useCallback(async () => {
    try {
      const res = await api.lvNetworkList()
      // Backend returns a list of LV network summaries; convert to a combined GeoJSON if features are present
      const data = res.data
      if (data && data.type === 'FeatureCollection') {
        setLvNetworkData(data as LVNetworkGeoJSON)
        // Extract bus points embedded as Point features
        const buses: LVBusPoint[] = []
        for (const feat of (data as LVNetworkGeoJSON).features) {
          const f = feat as any
          if (f.geometry?.type === 'Point' && f.properties?.bus_ref) {
            const [lng, lat] = f.geometry.coordinates as [number, number]
            buses.push({
              id: f.properties.id ?? f.properties.bus_ref,
              bus_ref: f.properties.bus_ref,
              lat,
              lng,
              v_pu: f.properties.v_pu ?? 1.0,
              v_v: f.properties.v_v ?? 230,
              voltage_status: f.properties.voltage_status ?? 'NORMAL',
              p_kw: f.properties.p_kw ?? 0,
              q_kvar: f.properties.q_kvar ?? 0,
              asset_id: f.properties.asset_id,
              asset_type: f.properties.asset_type,
              asset_name: f.properties.asset_name,
            })
          }
        }
        if (buses.length > 0) setLvBuses(buses)
      } else if (Array.isArray(data)) {
        // Merge multiple FeatureCollections into one
        const allFeatures: LVNetworkGeoJSON['features'] = []
        for (const item of data) {
          if (item?.geojson?.features) {
            allFeatures.push(...item.geojson.features)
          }
        }
        if (allFeatures.length > 0) {
          setLvNetworkData({ type: 'FeatureCollection', features: allFeatures })
        }

        // Extract LV bus points from all network items
        const buses: LVBusPoint[] = []
        for (const item of data) {
          if (Array.isArray(item?.buses)) {
            for (const b of item.buses) {
              if (b.lat != null && b.lng != null) {
                buses.push({
                  id: b.id ?? b.bus_ref,
                  bus_ref: b.bus_ref ?? b.id,
                  lat: b.lat,
                  lng: b.lng,
                  v_pu: b.v_pu ?? 1.0,
                  v_v: b.v_v ?? 230,
                  voltage_status: b.voltage_status ?? 'NORMAL',
                  p_kw: b.p_kw ?? 0,
                  q_kvar: b.q_kvar ?? 0,
                  asset_id: b.asset_id,
                  asset_type: b.asset_type,
                  asset_name: b.asset_name,
                })
              }
            }
          }
        }
        if (buses.length > 0) setLvBuses(buses)
      }
    } catch {
      // LV network data is optional — fail silently
    }
  }, [])

  const handleSelectDT = useCallback(
    (dtNodeId: string) => {
      const dtNode = nodes.find((n) => n.node_id === dtNodeId)
      setSelectedDT({ nodeId: dtNodeId, name: dtNode?.name ?? dtNodeId })
    },
    [nodes],
  )

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    loadLVNetworkData()
  }, [loadLVNetworkData])

  // Sync nodes from grid store
  useEffect(() => {
    if (gridState?.nodes?.length) setNodes(gridState.nodes)
  }, [gridState?.nodes])

  const filteredAssets = assets.filter((a) => {
    const matchSearch =
      !search ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.asset_ref.toLowerCase().includes(search.toLowerCase())
    const matchType = typeFilter === 'ALL' || a.type === typeFilter
    const matchStatus = statusFilter === 'ALL' || a.status === statusFilter
    return matchSearch && matchType && matchStatus
  })

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setRegistering(true)
    try {
      await api.createAsset({
        ...registerForm,
        capacity_kw: parseFloat(registerForm.capacity_kw),
      })
      setShowRegisterModal(false)
      loadData()
    } catch {
      alert('Failed to register asset. Please try again.')
    } finally {
      setRegistering(false)
    }
  }

  const liveAssets: DERAssetLive[] = gridState?.assets || (assets as unknown as DERAssetLive[])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Grid & Assets</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {assets.length} registered assets · {nodes.length} grid nodes
          </p>
        </div>
        <button onClick={() => setShowRegisterModal(true)} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Register Asset
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {(['gis', 'assets', 'hosting', 'nodes'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={activeTab === tab ? 'tab-active' : 'tab-inactive'}
          >
            {tab === 'gis' ? 'GIS View' : tab === 'assets' ? 'Asset Fleet' : tab === 'hosting' ? 'Hosting Capacity' : 'Grid Nodes'}
          </button>
        ))}
      </div>

      {loading && !assets.length ? (
        <LoadingSpinner fullPage label="Loading grid data..." />
      ) : (
        <>
          {/* GIS View */}
          {activeTab === 'gis' && (
            <div className="card p-0 overflow-hidden">
              <div className="flex items-center justify-between p-4 border-b border-gray-700">
                <h2 className="text-sm font-semibold text-gray-200">Network Topology Map</h2>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    <span>{liveAssets.filter((a) => a.status === 'ONLINE').length} online</span>
                    <span>·</span>
                    <span className="text-amber-400">{liveAssets.filter((a) => a.status === 'CURTAILED').length} curtailed</span>
                    <span>·</span>
                    <span className="text-red-400">{liveAssets.filter((a) => a.status === 'OFFLINE').length} offline</span>
                  </div>
                  <button
                    onClick={() => setShowCongestion((v) => !v)}
                    className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                      showCongestion
                        ? 'bg-amber-600/20 border-amber-600/50 text-amber-400'
                        : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    Congestion Analysis
                  </button>
                </div>
              </div>
              <CongestedDTOverlay visible={showCongestion} onSelectDT={handleSelectDT} />
              <GISMap
                nodes={nodes}
                assets={liveAssets}
                deployment={currentDeployment}
                height={520}
                onSelectAsset={(asset) => {
                  // Find the full DERAsset to open detail panel
                  const full = assets.find((a) => a.id === asset.id)
                  if (full) setSelectedAsset(full)
                }}
                onSelectDT={handleSelectDT}
                lvNetworkData={lvNetworkData}
                lvBuses={lvBuses}
                flexEnrolledBusIds={[]}
              />
            </div>
          )}

          {/* Asset Fleet */}
          {activeTab === 'assets' && (
            <div className="card p-0">
              {/* Filters */}
              <div className="p-4 border-b border-gray-700 flex items-center gap-3 flex-wrap">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search assets..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="input pl-9 w-full"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Filter className="w-4 h-4 text-gray-400" />
                  <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                    className="select text-xs"
                  >
                    {ASSET_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t === 'ALL' ? 'All Types' : t.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="select text-xs"
                  >
                    {ASSET_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s === 'ALL' ? 'All Statuses' : s}
                      </option>
                    ))}
                  </select>
                </div>
                <button onClick={loadData} className="btn-secondary flex items-center gap-1.5 text-xs px-3 py-2">
                  <RefreshCw className="w-3.5 h-3.5" />
                  Refresh
                </button>
              </div>

              {/* Table */}
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="table-header text-left">Asset Ref</th>
                      <th className="table-header text-left">Name</th>
                      <th className="table-header text-left">Type</th>
                      <th className="table-header text-left">Status</th>
                      <th className="table-header text-left">Feeder</th>
                      <th className="table-header text-right">Current kW</th>
                      <th className="table-header text-right">Capacity kW</th>
                      <th className="table-header text-right">SoC %</th>
                      <th className="table-header text-left">Last Telemetry</th>
                      <th className="table-header" />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAssets.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="text-center py-12 text-gray-500">
                          No assets match filters
                        </td>
                      </tr>
                    ) : (
                      filteredAssets.map((asset) => (
                        <tr
                          key={asset.id}
                          className="table-row"
                          onClick={() => setSelectedAsset(asset)}
                        >
                          <td className="table-cell font-mono text-xs text-indigo-400">
                            {asset.asset_ref}
                          </td>
                          <td className="table-cell">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400">{assetTypeIcon(asset.type)}</span>
                              <span className="text-gray-200 font-medium">{asset.name}</span>
                            </div>
                          </td>
                          <td className="table-cell">
                            <span className="text-xs text-gray-400">
                              {asset.type?.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="table-cell">
                            <StatusBadge status={asset.status} />
                          </td>
                          <td className="table-cell text-xs text-gray-400">{asset.feeder_id}</td>
                          <td className="table-cell text-right font-mono text-sm">
                            <span className={asset.current_kw > 0 ? 'text-green-400' : 'text-gray-500'}>
                              {asset.current_kw?.toFixed(1)}
                            </span>
                          </td>
                          <td className="table-cell text-right text-gray-400 font-mono text-sm">
                            {asset.capacity_kw?.toFixed(0)}
                          </td>
                          <td className="table-cell text-right">
                            {asset.current_soc_pct != null ? (
                              <div className="flex items-center justify-end gap-1.5">
                                <div className="w-12 h-1.5 bg-gray-600 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-indigo-500 rounded-full"
                                    style={{ width: `${asset.current_soc_pct}%` }}
                                  />
                                </div>
                                <span className="text-xs text-gray-400">
                                  {asset.current_soc_pct.toFixed(0)}%
                                </span>
                              </div>
                            ) : (
                              <span className="text-gray-600">—</span>
                            )}
                          </td>
                          <td className="table-cell text-xs text-gray-500">
                            {asset.last_telemetry_at
                              ? new Date(asset.last_telemetry_at).toLocaleTimeString('en-GB')
                              : '—'}
                          </td>
                          <td className="table-cell">
                            <ChevronRight className="w-4 h-4 text-gray-500" />
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Footer */}
              <div className="p-3 border-t border-gray-700 text-xs text-gray-500">
                Showing {filteredAssets.length} of {assets.length} assets
              </div>
            </div>
          )}

          {/* Hosting Capacity */}
          {activeTab === 'hosting' && (
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-200 mb-4">
                Hosting Capacity by CMZ
              </h2>
              {hostingData.length === 0 ? (
                <div className="text-center text-gray-500 py-12">
                  No hosting capacity data available
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={360}>
                  <BarChart data={hostingData} margin={{ top: 4, right: 16, left: 0, bottom: 32 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="cmz_id"
                      tick={{ fill: '#9ca3af', fontSize: 11 }}
                      angle={-30}
                      textAnchor="end"
                    />
                    <YAxis
                      tick={{ fill: '#9ca3af', fontSize: 11 }}
                      tickFormatter={(v) => `${v} kW`}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                      formatter={(v: number, name: string) => [
                        `${v?.toFixed(0)} kW`,
                        name === 'used_kw' ? 'Used Capacity' : 'Available Capacity',
                      ]}
                    />
                    <Legend formatter={(v) => v === 'used_kw' ? 'Used' : 'Available'} />
                    <Bar dataKey="available_kw" name="available_kw" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="used_kw" name="used_kw" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {/* Grid Nodes */}
          {activeTab === 'nodes' && (
            <div className="card p-0">
              <div className="p-4 border-b border-gray-700">
                <h2 className="text-sm font-semibold text-gray-200">Grid Nodes</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="table-header text-left">Node ID</th>
                      <th className="table-header text-left">Name</th>
                      <th className="table-header text-left">Type</th>
                      <th className="table-header text-left">CMZ</th>
                      <th className="table-header text-right">Loading %</th>
                      <th className="table-header text-right">V L1</th>
                      <th className="table-header text-right">V L2</th>
                      <th className="table-header text-right">V L3</th>
                      <th className="table-header text-right">HC kW</th>
                    </tr>
                  </thead>
                  <tbody>
                    {nodes.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="text-center py-12 text-gray-500">
                          No node data available
                        </td>
                      </tr>
                    ) : (
                      nodes.map((node) => (
                        <tr key={node.node_id} className="table-row">
                          <td className="table-cell font-mono text-xs text-indigo-400">
                            {node.node_id}
                          </td>
                          <td className="table-cell font-medium text-gray-200">{node.name}</td>
                          <td className="table-cell">
                            <span className="badge-info text-xs">
                              {node.node_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td className="table-cell text-gray-400">{node.cmz_id}</td>
                          <td className="table-cell text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 h-1.5 bg-gray-600 rounded-full overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    node.current_loading_pct > 90
                                      ? 'bg-red-500'
                                      : node.current_loading_pct > 75
                                      ? 'bg-amber-500'
                                      : 'bg-green-500'
                                  }`}
                                  style={{ width: `${Math.min(node.current_loading_pct, 100)}%` }}
                                />
                              </div>
                              <span className={`text-sm font-mono ${
                                node.current_loading_pct > 90 ? 'text-red-400' :
                                node.current_loading_pct > 75 ? 'text-amber-400' : 'text-green-400'
                              }`}>
                                {node.current_loading_pct?.toFixed(1)}%
                              </span>
                            </div>
                          </td>
                          <td className="table-cell text-right font-mono text-xs text-gray-400">
                            {node.voltage_l1_v?.toFixed(1) ?? '—'}
                          </td>
                          <td className="table-cell text-right font-mono text-xs text-gray-400">
                            {node.voltage_l2_v?.toFixed(1) ?? '—'}
                          </td>
                          <td className="table-cell text-right font-mono text-xs text-gray-400">
                            {node.voltage_l3_v?.toFixed(1) ?? '—'}
                          </td>
                          <td className="table-cell text-right font-mono text-sm text-indigo-400">
                            {node.hosting_capacity_kw?.toFixed(0)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Asset Detail Panel */}
      {selectedAsset && (
        <AssetDetailPanel asset={selectedAsset} onClose={() => setSelectedAsset(null)} />
      )}

      {/* LV Network Panel */}
      {selectedDT && (
        <LVNetworkPanel
          dtNodeId={selectedDT.nodeId}
          dtName={selectedDT.name}
          deployment={currentDeployment}
          onClose={() => setSelectedDT(null)}
        />
      )}

      {/* Register Asset Modal */}
      <Modal
        isOpen={showRegisterModal}
        onClose={() => setShowRegisterModal(false)}
        title="Register New DER Asset"
        size="md"
        footer={
          <>
            <button onClick={() => setShowRegisterModal(false)} className="btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleRegister}
              disabled={registering}
              className="btn-primary flex items-center gap-2"
            >
              {registering ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Registering...
                </>
              ) : (
                'Register Asset'
              )}
            </button>
          </>
        }
      >
        <form onSubmit={handleRegister} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-400 mb-1">Asset Name *</label>
              <input
                className="input w-full"
                value={registerForm.name}
                onChange={(e) => setRegisterForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Lerwick BESS Unit 1"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Asset Type *</label>
              <select
                className="select w-full"
                value={registerForm.type}
                onChange={(e) => setRegisterForm((p) => ({ ...p, type: e.target.value }))}
              >
                {ASSET_TYPES.filter((t) => t !== 'ALL').map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Phase</label>
              <select
                className="select w-full"
                value={registerForm.phase}
                onChange={(e) => setRegisterForm((p) => ({ ...p, phase: e.target.value }))}
              >
                <option value="SINGLE">Single Phase</option>
                <option value="THREE">Three Phase</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Capacity (kW) *</label>
              <input
                className="input w-full"
                type="number"
                step="0.1"
                value={registerForm.capacity_kw}
                onChange={(e) => setRegisterForm((p) => ({ ...p, capacity_kw: e.target.value }))}
                placeholder="250"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Comms Capability</label>
              <select
                className="select w-full"
                value={registerForm.comm_capability}
                onChange={(e) => setRegisterForm((p) => ({ ...p, comm_capability: e.target.value }))}
              >
                <option value="SMART_METER">Smart Meter</option>
                <option value="DIRECT_API">Direct API</option>
                <option value="MODBUS">Modbus</option>
                <option value="DNAP3">DNAP3</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Feeder ID</label>
              <input
                className="input w-full"
                value={registerForm.feeder_id}
                onChange={(e) => setRegisterForm((p) => ({ ...p, feeder_id: e.target.value }))}
                placeholder="FEEDER-001"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">DT ID</label>
              <input
                className="input w-full"
                value={registerForm.dt_id}
                onChange={(e) => setRegisterForm((p) => ({ ...p, dt_id: e.target.value }))}
                placeholder="DT-001"
              />
            </div>
          </div>
        </form>
      </Modal>
    </div>
  )
}
