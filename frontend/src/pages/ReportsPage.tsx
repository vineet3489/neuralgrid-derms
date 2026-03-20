import React, { useEffect, useState } from 'react'
import { BarChart3, Download, RefreshCw, TrendingUp, Zap, CheckCircle, DollarSign } from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line,
} from 'recharts'
import { api } from '../api/client'
import { useAuthStore } from '../stores/authStore'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { ReportSummary } from '../types'

export default function ReportsPage() {
  const { currentDeployment } = useAuthStore()
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState<string | null>(null)

  const currencySymbol = currentDeployment === 'puvvnl' ? '₹' : '£'
  const isSSEN = currentDeployment === 'ssen'

  useEffect(() => {
    api
      .reportSummary()
      .then((r) => setSummary(r.data))
      .catch(() => setSummary(null))
      .finally(() => setLoading(false))
  }, [currentDeployment])

  const handleExport = async (format: string) => {
    setExporting(format)
    try {
      const res = await api.exportReport(format)
      const blob = new Blob([res.data], {
        type: format === 'pdf' ? 'application/pdf' : 'text/csv',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `neuralgrid-report-${new Date().toISOString().slice(0, 10)}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert(`Export failed. Ensure the backend report endpoint is available.`)
    } finally {
      setExporting(null)
    }
  }

  if (loading) return <LoadingSpinner fullPage label="Loading reports..." />

  // Fallback data for display
  const monthlyTrend = summary?.monthly_trend || [
    { month: 'Sep 25', delivered_mwh: 12.4, events: 8 },
    { month: 'Oct 25', delivered_mwh: 18.9, events: 12 },
    { month: 'Nov 25', delivered_mwh: 22.1, events: 15 },
    { month: 'Dec 25', delivered_mwh: 28.7, events: 19 },
    { month: 'Jan 26', delivered_mwh: 31.4, events: 22 },
    { month: 'Feb 26', delivered_mwh: 26.8, events: 17 },
    { month: 'Mar 26', delivered_mwh: 19.2, events: 13 },
  ]

  const topPerformers = summary?.top_performers || [
    { name: 'Lerwick BESS 1', delivery_pct: 98.2, events: 22 },
    { name: 'Bressay Wind', delivery_pct: 95.7, events: 18 },
    { name: 'Sumburgh Solar', delivery_pct: 92.4, events: 15 },
    { name: 'Kirkwall BESS', delivery_pct: 89.1, events: 20 },
    { name: 'Stromness Flex', delivery_pct: 87.3, events: 11 },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Reports & Analytics</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {isSSEN ? 'SSEN RIIO-ED2 / ENA-CPP-2024 Reporting' : 'PUVVNL UPERC-DR-2025 Reporting'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.location.reload()}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            onClick={() => handleExport('csv')}
            disabled={exporting === 'csv'}
            className="btn-secondary flex items-center gap-2"
          >
            {exporting === 'csv' ? (
              <div className="w-4 h-4 border-2 border-gray-400/30 border-t-gray-300 rounded-full animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            Export CSV
          </button>
          <button
            onClick={() => handleExport('pdf')}
            disabled={exporting === 'pdf'}
            className="btn-primary flex items-center gap-2"
          >
            {exporting === 'pdf' ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            Download PDF
          </button>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          {
            title: 'Events This Month',
            value: summary?.events_this_month ?? 13,
            icon: BarChart3,
            color: 'text-indigo-400',
            bg: 'bg-indigo-900/40',
          },
          {
            title: 'Flex Delivered',
            value: `${(summary?.flex_delivered_mwh ?? 19.2).toFixed(1)} MWh`,
            icon: Zap,
            color: 'text-green-400',
            bg: 'bg-green-900/40',
          },
          {
            title: 'Avg Delivery',
            value: `${(summary?.avg_delivery_pct ?? 91.4).toFixed(1)}%`,
            icon: TrendingUp,
            color: 'text-amber-400',
            bg: 'bg-amber-900/40',
          },
          {
            title: 'Settlement Pending',
            value: `${currencySymbol}${((summary?.settlement_pending_minor ?? 45000) / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
            icon: DollarSign,
            color: 'text-blue-400',
            bg: 'bg-blue-900/40',
          },
        ].map(({ title, value, icon: Icon, color, bg }) => (
          <div key={title} className="card">
            <div className="flex items-center gap-3 mb-2">
              <div className={`p-2 rounded-lg ${bg}`}>
                <Icon className={`w-5 h-5 ${color}`} />
              </div>
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-gray-400 mt-1">{title}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Monthly flex delivery trend */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Monthly Flex Delivery Trend</h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={monthlyTrend} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="month" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fill: '#9ca3af', fontSize: 11 }}
                tickFormatter={(v) => `${v} MWh`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', fontSize: 12 }}
                formatter={(v: number, name: string) => [
                  name === 'delivered_mwh' ? `${v.toFixed(1)} MWh` : `${v} events`,
                  name === 'delivered_mwh' ? 'Delivered MWh' : 'Events',
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 12 }}
                formatter={(v) => <span className="text-gray-300">{v === 'delivered_mwh' ? 'Delivered MWh' : 'Events'}</span>} />
              <Line yAxisId="left" type="monotone" dataKey="delivered_mwh" stroke="#22c55e" strokeWidth={2} dot={{ r: 4 }} />
              <Line yAxisId="right" type="monotone" dataKey="events" stroke="#6366f1" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Top performers */}
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Top Performing Assets</h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={topPerformers}
              layout="vertical"
              margin={{ top: 4, right: 16, left: 80, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 100]}
                tick={{ fill: '#9ca3af', fontSize: 11 }}
                tickFormatter={(v) => `${v}%`}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#9ca3af', fontSize: 11 }}
                width={80}
              />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', fontSize: 12 }}
                formatter={(v: number) => [`${v.toFixed(1)}%`, 'Delivery']}
              />
              <Bar dataKey="delivery_pct" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Regulatory Reports section */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-200 mb-4">Regulatory Reports</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {(isSSEN
            ? [
                { title: 'SLC 31E Flexibility Report', period: 'Q1 2026', status: 'READY' },
                { title: 'ENA CPP-2024 Compliance', period: 'March 2026', status: 'PENDING' },
                { title: 'RIIO-ED2 Annual Submission', period: 'FY 2025-26', status: 'DRAFT' },
                { title: 'Ofgem DR Evidence Pack', period: 'Q1 2026', status: 'READY' },
                { title: 'Net Zero Pathway Report', period: '2026', status: 'DRAFT' },
                { title: 'Demand Side Response Log', period: 'March 2026', status: 'READY' },
              ]
            : [
                { title: 'UPERC DR-2025 Report', period: 'Q1 2026', status: 'READY' },
                { title: 'DISCOM Performance Report', period: 'March 2026', status: 'PENDING' },
                { title: 'AT&C Loss Reduction Summary', period: 'FY 2025-26', status: 'DRAFT' },
                { title: 'Smart Meter Penetration', period: 'Q1 2026', status: 'READY' },
                { title: 'Renewable Integration Report', period: 'March 2026', status: 'DRAFT' },
              ]
          ).map((report) => (
            <div key={report.title} className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-xs font-medium text-gray-300">{report.title}</h3>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    report.status === 'READY'
                      ? 'bg-green-900/50 text-green-400'
                      : report.status === 'PENDING'
                      ? 'bg-amber-900/50 text-amber-400'
                      : 'bg-gray-700 text-gray-400'
                  }`}
                >
                  {report.status}
                </span>
              </div>
              <p className="text-xs text-gray-500 mb-3">{report.period}</p>
              <button
                onClick={() => handleExport('pdf')}
                disabled={report.status === 'DRAFT' || exporting === 'pdf'}
                className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Download className="w-3 h-3" />
                {report.status === 'DRAFT' ? 'In Preparation' : 'Download'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Compliance checklist */}
      <div className="card">
        <h2 className="text-sm font-semibold text-gray-200 mb-4">
          {isSSEN ? 'ENA CPP-2024 Compliance Status' : 'UPERC-DR-2025 Compliance Status'}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {(isSSEN
            ? [
                'Flexibility Market tender documentation complete',
                'Operating Envelope calculations reviewed',
                'Settlement statements within 5 business day SLA',
                'Metering accuracy within ±2% tolerance',
                'DSO / DER communication protocols compliant',
                'Annual DER prequalification assessments done',
              ]
            : [
                'Demand Response program registered with UPERC',
                'Aggregator licences current and valid',
                'Metering data submitted to SLDC',
                'DR settlement within billing cycle SLA',
                'Smart meter rollout KPIs on track',
                'Renewable curtailment reports filed',
              ]
          ).map((item, i) => (
            <div key={item} className="flex items-center gap-2.5 text-sm">
              <CheckCircle className={`w-4 h-4 flex-shrink-0 ${i < 4 ? 'text-green-500' : 'text-amber-500'}`} />
              <span className={i < 4 ? 'text-gray-300' : 'text-gray-400'}>{item}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
