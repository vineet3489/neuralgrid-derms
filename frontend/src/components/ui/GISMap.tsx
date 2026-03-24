import React, { useState, useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Marker, Popup, GeoJSON, LayersControl, useMap, useMapEvents, Polyline } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { GridNode, DERAssetLive } from '../../types'

// Fix Leaflet default marker icon broken by webpack/vite bundling
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LVNetworkGeoJSON {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    geometry: {
      type: 'LineString'
      coordinates: [number, number][]
    }
    properties: {
      voltage_violation?: boolean
      feeder_id?: string
      [key: string]: unknown
    }
  }>
}

export interface LVBusPoint {
  id: string
  bus_ref: string
  lat: number
  lng: number
  v_pu: number
  v_v: number
  voltage_status: string
  p_kw: number
  q_kvar: number
  asset_id?: string
  asset_type?: string   // PV / BESS / V1G / V2G / HEAT_PUMP
  asset_name?: string
}

export interface GISMapProps {
  nodes: GridNode[]
  assets: DERAssetLive[]
  deployment: string
  onSelectAsset?: (asset: DERAssetLive) => void
  onSelectDT?: (dtNodeId: string) => void
  height?: number
  lvNetworkData?: LVNetworkGeoJSON | null
  lvBuses?: LVBusPoint[]
  flexEnrolledBusIds?: string[]
}

// ─── Constants ────────────────────────────────────────────────────────────────

const TILE_PROVIDERS = {
  osm: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    name: 'OpenStreetMap',
  },
  esri: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    name: 'Esri Satellite',
  },
  carto: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    name: 'CartoDB Dark',
  },
} as const

type TileProvider = keyof typeof TILE_PROVIDERS

const DEPLOYMENT_BOUNDS: Record<string, { center: [number, number]; zoom: number }> = {
  ssen: { center: [59.5, -2.5], zoom: 9 },
  puvvnl: { center: [25.32, 83.01], zoom: 13 },
}

const DEFAULT_CENTER: [number, number] = [51.5, -0.1]
const DEFAULT_ZOOM = 11

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getAssetColor(status: string): string {
  switch (status?.toUpperCase()) {
    case 'ONLINE': return '#22c55e'
    case 'OFFLINE': return '#ef4444'
    case 'CURTAILED': return '#f59e0b'
    case 'WARNING': return '#f59e0b'
    default: return '#6b7280'
  }
}

function getNodeTypeLabel(nodeType: string): string {
  switch (nodeType) {
    case 'SUBSTATION': return 'Substation'
    case 'DISTRIBUTION_TRANSFORMER': return 'DT'
    case 'FEEDER': return 'Feeder'
    default: return nodeType.replace(/_/g, ' ')
  }
}

function getVoltageColor(v_pu: number): string {
  if (v_pu > 1.05 || v_pu < 0.94) return '#ef4444'
  if (v_pu > 1.03 || v_pu < 0.97) return '#f59e0b'
  return '#22c55e'
}

// DT marker — indigo rotated square (diamond)
function makeDTIcon() {
  return L.divIcon({
    className: '',
    html: `<div style="width:12px;height:12px;background:#6366f1;border:2px solid white;border-radius:2px;transform:rotate(45deg);box-shadow:0 0 4px rgba(99,102,241,0.8)"></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
  })
}

// Substation marker — larger indigo square
function makeSubstationIcon() {
  return L.divIcon({
    className: '',
    html: `<div style="width:16px;height:16px;background:#818cf8;border:2px solid white;border-radius:3px;box-shadow:0 0 6px rgba(129,140,248,0.8)"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  })
}

// Feeder node marker — small slate square
function makeFeederIcon() {
  return L.divIcon({
    className: '',
    html: `<div style="width:8px;height:8px;background:#94a3b8;border:1.5px solid white;border-radius:1px"></div>`,
    iconSize: [8, 8],
    iconAnchor: [4, 4],
  })
}

