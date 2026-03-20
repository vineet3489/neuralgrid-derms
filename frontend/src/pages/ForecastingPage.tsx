import React, { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Sun, TrendingUp, Zap, Cpu } from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { format, parseISO } from 'date-fns'
import { api } from '../api/client'
import { useGridStore } from '../stores/gridStore'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { ForecastData, ForecastPoint } from '../types'

interface ForecastChartProps {
  data: ForecastPoint[]
  color: string
  gradientId: string
  title: string
  height?: number
}

function ForecastChart({ data, color, gradientId, title, height = 200 }: ForecastChartProps) {
  const now = new Date()
  const nowTime = data.find(
    (d) => Math.abs(parseISO(d.timestamp).getTime() - now.getTime()) < 30 * 60 * 1000
  )?.timestamp

  const chartData = data.map((d) => ({
    time: format(parseISO(d.timestamp), 'HH:mm'),
    value: d.value_kw,
    low: d.confidence_low,
    high: d.confidence_high,
  }))

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-gray-500 text-sm"
        style={{ height }}
      >
        No forecast data
      </div>
    )
  }

  const nowFormatted = nowTime ? format(parseISO(nowTime), 'HH:mm') : null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.4} />
            <stop offset="95%" stopColor={color} stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis
          dataKey="time"
          tick={{ fill: '#6b7280', fontSize: 10 }}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 10 }}
          tickFormatter={(v) => `${v.toFixed(0)}`}
          width={40}
        />
        <Tooltip
          contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', fontSize: 12 }}
          formatter={(v: number) => [`${v.toFixed(1)} kW`, title]}
          labelStyle={{ color: '#9ca3af' }}
        />
        {nowFormatted && (
          <ReferenceLine
            x={nowFormatted}
            stroke="#6366f1"
            strokeDasharray="3 3"
            label={{ value: 'Now', fill: '#818cf8', fontSize: 10 }}
          />
        )}
        {/* Confidence band */}
        <Area
          type="monotone"
          dataKey="high"
          stroke="none"
          fill={color}
          fillOpacity={0.15}
          legendType="none"
        />
        <Area
          type="monotone"
          dataKey="low"
          stroke="none"
          fill={color}
          fillOpacity={0.08}
          legendType="none"
        />
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export default function ForecastingPage() {
  const { forecasts, setForecasts } = useGridStore()
  const [loading, setLoading] = useState(!forecasts.solar)
  const [refreshing, setRefreshing] = useState(false)
  const [aiNarrative, setAiNarrative] = useState('')
  const [loadingAI, setLoadingAI] = useState(false)

  const loadForecasts = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    else setRefreshing(true)
    try {
      const res = await api.forecastAll()
      setForecasts(res.data || {})
    } catch {
      // keep existing
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [setForecasts])

  useEffect(() => {
    loadForecasts(false)
  }, [loadForecasts])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await api.forecastRefresh()
      await loadForecasts(true)
    } catch {
      await loadForecasts(true)
    }
  }

  const getAINarrative = async () => {
    setLoadingAI(true)
    try {
      const res = await api.optimizationRecommendations()
      setAiNarrative(
        res.data?.forecast_narrative ||
        res.data?.recommendation ||
        `Current forecasts show peak solar generation of ${
          Math.max(...(forecasts.solar?.values.map((v) => v.value_kw) || [0])).toFixed(0)
        } kW expected this afternoon. Load demand peaks at ${
          Math.max(...(forecasts.load?.values.map((v) => v.value_kw) || [0])).toFixed(0)
        } kW during evening. Flex availability of ${
          Math.max(...(forecasts.flex?.values.map((v) => v.value_kw) || [0])).toFixed(0)
        } kW provides adequate headroom for grid balancing operations.`
      )
    } catch {
      setAiNarrative(
        'AI forecast narrative unavailable. Ensure the optimization service is running.'
      )
    } finally {
      setLoadingAI(false)
    }
  }

  const solarData = forecasts.solar?.values || []
  const loadData = forecasts.load?.values || []
  const flexData = forecasts.flex?.values || []

  const peakSolar = solarData.length ? Math.max(...solarData.map((v) => v.value_kw)) : 0
  const peakLoad = loadData.length ? Math.max(...loadData.map((v) => v.value_kw)) : 0
  const peakFlex = flexData.length ? Math.max(...flexData.map((v) => v.value_kw)) : 0
  const avgConfidence = solarData.length
    ? solarData.reduce((s, d) => {
        const range = d.confidence_high - d.confidence_low
        const rel = range > 0 ? (1 - range / (d.value_kw + 0.1)) * 100 : 90
        return s + Math.max(0, Math.min(100, rel))
      }, 0) / solarData.length
    : 0

  if (loading) return <LoadingSpinner fullPage label="Loading forecasts..." />

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Forecasting</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            48-hour horizon · Model: {forecasts.solar?.model || 'Prophet + GBM Ensemble'}
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="btn-primary flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh Forecasts
        </button>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Peak Solar', value: peakSolar.toFixed(0), unit: 'kW', color: 'text-amber-400', icon: Sun },
          { label: 'Peak Load', value: peakLoad.toFixed(0), unit: 'kW', color: 'text-indigo-400', icon: TrendingUp },
          { label: 'Peak Flex', value: peakFlex.toFixed(0), unit: 'kW', color: 'text-green-400', icon: Zap },
          { label: 'Avg Confidence', value: avgConfidence.toFixed(0), unit: '%', color: 'text-blue-400', icon: Cpu },
        ].map(({ label, value, unit, color, icon: Icon }) => (
          <div key={label} className="card text-center">
            <Icon className={`w-5 h-5 mx-auto mb-2 ${color}`} />
            <div className={`text-xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-gray-500 mt-0.5">{unit} — {label}</div>
          </div>
        ))}
      </div>

      {/* Three forecast panels */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Solar */}
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <Sun className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-gray-200">Solar Generation Forecast</h3>
          </div>
          {forecasts.solar?.generated_at && (
            <p className="text-xs text-gray-500 mb-3">
              Generated: {new Date(forecasts.solar.generated_at).toLocaleTimeString('en-GB')}
            </p>
          )}
          <ForecastChart
            data={solarData}
            color="#f59e0b"
            gradientId="solarForecastGrad"
            title="Solar Generation"
            height={200}
          />
          <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
            <span>Peak: {peakSolar.toFixed(0)} kW</span>
            <span>{solarData.length} data points</span>
          </div>
        </div>

        {/* Load */}
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-gray-200">Load Demand Forecast</h3>
          </div>
          {forecasts.load?.generated_at && (
            <p className="text-xs text-gray-500 mb-3">
              Generated: {new Date(forecasts.load.generated_at).toLocaleTimeString('en-GB')}
            </p>
          )}
          <ForecastChart
            data={loadData}
            color="#6366f1"
            gradientId="loadForecastGrad"
            title="Load Demand"
            height={200}
          />
          <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
            <span>Peak: {peakLoad.toFixed(0)} kW</span>
            <span>{loadData.length} data points</span>
          </div>
        </div>

        {/* Flex */}
        <div className="card">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-green-400" />
            <h3 className="text-sm font-semibold text-gray-200">Flex Availability Forecast</h3>
          </div>
          {forecasts.flex?.generated_at && (
            <p className="text-xs text-gray-500 mb-3">
              Generated: {new Date(forecasts.flex.generated_at).toLocaleTimeString('en-GB')}
            </p>
          )}
          <ForecastChart
            data={flexData}
            color="#22c55e"
            gradientId="flexForecastGrad"
            title="Flex Availability"
            height={200}
          />
          <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
            <span>Peak: {peakFlex.toFixed(0)} kW</span>
            <span>{flexData.length} data points</span>
          </div>
        </div>
      </div>

      {/* AI Narrative */}
      <div className="card bg-indigo-900/10 border-indigo-800/30">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-indigo-300">AI Forecast Narrative</h3>
          </div>
          <button
            onClick={getAINarrative}
            disabled={loadingAI}
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1.5 btn-secondary py-1 px-2"
          >
            {loadingAI ? (
              <div className="w-3 h-3 border border-indigo-400/50 border-t-indigo-400 rounded-full animate-spin" />
            ) : (
              <Cpu className="w-3 h-3" />
            )}
            Generate Narrative
          </button>
        </div>
        {aiNarrative ? (
          <p className="text-sm text-gray-300 leading-relaxed">{aiNarrative}</p>
        ) : (
          <p className="text-sm text-gray-500">
            Click "Generate Narrative" for an AI-powered summary of current forecast conditions
            and recommended actions.
          </p>
        )}
      </div>

      {/* Forecast Accuracy Table (if data has history) */}
      {forecasts.solar && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Forecast Model Information</h3>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Solar Model', value: forecasts.solar?.model || '—', badge: 'badge-warning' },
              { label: 'Load Model', value: forecasts.load?.model || '—', badge: 'badge-info' },
              { label: 'Flex Model', value: forecasts.flex?.model || '—', badge: 'badge-online' },
            ].map(({ label, value, badge }) => (
              <div key={label} className="bg-gray-800/50 rounded-lg p-3">
                <div className="text-xs text-gray-500 mb-1">{label}</div>
                <span className={badge}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
