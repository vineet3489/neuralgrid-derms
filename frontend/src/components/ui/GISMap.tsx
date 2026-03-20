import React, { useState, useMemo } from 'react'
import clsx from 'clsx'
import type { GridNode, DERAssetLive } from '../../types'

interface GISMapProps {
  nodes: GridNode[]
  assets: DERAssetLive[]
  deployment: string
  onSelectAsset?: (asset: DERAssetLive) => void
  height?: number
}

interface TooltipState {
  x: number
  y: number
  content: React.ReactNode
}

const DEPLOYMENT_BOUNDS: Record<string, { minLat: number; maxLat: number; minLng: number; maxLng: number; label: string }> = {
  ssen: { minLat: 58.9, maxLat: 60.5, minLng: -3.3, maxLng: -1.0, label: 'SSEN — Shetland & Orkney' },
  puvvnl: { minLat: 25.24, maxLat: 25.40, minLng: 82.95, maxLng: 83.08, label: 'PUVVNL — Varanasi' },
}

function getAssetColor(status: string): string {
  switch (status?.toUpperCase()) {
    case 'ONLINE': return '#22c55e'
    case 'OFFLINE': return '#ef4444'
    case 'CURTAILED': return '#f59e0b'
    case 'WARNING': return '#f59e0b'
    default: return '#6b7280'
  }
}

function getNodeColor(nodeType: string): string {
  switch (nodeType) {
    case 'SUBSTATION': return '#818cf8'
    case 'DISTRIBUTION_TRANSFORMER': return '#60a5fa'
    case 'FEEDER': return '#94a3b8'
    default: return '#6b7280'
  }
}

function getAssetTypeLabel(type: string): string {
  const map: Record<string, string> = {
    BATTERY: 'BESS',
    SOLAR_PV: 'Solar',
    WIND: 'Wind',
    EV_CHARGER: 'EV',
    HEAT_PUMP: 'HP',
    DEMAND: 'Load',
    FLEXIBLE_LOAD: 'Flex',
  }
  return map[type] || type?.slice(0, 4) || '?'
}