function getNodeIcon(nodeType: string) {
  switch (nodeType) {
    case 'SUBSTATION': return makeSubstationIcon()
    case 'DISTRIBUTION_TRANSFORMER': return makeDTIcon()
    default: return makeFeederIcon()
  }
}

// Home marker icon — small house shape using CSS
function makeHomeIcon(hasFlexEnrollment: boolean, hasDER: boolean) {
  const color = hasDER ? '#22c55e' : '#64748b'
  const ring = hasFlexEnrollment ? `box-shadow: 0 0 0 3px rgba(99,102,241,0.5);` : ''
  return L.divIcon({
    className: '',
    html: `<div style="width:10px;height:10px;background:${color};border:1.5px solid white;border-radius:2px;${ring}"></div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  })
}

function lvLineStyle(feature?: { properties?: { voltage_violation?: boolean } }) {
  const isViolation = feature?.properties?.voltage_violation === true
  return {
    color: isViolation ? '#ef4444' : '#3b82f6',
    weight: isViolation ? 2.5 : 1.5,
    opacity: 0.8,
    dashArray: isViolation ? '6 3' : undefined,
  }
}

// ─── Zoom Tracker ─────────────────────────────────────────────────────────────

function ZoomTracker({ onZoomChange }: { onZoomChange: (z: number) => void }) {
  const map = useMapEvents({
    zoom: () => onZoomChange(map.getZoom()),
    move: () => onZoomChange(map.getZoom()),
  })
  return null
}

// ─── Tile Provider Selector ───────────────────────────────────────────────────

interface TileProviderSelectorProps {
  value: TileProvider
  onChange: (p: TileProvider) => void
}

function TileProviderSelector({ value, onChange }: TileProviderSelectorProps) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 10,
        right: 10,
        zIndex: 1000,
        background: 'rgba(17,24,39,0.92)',
        border: '1px solid rgba(75,85,99,0.8)',
        borderRadius: 8,
        padding: '6px 8px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        minWidth: 136,
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
      }}
    >
      <span style={{ fontSize: 10, color: '#9ca3af', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>
        Map Layer
      </span>
      {(Object.keys(TILE_PROVIDERS) as TileProvider[]).map((key) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          style={{
            background: value === key ? '#4f46e5' : 'transparent',
            color: value === key ? '#fff' : '#9ca3af',
            border: 'none',
            borderRadius: 5,
            padding: '3px 8px',
            fontSize: 11,
            fontWeight: value === key ? 600 : 400,
            cursor: 'pointer',
            textAlign: 'left',
            transition: 'all 0.15s',
          }}
        >
          {TILE_PROVIDERS[key].name}
        </button>
      ))}
    </div>
  )
}

// ─── Map Stats Legend ─────────────────────────────────────────────────────────

function MapLegend({ assets, zoom }: { assets: DERAssetLive[]; zoom: number }) {
  const online = assets.filter((a) => a.status === 'ONLINE').length
  const offline = assets.filter((a) => a.status === 'OFFLINE').length
  const curtailed = assets.filter((a) => a.status === 'CURTAILED').length

  const items = [
    { color: '#22c55e', label: `Online (${online})` },
    { color: '#f59e0b', label: `Curtailed (${curtailed})` },
    { color: '#ef4444', label: `Offline (${offline})` },
    { color: '#6366f1', label: 'DT Node', shape: 'square' as const },
    { color: '#3b82f6', label: 'LV Normal', dashed: false, line: true },
    { color: '#ef4444', label: 'LV Violation', dashed: true, line: true },
    ...(zoom >= 13 ? [{ color: '#6366f1', label: 'Flex Link', dashed: true, line: true }] : []),
    ...(zoom >= 15 ? [
      { color: '#22c55e', label: 'Home (DER)', shape: 'square' as const },
      { color: '#64748b', label: 'Home (no DER)', shape: 'square' as const },
    ] : []),
  ]

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 24,
        left: 10,
        zIndex: 1000,
        background: 'rgba(17,24,39,0.92)',
        border: '1px solid rgba(75,85,99,0.8)',
        borderRadius: 8,
        padding: '8px 10px',
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
      }}
    >
      {items.map(({ color, label, shape, line, dashed }) => (
        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {line ? (
            <svg width="14" height="8" style={{ flexShrink: 0 }}>
              <line
                x1="0" y1="4" x2="14" y2="4"
                stroke={color}
                strokeWidth={dashed ? 2 : 1.5}
                strokeDasharray={dashed ? '4 2' : undefined}
              />
            </svg>
          ) : (
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: shape === 'square' ? 1 : '50%',
                backgroundColor: color,
                flexShrink: 0,
                transform: shape === 'square' ? 'rotate(45deg)' : undefined,
              }}
            />
          )}
          <span style={{ fontSize: 10, color: '#9ca3af', whiteSpace: 'nowrap' }}>{label}</span>
        </div>
      ))}
      {zoom >= 12 && (
        <div style={{ marginTop: 3, paddingTop: 3, borderTop: '1px solid #374151' }}>
          <span style={{ fontSize: 9, color: '#6b7280' }}>Zoom {zoom} — {zoom >= 15 ? 'Home detail' : zoom >= 12 ? 'DT detail' : 'Grid overview'}</span>
        </div>
      )}
    </div>
  )
}

// ─── Node Marker ──────────────────────────────────────────────────────────────

interface NodeMarkerProps {
  node: GridNode
  onSelectDT?: (nodeId: string) => void
  zoom: number
}

function NodeMarker({ node, onSelectDT, zoom }: NodeMarkerProps) {
  if (node.lat == null || node.lng == null) return null

  // At low zoom, hide DTs (show only substations and feeder nodes)
  if (zoom < 12 && node.node_type === 'DISTRIBUTION_TRANSFORMER') return null

  const icon = getNodeIcon(node.node_type)
  const loadPct = node.current_loading_pct ?? 0
  const isDT = node.node_type === 'DISTRIBUTION_TRANSFORMER'

  return (
    <Marker position={[node.lat, node.lng]} icon={icon}>
      <Popup>
        <div style={{ minWidth: 180 }}>
          <div style={{ fontWeight: 700, color: '#e5e7eb', marginBottom: 4, fontSize: 13 }}>
            {node.name}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 6 }}>
            {getNodeTypeLabel(node.node_type)}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
            Loading:{' '}
            <span style={{ color: loadPct > 90 ? '#ef4444' : loadPct > 75 ? '#f59e0b' : '#22c55e', fontWeight: 600 }}>
              {loadPct.toFixed(1)}%
            </span>
          </div>
          {(node.voltage_l1_v != null) && (
            <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
              V L1: <span style={{ color: '#e5e7eb' }}>{node.voltage_l1_v.toFixed(1)} V</span>
            </div>
          )}
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: isDT ? 8 : 0 }}>
            HC: <span style={{ color: '#818cf8' }}>{node.hosting_capacity_kw?.toFixed(0)} kW</span>
          </div>
          {isDT && onSelectDT && (
            <button
              onClick={() => onSelectDT(node.node_id)}
              style={{
                width: '100%',
                padding: '5px 10px',
                background: '#4f46e5',
                color: '#fff',
                border: 'none',
                borderRadius: 5,
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
                marginTop: 4,
              }}
            >
              View LV Network
            </button>
          )}
        </div>
      </Popup>
    </Marker>
  )
}

// ─── Asset Marker ─────────────────────────────────────────────────────────────

interface AssetMarkerProps {
  asset: DERAssetLive
  onSelectAsset?: (asset: DERAssetLive) => void
}

function AssetMarker({ asset, onSelectAsset }: AssetMarkerProps) {
  if (asset.lat == null || asset.lng == null) return null
  const color = getAssetColor(asset.status)

  return (
    <CircleMarker
      center={[asset.lat, asset.lng]}
      radius={7}
      pathOptions={{
        fillColor: color,
        fillOpacity: 0.35,
        color: color,
        weight: 1.5,
      }}
      eventHandlers={{
        click: () => onSelectAsset?.(asset),
      }}
    >
      <Popup>
        <div style={{ minWidth: 170 }}>
          <div style={{ fontWeight: 700, color: '#e5e7eb', marginBottom: 3, fontSize: 13 }}>
            {asset.name}
          </div>
          <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 6, fontFamily: 'monospace' }}>
            {asset.asset_ref}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: color }} />
            <span style={{ fontSize: 11, color: '#e5e7eb', fontWeight: 600 }}>{asset.status}</span>
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
            Type: {asset.type?.replace(/_/g, ' ')}
          </div>
          <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
            Output: <span style={{ color: '#e5e7eb' }}>{asset.current_kw?.toFixed(1)}</span> / {asset.capacity_kw?.toFixed(0)} kW
          </div>
          {asset.current_soc_pct != null && (
            <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
              SoC: <span style={{ color: '#818cf8' }}>{asset.current_soc_pct.toFixed(1)}%</span>
            </div>
          )}
          {(asset.doe_export_max_kw != null || asset.doe_import_max_kw != null) && (
            <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid #374151' }}>
              {asset.doe_export_max_kw != null && (
                <div style={{ fontSize: 10, color: '#9ca3af' }}>
                  Max Export: <span style={{ color: '#22c55e' }}>{asset.doe_export_max_kw.toFixed(1)} kW</span>
                </div>
              )}
              {asset.doe_import_max_kw != null && (
                <div style={{ fontSize: 10, color: '#9ca3af' }}>
                  Max Import: <span style={{ color: '#60a5fa' }}>{asset.doe_import_max_kw.toFixed(1)} kW</span>
                </div>
              )}
            </div>
          )}
          {onSelectAsset && (
            <button
              onClick={() => onSelectAsset(asset)}
              style={{
                width: '100%',
                padding: '4px 8px',
                background: '#374151',
                color: '#e5e7eb',
                border: 'none',
                borderRadius: 4,
                fontSize: 10,
                cursor: 'pointer',
                marginTop: 8,
              }}
            >
              View Asset Detail
            </button>
          )}
        </div>
      </Popup>
    </CircleMarker>
  )
}

// ─── Home Marker (LV Bus, zoom ≥ 15) ─────────────────────────────────────────

interface HomeMarkerProps {
  bus: LVBusPoint
  isFlexEnrolled: boolean
}

function HomeMarker({ bus, isFlexEnrolled }: HomeMarkerProps) {
  const hasDER = !!bus.asset_type
  const icon = makeHomeIcon(isFlexEnrolled, hasDER)
  const vColor = getVoltageColor(bus.v_pu)
  const netLoad = bus.p_kw
  const netLoadStr = netLoad >= 0 ? `+${netLoad.toFixed(1)}` : netLoad.toFixed(1)

  return (
    <Marker position={[bus.lat, bus.lng]} icon={icon}>
      <Popup>
        <div style={{ minWidth: 190, fontFamily: 'system-ui, sans-serif' }}>
          <div style={{ fontWeight: 700, color: '#e5e7eb', marginBottom: 4, fontSize: 12, fontFamily: 'monospace' }}>
            {bus.bus_ref}
          </div>
          <div style={{ fontSize: 10, color: '#9ca3af', marginBottom: 6 }}>
            Type: CUSTOMER · {bus.p_kw !== undefined ? '3-phase' : '1-phase'}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 8px', marginBottom: 6 }}>
            <div style={{ fontSize: 10, color: '#9ca3af' }}>Voltage</div>
            <div style={{ fontSize: 10 }}>
              <span style={{ color: vColor, fontWeight: 600 }}>{bus.v_v?.toFixed(1)} V</span>
              <span style={{ color: '#6b7280' }}> ({bus.v_pu?.toFixed(3)} pu)</span>
            </div>

            <div style={{ fontSize: 10, color: '#9ca3af' }}>Net Load</div>
            <div style={{ fontSize: 10, color: netLoad > 0 ? '#f59e0b' : '#60a5fa', fontWeight: 600 }}>
              {netLoadStr} kW
            </div>

            {bus.q_kvar !== undefined && (
              <>
                <div style={{ fontSize: 10, color: '#9ca3af' }}>Reactive</div>
                <div style={{ fontSize: 10, color: '#9ca3af' }}>{bus.q_kvar?.toFixed(1)} kVAR</div>
              </>
            )}
          </div>

          {bus.asset_type && (
            <div style={{ background: '#1a2435', borderRadius: 4, padding: '4px 6px', marginBottom: 5 }}>
              <div style={{ fontSize: 10, color: '#818cf8', fontWeight: 600, marginBottom: 2 }}>DER Asset</div>
              <div style={{ fontSize: 10, color: '#e5e7eb' }}>
                {bus.asset_name || bus.asset_type} · <span style={{ color: '#22c55e' }}>ONLINE</span>
              </div>
            </div>
          )}

          {isFlexEnrolled && (
            <div style={{ background: '#1e1b35', borderRadius: 4, padding: '4px 6px', marginBottom: 5, border: '1px solid rgba(99,102,241,0.3)' }}>
              <div style={{ fontSize: 10, color: '#a5b4fc', fontWeight: 600, marginBottom: 1 }}>Flex Enrolled</div>
              <div style={{ fontSize: 10, color: '#9ca3af' }}>Active DR programme</div>
            </div>
          )}

          <div style={{ fontSize: 9, color: '#4b5563', borderTop: '1px solid #1f2937', paddingTop: 4 }}>
            Bus ID: {bus.id}
          </div>
        </div>
      </Popup>
    </Marker>
  )
}

// ─── Fit-bounds controller (inner component uses useMap) ─────────────────────

function FitBoundsController({ assets, nodes }: { assets: DERAssetLive[]; nodes: GridNode[] }) {
  const map = useMap()
  useEffect(() => {
    const coordPairs: [number, number][] = [
      ...assets.filter((a) => a.lat != null && a.lng != null).map((a) => [a.lat!, a.lng!] as [number, number]),
      ...nodes.filter((n) => n.lat != null && n.lng != null).map((n) => [n.lat!, n.lng!] as [number, number]),
    ]
    if (coordPairs.length >= 2) {
      try {
        map.fitBounds(L.latLngBounds(coordPairs), { padding: [30, 30], maxZoom: 14 })
      } catch {
        // ignore bounds errors
      }
    }
  }, [map, assets, nodes])
  return null
}

// ─── Flex Interconnection Lines (zoom ≥ 13) ───────────────────────────────────

interface FlexLinesProps {
  nodes: GridNode[]
  lvBuses: LVBusPoint[]
  flexEnrolledBusIds: string[]
}

function FlexLines({ nodes, lvBuses, flexEnrolledBusIds }: FlexLinesProps) {
  const enrolledBuses = lvBuses.filter((b) => flexEnrolledBusIds.includes(b.id))
  if (enrolledBuses.length === 0) return null

  // Find DT nodes that have valid coordinates
  const dtNodes = nodes.filter(
    (n) => n.node_type === 'DISTRIBUTION_TRANSFORMER' && n.lat != null && n.lng != null
  )
  if (dtNodes.length === 0) return null

  // For each enrolled bus, draw a line to the nearest DT
  return (
    <>
      {enrolledBuses.map((bus) => {
        // Find nearest DT by simple Euclidean distance
        let nearestDT: GridNode | null = null
        let minDist = Infinity
        for (const dt of dtNodes) {
          const dist = Math.sqrt(
            Math.pow(bus.lat - dt.lat!, 2) + Math.pow(bus.lng - dt.lng!, 2)
          )
          if (dist < minDist) {
            minDist = dist
            nearestDT = dt
          }
        }
        if (!nearestDT) return null

        return (
          <Polyline
            key={`flex-${bus.id}`}
            positions={[
              [nearestDT.lat!, nearestDT.lng!],
              [bus.lat, bus.lng],
            ]}
            pathOptions={{
              color: '#6366f1',
              weight: 1,
              opacity: 0.55,
              dashArray: '4 4',
            }}
          />
        )
      })}
    </>
  )
}

// ─── Inner map content (needs access to map zoom state) ──────────────────────

interface MapContentProps {
  nodes: GridNode[]
  assets: DERAssetLive[]
  lvNetworkData: LVNetworkGeoJSON | null
  lvBuses: LVBusPoint[]
  flexEnrolledBusIds: string[]
  tileProvider: TileProvider
  onSelectAsset?: (asset: DERAssetLive) => void
  onSelectDT?: (nodeId: string) => void
  onZoomChange: (z: number) => void
  zoom: number
}

function MapContent({
  nodes,
  assets,
  lvNetworkData,
  lvBuses,
  flexEnrolledBusIds,
  tileProvider,
  onSelectAsset,
  onSelectDT,
  onZoomChange,
  zoom,
}: MapContentProps) {
  const provider = TILE_PROVIDERS[tileProvider]
  const nodesWithCoords = nodes.filter((n) => n.lat != null && n.lng != null)
  const assetsWithCoords = assets.filter((a) => a.lat != null && a.lng != null)
  const lvBusesWithCoords = lvBuses.filter((b) => b.lat != null && b.lng != null)

  return (
    <>
      <ZoomTracker onZoomChange={onZoomChange} />
      <FitBoundsController assets={assets} nodes={nodes} />
      <LayersControl position="topleft">
        <TileLayer
          url={provider.url}
          attribution={provider.attribution}
          key={tileProvider}
        />

        {/* Grid Nodes (substations + feeders always; DTs at zoom ≥ 12) */}
        <LayersControl.Overlay checked name="Grid Nodes">
          <>
            {nodesWithCoords.map((node) => (
              <NodeMarker
                key={node.node_id}
                node={node}
                onSelectDT={onSelectDT}
                zoom={zoom}
              />
            ))}
          </>
        </LayersControl.Overlay>

        {/* DER Assets layer */}
        <LayersControl.Overlay checked name="DER Assets">
          <>
            {assetsWithCoords.map((asset) => (
              <AssetMarker
                key={asset.id}
                asset={asset}
                onSelectAsset={onSelectAsset}
              />
            ))}
          </>
        </LayersControl.Overlay>

        {/* LV Network overlay (zoom ≥ 12) */}
        {lvNetworkData && zoom >= 12 && (
          <LayersControl.Overlay checked name="LV Feeder Routes">
            <GeoJSON
              key={JSON.stringify(lvNetworkData).slice(0, 64)}
              data={lvNetworkData as any}
              style={lvLineStyle}
            />
          </LayersControl.Overlay>
        )}

        {/* Flex interconnection lines (zoom ≥ 13) */}
        {zoom >= 13 && flexEnrolledBusIds.length > 0 && (
          <LayersControl.Overlay checked name="Flex Links">
            <FlexLines
              nodes={nodes}
              lvBuses={lvBusesWithCoords}
              flexEnrolledBusIds={flexEnrolledBusIds}
            />
          </LayersControl.Overlay>
        )}

        {/* Home-level LV bus markers (zoom ≥ 15) */}
        {zoom >= 15 && lvBusesWithCoords.length > 0 && (
          <LayersControl.Overlay checked name="LV Bus Points">
            <>
              {lvBusesWithCoords.map((bus) => (
                <HomeMarker
                  key={bus.id}
                  bus={bus}
                  isFlexEnrolled={flexEnrolledBusIds.includes(bus.id)}
                />
              ))}
            </>
          </LayersControl.Overlay>
        )}
      </LayersControl>
    </>
  )
}

// ─── Main GISMap Component ────────────────────────────────────────────────────

export default function GISMap({
  nodes,
  assets,
  deployment,
  onSelectAsset,
  onSelectDT,
  height = 400,
  lvNetworkData = null,
  lvBuses = [],
  flexEnrolledBusIds = [],
}: GISMapProps) {
  const [tileProvider, setTileProvider] = useState<TileProvider>('osm')
  const [zoom, setZoom] = useState<number>(DEFAULT_ZOOM)

  const deploymentConfig = DEPLOYMENT_BOUNDS[deployment] ?? null

  // Compute initial view from data if no preset
  const initialCenter: [number, number] = (() => {
    if (deploymentConfig) return deploymentConfig.center
    const lats = [
      ...assets.filter((a) => a.lat != null).map((a) => a.lat!),
      ...nodes.filter((n) => n.lat != null).map((n) => n.lat!),
    ]
    const lngs = [
      ...assets.filter((a) => a.lng != null).map((a) => a.lng!),
      ...nodes.filter((n) => n.lng != null).map((n) => n.lng!),
    ]
    if (lats.length === 0) return DEFAULT_CENTER
    const avgLat = lats.reduce((s, v) => s + v, 0) / lats.length
    const avgLng = lngs.reduce((s, v) => s + v, 0) / lngs.length
    return [avgLat, avgLng]
  })()

  const initialZoom = deploymentConfig?.zoom ?? DEFAULT_ZOOM

  const assetsWithCoords = assets.filter((a) => a.lat != null && a.lng != null)
  const nodesWithCoords = nodes.filter((n) => n.lat != null && n.lng != null)

  const hasData = assetsWithCoords.length > 0 || nodesWithCoords.length > 0

  return (
    <div style={{ position: 'relative', height }}>
      <MapContainer
        center={initialCenter}
        zoom={initialZoom}
        style={{ height: '100%', width: '100%', borderRadius: 8, background: '#111827' }}
        zoomControl
      >
        <MapContent
          nodes={nodes}
          assets={assets}
          lvNetworkData={lvNetworkData}
          lvBuses={lvBuses}
          flexEnrolledBusIds={flexEnrolledBusIds}
          tileProvider={tileProvider}
          onSelectAsset={onSelectAsset}
          onSelectDT={onSelectDT}
          onZoomChange={setZoom}
          zoom={zoom}
        />
      </MapContainer>

      {/* Tile provider selector overlay */}
      <TileProviderSelector value={tileProvider} onChange={setTileProvider} />

      {/* Legend overlay */}
      <MapLegend assets={assets} zoom={zoom} />

      {/* Zoom level detail indicator */}
      <div
        style={{
          position: 'absolute',
          top: 10,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 1000,
          background: 'rgba(17,24,39,0.85)',
          border: '1px solid rgba(75,85,99,0.6)',
          borderRadius: 20,
          padding: '3px 10px',
          fontSize: 10,
          color: zoom >= 15 ? '#22c55e' : zoom >= 12 ? '#818cf8' : '#6b7280',
          fontWeight: 600,
          letterSpacing: '0.04em',
          pointerEvents: 'none',
        }}
      >
        {zoom >= 15 ? 'HOME DETAIL' : zoom >= 12 ? 'DT NETWORK' : 'GRID OVERVIEW'}
      </div>

      {/* Empty state overlay */}
      {!hasData && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
            zIndex: 500,
          }}
        >
          <div
            style={{
              background: 'rgba(17,24,39,0.85)',
              border: '1px solid rgba(75,85,99,0.6)',
              borderRadius: 10,
              padding: '14px 22px',
              color: '#6b7280',
              fontSize: 13,
            }}
          >
            No asset location data available
          </div>
        </div>
      )}
    </div>
  )
}
