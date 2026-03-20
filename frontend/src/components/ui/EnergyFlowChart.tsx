import React, { useMemo } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import type { ForecastPoint } from '../../types'

interface EnergyFlowChartProps {
  solarData: ForecastPoint[]
  loadData: ForecastPoint[]
  height?: number
}

interface ChartPoint {
  time: string
  solar: number
  load: number
  solarLow: number
  solarHigh: number
  loadLow: number
  loadHigh: number
  isNow: boolean
}

const CustomTooltip = ({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-600 rounded-lg p-3 text-xs shadow-xl">
      <div className="text-gray-400 mb-2 font-medium">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 mb-1">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-gray-300 capitalize">{p.name}:</span>
          <span className="text-white font-medium">{p.value?.toFixed(1)} kW</span>
        </div>
      ))}
    </div>
  )
}

export default function EnergyFlowChart({
  solarData,
  loadData,
  height = 260,
}: EnergyFlowChartProps) {
  const now = new Date()

  const chartData: ChartPoint[] = useMemo(() => {
    const allTimes = new Set([
      ...solarData.map((d) => d.timestamp),
      ...loadData.map((d) => d.timestamp),
    ])
    const solarMap = new Map(solarData.map((d) => [d.timestamp, d]))
    const loadMap = new Map(loadData.map((d) => [d.timestamp, d]))

    return Array.from(allTimes)
      .sort()
      .map((t) => {
        const s = solarMap.get(t)
        const l = loadMap.get(t)
        const dt = parseISO(t)
        return {
          time: format(dt, 'HH:mm'),
          solar: s?.value_kw ?? 0,
          load: l?.value_kw ?? 0,
          solarLow: s?.confidence_low ?? 0,
          solarHigh: s?.confidence_high ?? 0,
          loadLow: l?.confidence_low ?? 0,
          loadHigh: l?.confidence_high ?? 0,
          isNow: Math.abs(dt.getTime() - now.getTime()) < 15 * 60 * 1000,
        }
      })
  }, [solarData, loadData, now])

  const nowIdx = chartData.findIndex((d) => d.isNow)
  const nowTime = nowIdx >= 0 ? chartData[nowIdx].time : null

  if (chartData.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-gray-500 text-sm"
        style={{ height }}
      >
        No forecast data available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="solarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="loadGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="time"
          stroke="#6b7280"
          tick={{ fill: '#9ca3af', fontSize: 11 }}
          interval="preserveStartEnd"
        />
        <YAxis
          stroke="#6b7280"
          tick={{ fill: '#9ca3af', fontSize: 11 }}
          width={50}
          tickFormatter={(v) => `${v} kW`}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ paddingTop: 8, fontSize: 12 }}
          formatter={(value) => (
            <span className="text-gray-300 capitalize">{value}</span>
          )}
        />
        {nowTime && (
          <ReferenceLine
            x={nowTime}
            stroke="#6366f1"
            strokeDasharray="4 4"
            label={{ value: 'Now', fill: '#818cf8', fontSize: 11 }}
          />
        )}
        {/* Confidence band for solar */}
        <Area
          type="monotone"
          dataKey="solarHigh"
          stroke="none"
          fill="#f59e0b"
          fillOpacity={0.1}
          legendType="none"
          name="Solar High"
        />
        <Area
          type="monotone"
          dataKey="solarLow"
          stroke="none"
          fill="#f59e0b"
          fillOpacity={0.1}
          legendType="none"
          name="Solar Low"
        />
        {/* Confidence band for load */}
        <Area
          type="monotone"
          dataKey="loadHigh"
          stroke="none"
          fill="#6366f1"
          fillOpacity={0.1}
          legendType="none"
          name="Load High"
        />
        <Area
          type="monotone"
          dataKey="loadLow"
          stroke="none"
          fill="#6366f1"
          fillOpacity={0.1}
          legendType="none"
          name="Load Low"
        />
        <Area
          type="monotone"
          dataKey="solar"
          stroke="#f59e0b"
          strokeWidth={2}
          fill="url(#solarGrad)"
          name="Solar"
          dot={false}
          activeDot={{ r: 4, fill: '#f59e0b' }}
        />
        <Area
          type="monotone"
          dataKey="load"
          stroke="#6366f1"
          strokeWidth={2}
          fill="url(#loadGrad)"
          name="Load"
          dot={false}
          activeDot={{ r: 4, fill: '#6366f1' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
