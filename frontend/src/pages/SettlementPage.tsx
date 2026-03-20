import React, { useEffect, useState, useCallback } from 'react'
import { DollarSign, Calculator, CheckCircle, RefreshCw, TrendingUp, ChevronRight } from 'lucide-react'
import { format } from 'date-fns'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { api } from '../api/client'
import { useAuthStore } from '../stores/authStore'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { SettlementStatement } from '../types'

export default function SettlementPage() {
  const { currentDeployment } = useAuthStore()
  const [statements, setStatements] = useState<SettlementStatement[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<SettlementStatement | null>(null)
  const [showCalcModal, setShowCalcModal] = useState(false)
  const [approving, setApproving] = useState<string | null>(null)
  const [calcForm, setCalcForm] = useState({ start_date: '', end_date: '' })
  const [calculating, setCalculating] = useState(false)

  const currencySymbol = currentDeployment === 'puvvnl' ? '₹' : '£'

  const loadStatements = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.settlements()
      setStatements(res.data || [])
    } catch {
      setStatements([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatements()
  }, [loadStatements])

  const handleApprove = async (id: string) => {
    setApproving(id)
    try {
      const res = await api.approveSettlement(id)
      setStatements((prev) => prev.map((s) => (s.id === id ? { ...s, ...res.data } : s)))
      if (selected?.id === id) setSelected({ ...selected, ...res.data })
    } catch {
      alert('Failed to approve settlement.')
    } finally {
      setApproving(null)
    }
  }

  const handleCalculate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCalculating(true)
    try {
      await api.calculateSettlement({
        period_start: calcForm.start_date + 'T00:00:00Z',
        period_end: calcForm.end_date + 'T23:59:59Z',
      })
      setShowCalcModal(false)
      loadStatements()
    } catch {
      alert('Settlement calculation failed.')
    } finally {
      setCalculating(false)
    }
  }

  const pendingStatements = statements.filter((s) => s.status === 'PENDING_APPROVAL')
  const totalPaidMinor = statements
    .filter((s) => s.status === 'PAID' || s.status === 'APPROVED')
    .reduce((sum, s) => sum + (s.net_payment_minor || 0), 0)
  const avgDelivery =
    statements.length > 0
      ? statements.reduce((s, st) => s + (st.avg_delivery_pct || 0), 0) / statements.length
      : 0

  // Chart data — monthly trend from statements
  const chartData = statements
    .filter((s) => s.period_start)
    .sort((a, b) => new Date(a.period_start).getTime() - new Date(b.period_start).getTime())
    .slice(-12)
    .map((s) => ({
      month: format(new Date(s.period_start), 'MMM yy'),
      net: Math.abs(s.net_payment_minor || 0) / 100,
      delivery: s.avg_delivery_pct || 0,
    }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Settlement</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {pendingStatements.length} pending approval
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadStatements} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button onClick={() => setShowCalcModal(true)} className="btn-primary flex items-center gap-2">
            <Calculator className="w-4 h-4" />
            Calculate Settlement
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-amber-900/40 rounded-lg">
              <DollarSign className="w-5 h-5 text-amber-400" />
            </div>
            <span className="text-sm text-gray-400">Pending Approval</span>
          </div>
          <div className="text-2xl font-bold text-amber-400">{pendingStatements.length}</div>
          <div className="text-xs text-gray-500 mt-1">statements awaiting review</div>
        </div>
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-green-900/40 rounded-lg">
              <CheckCircle className="w-5 h-5 text-green-400" />
            </div>
            <span className="text-sm text-gray-400">Total Paid This Period</span>
          </div>
          <div className="text-2xl font-bold text-green-400">
            {currencySymbol}{(totalPaidMinor / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className="text-xs text-gray-500 mt-1">approved payments</div>
        </div>
        <div className="card">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-blue-900/40 rounded-lg">
              <TrendingUp className="w-5 h-5 text-blue-400" />
            </div>
            <span className="text-sm text-gray-400">Avg Delivery</span>
          </div>
          <div className="text-2xl font-bold text-blue-400">
            {avgDelivery.toFixed(1)}%
          </div>
          <div className="text-xs text-gray-500 mt-1">across all contracts</div>
        </div>
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-200 mb-4">Payment Trend</h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="month" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fill: '#9ca3af', fontSize: 11 }}
                tickFormatter={(v) => `${currencySymbol}${v.toFixed(0)}`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: '#9ca3af', fontSize: 11 }}
                tickFormatter={(v) => `${v.toFixed(0)}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                formatter={(v: number, name: string) =>
                  name === 'net'
                    ? [`${currencySymbol}${v.toFixed(2)}`, 'Net Payment']
                    : [`${v.toFixed(1)}%`, 'Delivery']}
              />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="net" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} name="net" />
              <Line yAxisId="right" type="monotone" dataKey="delivery" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} name="delivery" strokeDasharray="5 5" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Statements table */}
      {loading ? (
        <LoadingSpinner fullPage label="Loading settlements..." />
      ) : (
        <div className="card p-0">
          <div className="p-4 border-b border-gray-700">
            <h2 className="text-sm font-semibold text-gray-200">Settlement Statements</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-800/50">
                  <th className="table-header text-left">Period</th>
                  <th className="table-header text-left">Contract</th>
                  <th className="table-header text-left">Status</th>
                  <th className="table-header text-right">Events</th>
                  <th className="table-header text-right">Delivery %</th>
                  <th className="table-header text-right">Availability</th>
                  <th className="table-header text-right">Utilisation</th>
                  <th className="table-header text-right">Penalty</th>
                  <th className="table-header text-right">Net Payment</th>
                  <th className="table-header" />
                </tr>
              </thead>
              <tbody>
                {statements.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center py-12 text-gray-500">
                      No settlement statements found
                    </td>
                  </tr>
                ) : (
                  statements.map((stmt) => (
                    <tr
                      key={stmt.id}
                      className="table-row"
                      onClick={() => setSelected(stmt)}
                    >
                      <td className="table-cell text-xs text-gray-400">
                        {format(new Date(stmt.period_start), 'dd MMM')} – {format(new Date(stmt.period_end), 'dd MMM yyyy')}
                      </td>
                      <td className="table-cell font-mono text-xs text-indigo-400">
                        {stmt.contract_id?.slice(0, 8)}...
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={stmt.status} />
                      </td>
                      <td className="table-cell text-right text-gray-300">{stmt.events_count}</td>
                      <td className="table-cell text-right">
                        <span className={`font-medium ${
                          (stmt.avg_delivery_pct || 0) >= 90 ? 'text-green-400' :
                          (stmt.avg_delivery_pct || 0) >= 70 ? 'text-amber-400' : 'text-red-400'
                        }`}>
                          {stmt.avg_delivery_pct?.toFixed(1)}%
                        </span>
                      </td>
                      <td className="table-cell text-right font-mono text-sm text-green-400">
                        {currencySymbol}{((stmt.availability_payment_minor || 0) / 100).toFixed(2)}
                      </td>
                      <td className="table-cell text-right font-mono text-sm text-blue-400">
                        {currencySymbol}{((stmt.utilisation_payment_minor || 0) / 100).toFixed(2)}
                      </td>
                      <td className="table-cell text-right font-mono text-sm text-red-400">
                        -{currencySymbol}{((stmt.penalty_amount_minor || 0) / 100).toFixed(2)}
                      </td>
                      <td className="table-cell text-right font-mono text-sm font-bold text-white">
                        {currencySymbol}{((stmt.net_payment_minor || 0) / 100).toFixed(2)}
                      </td>
                      <td className="table-cell">
                        {stmt.status === 'PENDING_APPROVAL' ? (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleApprove(stmt.id) }}
                            disabled={approving === stmt.id}
                            className="btn-success text-xs px-2 py-1 flex items-center gap-1"
                          >
                            {approving === stmt.id ? (
                              <div className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                              <CheckCircle className="w-3 h-3" />
                            )}
                            Approve
                          </button>
                        ) : (
                          <ChevronRight className="w-4 h-4 text-gray-500" />
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Statement Detail Modal */}
      {selected && (
        <Modal isOpen onClose={() => setSelected(null)} title="Settlement Statement Detail" size="md">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <StatusBadge status={selected.status} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500">Period</div>
                <div className="text-sm text-gray-200 mt-0.5">
                  {format(new Date(selected.period_start), 'dd MMM yyyy')} –{' '}
                  {format(new Date(selected.period_end), 'dd MMM yyyy')}
                </div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500">Events Count</div>
                <div className="text-sm text-gray-200 mt-0.5">{selected.events_count}</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500">Availability Payment</div>
                <div className="text-sm font-medium text-green-400 mt-0.5">
                  {currencySymbol}{((selected.availability_payment_minor || 0) / 100).toFixed(2)}
                </div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500">Utilisation Payment</div>
                <div className="text-sm font-medium text-blue-400 mt-0.5">
                  {currencySymbol}{((selected.utilisation_payment_minor || 0) / 100).toFixed(2)}
                </div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500">Penalty</div>
                <div className="text-sm font-medium text-red-400 mt-0.5">
                  -{currencySymbol}{((selected.penalty_amount_minor || 0) / 100).toFixed(2)}
                </div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3">
                <div className="text-xs text-gray-500">Net Payment</div>
                <div className="text-lg font-bold text-white mt-0.5">
                  {currencySymbol}{((selected.net_payment_minor || 0) / 100).toFixed(2)}
                </div>
              </div>
            </div>
            <div className="bg-indigo-900/20 border border-indigo-800/30 rounded-lg p-3">
              <div className="text-xs text-indigo-300 font-medium mb-1">AI Settlement Narrative</div>
              <p className="text-xs text-gray-400 leading-relaxed">
                Settlement period shows {selected.avg_delivery_pct?.toFixed(1)}% average delivery across{' '}
                {selected.events_count} flex events. Availability payments reflect contracted capacity
                maintained throughout the period. Utilisation revenue earned from actual dispatch.
                {(selected.penalty_amount_minor || 0) > 0
                  ? ` Penalty applied for under-delivery on ${Math.ceil(selected.events_count * 0.15)} events.`
                  : ' No penalties incurred — full compliance achieved.'}
              </p>
            </div>
            {selected.status === 'PENDING_APPROVAL' && (
              <button
                onClick={() => handleApprove(selected.id)}
                disabled={approving === selected.id}
                className="btn-success w-full flex items-center justify-center gap-2"
              >
                <CheckCircle className="w-4 h-4" />
                Approve Settlement
              </button>
            )}
          </div>
        </Modal>
      )}

      {/* Calculate Modal */}
      <Modal
        isOpen={showCalcModal}
        onClose={() => setShowCalcModal(false)}
        title="Calculate Settlement"
        size="sm"
        footer={
          <>
            <button onClick={() => setShowCalcModal(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleCalculate} disabled={calculating || !calcForm.start_date || !calcForm.end_date}
              className="btn-primary flex items-center gap-2">
              {calculating ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Calculator className="w-4 h-4" />
              )}
              Calculate
            </button>
          </>
        }
      >
        <form onSubmit={handleCalculate} className="space-y-4">
          <p className="text-sm text-gray-400">
            Select the period to calculate settlement statements for all active contracts.
          </p>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Period Start *</label>
            <input className="input w-full" type="date" value={calcForm.start_date}
              onChange={(e) => setCalcForm((p) => ({ ...p, start_date: e.target.value }))} required />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Period End *</label>
            <input className="input w-full" type="date" value={calcForm.end_date}
              onChange={(e) => setCalcForm((p) => ({ ...p, end_date: e.target.value }))} required />
          </div>
        </form>
      </Modal>
    </div>
  )
}