export default function GISMap({
  nodes,
  assets,
  deployment,
  onSelectAsset,
  height = 400,
}: GISMapProps) {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const W = 780
  const H = height

  const bounds = useMemo(() => {
    const preset = DEPLOYMENT_BOUNDS[deployment]
    if (preset) return preset

    // Calculate from data
    const lats = [
      ...assets.filter((a) => a.lat).map((a) => a.lat!),
      ...nodes.filter((n) => n.lat).map((n) => n.lat!),
    ]
    const lngs = [
      ...assets.filter((a) => a.lng).map((a) => a.lng!),
      ...nodes.filter((n) => n.lng).map((n) => n.lng!),
    ]
    if (!lats.length) return DEPLOYMENT_BOUNDS['ssen']
    const pad = 0.02
    return {
      minLat: Math.min(...lats) - pad,
      maxLat: Math.max(...lats) + pad,
      minLng: Math.min(...lngs) - pad,
      maxLng: Math.max(...lngs) + pad,
      label: deployment.toUpperCase(),
    }
  }, [assets, nodes, deployment])

  const MARGIN = { top: 24, bottom: 24, left: 24, right: 24 }
  const innerW = W - MARGIN.left - MARGIN.right
  const innerH = H - MARGIN.top - MARGIN.bottom

  function toSVG(lat: number, lng: number): [number, number] {
    const x =
      MARGIN.left +
      ((lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * innerW
    const y =
      MARGIN.top +
      ((bounds.maxLat - lat) / (bounds.maxLat - bounds.minLat)) * innerH
    return [x, y]
  }

  const assetsWithPos = useMemo(
    () =>
      assets
        .filter((a) => a.lat != null && a.lng != null)
        .map((a) => ({ ...a, svgPos: toSVG(a.lat!, a.lng!) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [assets, bounds]
  )

  const nodesWithPos = useMemo(
    () =>
      nodes
        .filter((n) => n.lat != null && n.lng != null)
        .map((n) => ({ ...n, svgPos: toSVG(n.lat!, n.lng!) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [nodes, bounds]
  )

  // Synthetic demo positions if no lat/lng provided
  const syntheticAssets = useMemo(() => {
    if (assetsWithPos.length > 0) return []
    const cols = Math.ceil(Math.sqrt(assets.length))
    return assets.map((a, i) => {
      const row = Math.floor(i / cols)
      const col = i % cols
      const x = MARGIN.left + 40 + col * ((innerW - 80) / Math.max(cols - 1, 1))
      const y = MARGIN.top + 40 + row * ((innerH - 80) / Math.max(Math.ceil(assets.length / cols) - 1, 1))
      return { ...a, svgPos: [x, y] as [number, number] }
    })
  }, [assetsWithPos, assets, innerW, innerH, MARGIN])

  const displayAssets = assetsWithPos.length > 0 ? assetsWithPos : syntheticAssets

  const onlineCnt = assets.filter((a) => a.status === 'ONLINE').length
  const offlineCnt = assets.filter((a) => a.status === 'OFFLINE').length
  const curtailedCnt = assets.filter((a) => a.status === 'CURTAILED').length

  return (
    <div className="relative select-none" style={{ height }}>
      {/* Legend */}
      <div className="absolute top-2 right-2 z-10 bg-gray-900/90 border border-gray-700 rounded-lg p-2 flex flex-col gap-1.5">
        <div className="text-xs font-medium text-gray-300 mb-0.5">{bounds.label}</div>
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
          Online ({onlineCnt})
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
          Curtailed ({curtailedCnt})
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
          Offline ({offlineCnt})
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-400">
          <div className="w-2.5 h-2.5 rounded-sm bg-blue-400" />
          Node
        </div>
      </div>

      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="bg-gray-900/50 rounded-lg border border-gray-700 w-full"
        onMouseLeave={() => setTooltip(null)}
      >
        {/* Grid background */}
        <defs>
          <pattern id="grid-pat" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1f2937" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#grid-pat)" />

        {/* Node connections (simple lines to simulate feeder paths) */}
        {nodesWithPos.length > 1 &&
          nodesWithPos.slice(0, -1).map((n, i) => {
            const next = nodesWithPos[i + 1]
            return (
              <line
                key={`conn-${i}`}
                x1={n.svgPos[0]}
                y1={n.svgPos[1]}
                x2={next.svgPos[0]}
                y2={next.svgPos[1]}
                stroke="#374151"
                strokeWidth="1.5"
                strokeDasharray="4 3"
              />
            )
          })}

        {/* Grid Nodes */}
        {nodesWithPos.map((node) => {
          const [x, y] = node.svgPos
          const color = getNodeColor(node.node_type)
          const size = node.node_type === 'SUBSTATION' ? 8 : 6
          const loadPct = node.current_loading_pct || 0
          const borderColor = loadPct > 90 ? '#ef4444' : loadPct > 75 ? '#f59e0b' : color

          return (
            <g
              key={node.node_id}
              onMouseEnter={(e) => {
                const rect = (e.target as SVGElement)
                  .closest('svg')!
                  .getBoundingClientRect()
                setTooltip({
                  x: e.clientX - rect.left,
                  y: e.clientY - rect.top,
                  content: (
                    <div>
                      <div className="font-semibold text-gray-200 mb-1">{node.name}</div>
                      <div className="text-xs text-gray-400">{node.node_type.replace(/_/g, ' ')}</div>
                      <div className="text-xs text-gray-400 mt-1">
                        Loading: <span className={loadPct > 90 ? 'text-red-400' : loadPct > 75 ? 'text-amber-400' : 'text-green-400'}>{loadPct.toFixed(1)}%</span>
                      </div>
                      <div className="text-xs text-gray-400">
                        HC: {node.hosting_capacity_kw?.toFixed(0)} kW
                      </div>
                    </div>
                  ),
                })
              }}
              onMouseLeave={() => setTooltip(null)}
            >
              <rect
                x={x - size}
                y={y - size}
                width={size * 2}
                height={size * 2}
                fill={color + '33'}
                stroke={borderColor}
                strokeWidth="1.5"
                rx="2"
              />
            </g>
          )
        })}

        {/* DER Assets */}
        {displayAssets.map((asset) => {
          const [x, y] = asset.svgPos
          const color = getAssetColor(asset.status)
          const r = 7
          const isSelected = selectedId === asset.id
          const pct = asset.capacity_kw > 0
            ? Math.min((asset.current_kw / asset.capacity_kw) * 100, 100)
            : 0

          return (
            <g
              key={asset.id}
              className="cursor-pointer"
              onClick={() => {
                setSelectedId(asset.id)
                onSelectAsset?.(asset)
              }}
              onMouseEnter={(e) => {
                const rect = (e.target as SVGElement)
                  .closest('svg')!
                  .getBoundingClientRect()
                setTooltip({
                  x: e.clientX - rect.left,
                  y: e.clientY - rect.top,
                  content: (
                    <div>
                      <div className="font-semibold text-gray-200 mb-1">{asset.name}</div>
                      <div className="text-xs text-gray-400">{asset.asset_ref}</div>
                      <div className="flex items-center gap-1.5 mt-1">
                        <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
                        <span className="text-xs text-gray-300">{asset.status}</span>
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        Type: {asset.type?.replace(/_/g, ' ')}
                      </div>
                      <div className="text-xs text-gray-400">
                        Output: {asset.current_kw?.toFixed(1)} / {asset.capacity_kw?.toFixed(0)} kW
                      </div>
                      {asset.current_soc_pct != null && (
                        <div className="text-xs text-gray-400">
                          SoC: {asset.current_soc_pct.toFixed(1)}%
                        </div>
                      )}
                    </div>
                  ),
                })
              }}
              onMouseLeave={() => setTooltip(null)}
            >
              {/* Pulse ring for critical assets */}
              {asset.status === 'OFFLINE' && (
                <circle cx={x} cy={y} r={r + 4} fill="none" stroke="#ef4444" strokeWidth="1" opacity="0.4">
                  <animate attributeName="r" values={`${r + 2};${r + 8};${r + 2}`} dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Selection ring */}
              {isSelected && (
                <circle cx={x} cy={y} r={r + 4} fill="none" stroke="#6366f1" strokeWidth="2" />
              )}

              {/* Main circle */}
              <circle cx={x} cy={y} r={r} fill={color + '33'} stroke={color} strokeWidth="1.5" />

              {/* Type label */}
              <text
                x={x}
                y={y + 1}
                textAnchor="middle"
                dominantBaseline="middle"
                fill={color}
                fontSize="5"
                fontWeight="600"
              >
                {getAssetTypeLabel(asset.type)}
              </text>

              {/* SoC arc for batteries */}
              {asset.type === 'BATTERY' && asset.current_soc_pct != null && (
                <circle
                  cx={x}
                  cy={y}
                  r={r + 2}
                  fill="none"
                  stroke="#6366f1"
                  strokeWidth="1.5"
                  strokeDasharray={`${(asset.current_soc_pct / 100) * (2 * Math.PI * (r + 2))} ${2 * Math.PI * (r + 2)}`}
                  transform={`rotate(-90 ${x} ${y})`}
                  opacity="0.7"
                />
              )}

              {/* Output fill indicator */}
              {pct > 0 && (
                <line
                  x1={x - r + 1}
                  y1={y + r - 2}
                  x2={x - r + 1 + (pct / 100) * (r * 2 - 2)}
                  y2={y + r - 2}
                  stroke={color}
                  strokeWidth="1.5"
                  opacity="0.6"
                />
              )}
            </g>
          )
        })}
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="absolute z-20 bg-gray-800 border border-gray-600 rounded-lg p-2.5 text-xs shadow-xl pointer-events-none"
          style={{
            left: Math.min(tooltip.x + 12, W - 160),
            top: tooltip.y - 10,
            maxWidth: 180,
          }}
        >
          {tooltip.content}
        </div>
      )}

      {/* Empty state */}
      {displayAssets.length === 0 && nodesWithPos.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
          No asset location data available
        </div>
      )}
    </div>
  )
}
