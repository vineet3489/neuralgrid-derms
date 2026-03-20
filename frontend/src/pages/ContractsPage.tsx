import React, { useEffect, useState, useCallback } from 'react'
import { Plus, Shield, RefreshCw, ChevronRight, Calculator, CheckCircle } from 'lucide-react'
import { format } from 'date-fns'
import { api } from '../api/client'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { Contract, Program } from '../types'

interface CreateContractForm {
  name: string
  contract_ref: string
  type: string
  program_id: string
  counterparty_id: string
  cmz_id: string
  contracted_capacity_kw: string
  availability_rate_minor: string
  utilisation_rate_minor: string
  start_date: string
  end_date: string
}

interface SimulationResult {
  availability_payment_minor: number
  utilisation_payment_minor: number
  penalty_amount_minor: number
  net_payment_minor: number
  currency_code: string
}

export default function ContractsPage() {
  const [contracts, setContracts] = useState<Contract[]>([])
  const [programs, setPrograms] = useState<Program[]>([])
  const [loading, setLoading] = useState(true)
  const [programFilter, setProgramFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [typeFilter, setTypeFilter] = useState('ALL')
  const [selectedContract, setSelectedContract] = useState<Contract | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showSimModal, setShowSimModal] = useState(false)
  const [simResult, setSimResult] = useState<SimulationResult | null>(null)
  const [simLoading, setSimLoading] = useState(false)
  const [activating, setActivating] = useState<string | null>(null)
  const [form, setForm] = useState<CreateContractForm>({
    name: '',
    contract_ref: '',
    type: 'AVAILABILITY',
    program_id: '',
    counterparty_id: '',
    cmz_id: '',
    contracted_capacity_kw: '',
    availability_rate_minor: '',
    utilisation_rate_minor: '',
    start_date: '',
    end_date: '',
  })
  const [creating, setCreating] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [contractsRes, programsRes] = await Promise.all([
        api.contracts(programFilter || undefined),
        api.programs(),
      ])
      setContracts(contractsRes.data || [])
      setPrograms(programsRes.data || [])
    } catch {
      setContracts([])
    } finally {
      setLoading(false)
    }
  }, [programFilter])

  useEffect(() => {
    loadData()
  }, [loadData])

  const filteredContracts = contracts.filter((c) => {
    const matchStatus = statusFilter === 'ALL' || c.status === statusFilter
    const matchType = typeFilter === 'ALL' || c.type === typeFilter
    return matchStatus && matchType
  })

  const handleActivate = async (id: string) => {
    setActivating(id)
    try {
      const res = await api.activateContract(id)
      setContracts((prev) => prev.map((c) => (c.id === id ? { ...c, ...res.data } : c)))
    } catch {
      alert('Failed to activate contract.')
    } finally {
      setActivating(null)
    }
  }

  const handleSimulate = async () => {
    if (!selectedContract) return
    setSimLoading(true)
    setSimResult(null)
    try {
      const res = await api.simulateSettlement(selectedContract.id, {
        period_start: new Date().toISOString().slice(0, 10) + 'T00:00:00Z',
        period_end: new Date().toISOString().slice(0, 10) + 'T23:59:59Z',
      })
      setSimResult(res.data)
      setShowSimModal(true)
    } catch {
      alert('Settlement simulation failed.')
    } finally {
      setSimLoading(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const res = await api.createContract({
        ...form,
        contracted_capacity_kw: parseFloat(form.contracted_capacity_kw),
        availability_rate_minor: parseInt(form.availability_rate_minor),
        utilisation_rate_minor: parseInt(form.utilisation_rate_minor),
      })
      setContracts((prev) => [res.data, ...prev])
      setShowCreateModal(false)
    } catch {
      alert('Failed to create contract.')
    } finally {
      setCreating(false)
    }
  }

  const getProgramName = (id: string) =>
    programs.find((p) => p.id === id)?.name || id

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Flexibility Contracts</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {contracts.filter((c) => c.status === 'ACTIVE').length} active ·{' '}
            {contracts.filter((c) => c.status === 'DRAFT').length} draft
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadData} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            New Contract
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={programFilter}
          onChange={(e) => setProgramFilter(e.target.value)}
          className="select text-sm"
        >
          <option value="">All Programs</option>
          {programs.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="select text-sm"
        >
          <option value="ALL">All Statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="DRAFT">Draft</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="TERMINATED">Terminated</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="select text-sm"
        >
          <option value="ALL">All Types</option>
          <option value="AVAILABILITY">Availability</option>
          <option value="UTILISATION">Utilisation</option>
          <option value="COMBINED">Combined</option>
          <option value="FLOOR">Floor Price</option>
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <LoadingSpinner fullPage label="Loading contracts..." />
      ) : (
        <div className="card p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-800/50">
                  <th className="table-header text-left">Contract Ref</th>
                  <th className="table-header text-left">Name</th>
                  <th className="table-header text-left">Program</th>
                  <th className="table-header text-left">Type</th>
                  <th className="table-header text-left">Status</th>
                  <th className="table-header text-left">CMZ</th>
                  <th className="table-header text-right">Capacity kW</th>
                  <th className="table-header text-right">Avail Rate</th>
                  <th className="table-header text-right">Util Rate</th>
                  <th className="table-header text-left">Expires</th>
                  <th className="table-header" />
                </tr>
              </thead>
              <tbody>
                {filteredContracts.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="text-center py-16 text-gray-500">
                      <Shield className="w-8 h-8 mx-auto mb-2 opacity-40" />
                      No contracts found
                    </td>
                  </tr>
                ) : (
                  filteredContracts.map((contract) => (
                    <tr
                      key={contract.id}
                      className="table-row"
                      onClick={() => setSelectedContract(contract)}
                    >
                      <td className="table-cell font-mono text-xs text-indigo-400">
                        {contract.contract_ref}
                      </td>
                      <td className="table-cell font-medium text-gray-200">
                        {contract.name}
                      </td>
                      <td className="table-cell text-xs text-gray-400">
                        {getProgramName(contract.program_id)}
                      </td>
                      <td className="table-cell">
                        <span className="badge-info text-xs">{contract.type}</span>
                      </td>
                      <td className="table-cell">
                        <StatusBadge status={contract.status} />
                      </td>
                      <td className="table-cell text-gray-400">{contract.cmz_id}</td>
                      <td className="table-cell text-right font-mono text-sm text-white">
                        {contract.contracted_capacity_kw?.toFixed(0)}
                      </td>
                      <td className="table-cell text-right font-mono text-xs text-green-400">
                        {(contract.availability_rate_minor / 100).toFixed(2)}
                      </td>
                      <td className="table-cell text-right font-mono text-xs text-blue-400">
                        {(contract.utilisation_rate_minor / 100).toFixed(2)}
                      </td>
                      <td className="table-cell text-xs text-gray-400">
                        {contract.end_date
                          ? format(new Date(contract.end_date), 'dd MMM yyyy')
                          : '—'}
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                          {contract.status === 'DRAFT' && (
                            <button
                              onClick={() => handleActivate(contract.id)}
                              disabled={activating === contract.id}
                              className="btn-success text-xs px-2 py-1 flex items-center gap-1"
                            >
                              {activating === contract.id ? (
                                <div className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                              ) : (
                                <CheckCircle className="w-3 h-3" />
                              )}
                              Activate
                            </button>
                          )}
                          <ChevronRight className="w-4 h-4 text-gray-500" />
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="p-3 border-t border-gray-700 text-xs text-gray-500">
            {filteredContracts.length} contracts
          </div>
        </div>
      )}

      {/* Contract Detail Side Panel */}
      {selectedContract && (
        <div className="fixed inset-y-0 right-0 w-96 bg-gray-900 border-l border-gray-700 shadow-2xl z-40 flex flex-col">
          <div className="flex items-center justify-between p-4 border-b border-gray-700">
            <div>
              <h3 className="text-sm font-semibold text-gray-100">{selectedContract.name}</h3>
              <p className="text-xs text-gray-500 mt-0.5">{selectedContract.contract_ref}</p>
            </div>
            <button onClick={() => setSelectedContract(null)} className="text-gray-400 hover:text-gray-200">
              ×
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="flex items-center gap-2">
              <StatusBadge status={selectedContract.status} />
              <span className="badge-info">{selectedContract.type}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: 'Capacity', value: `${selectedContract.contracted_capacity_kw?.toFixed(0)} kW` },
                { label: 'CMZ', value: selectedContract.cmz_id },
                { label: 'Avail Rate', value: `${(selectedContract.availability_rate_minor / 100).toFixed(2)} /kW/h` },
                { label: 'Util Rate', value: `${(selectedContract.utilisation_rate_minor / 100).toFixed(2)} /kWh` },
                { label: 'Start', value: selectedContract.start_date ? format(new Date(selectedContract.start_date), 'dd MMM yyyy') : '—' },
                { label: 'End', value: selectedContract.end_date ? format(new Date(selectedContract.end_date), 'dd MMM yyyy') : '—' },
              ].map(({ label, value }) => (
                <div key={label} className="bg-gray-800 rounded-lg p-2.5">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-sm text-gray-200 font-medium mt-0.5">{value}</div>
                </div>
              ))}
            </div>
            <button
              onClick={handleSimulate}
              disabled={simLoading}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {simLoading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Calculator className="w-4 h-4" />
              )}
              Simulate Settlement
            </button>
          </div>
        </div>
      )}

      {/* Simulation Result Modal */}
      <Modal
        isOpen={showSimModal}
        onClose={() => setShowSimModal(false)}
        title="Settlement Simulation"
        size="sm"
      >
        {simResult && (
          <div className="space-y-3">
            <p className="text-sm text-gray-400">Estimated settlement for today's period:</p>
            <div className="space-y-2">
              {[
                { label: 'Availability Payment', value: simResult.availability_payment_minor, color: 'text-green-400' },
                { label: 'Utilisation Payment', value: simResult.utilisation_payment_minor, color: 'text-blue-400' },
                { label: 'Penalty Deduction', value: -Math.abs(simResult.penalty_amount_minor), color: 'text-red-400' },
              ].map(({ label, value, color }) => (
                <div key={label} className="flex justify-between items-center py-2 border-b border-gray-700">
                  <span className="text-sm text-gray-400">{label}</span>
                  <span className={`text-sm font-medium ${color}`}>
                    {simResult.currency_code} {Math.abs(value / 100).toFixed(2)}
                  </span>
                </div>
              ))}
              <div className="flex justify-between items-center pt-1">
                <span className="text-sm font-semibold text-gray-200">Net Payment</span>
                <span className="text-lg font-bold text-white">
                  {simResult.currency_code} {(simResult.net_payment_minor / 100).toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Create Contract Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="New Flexibility Contract"
        size="lg"
        footer={
          <>
            <button onClick={() => setShowCreateModal(false)} className="btn-secondary">Cancel</button>
            <button
              onClick={handleCreate}
              disabled={creating}
              className="btn-primary flex items-center gap-2"
            >
              {creating ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Shield className="w-4 h-4" />
              )}
              Create Contract
            </button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-400 mb-1">Contract Name *</label>
              <input className="input w-full" value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Lerwick Battery Flex 2026" required />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Contract Ref</label>
              <input className="input w-full" value={form.contract_ref}
                onChange={(e) => setForm((p) => ({ ...p, contract_ref: e.target.value }))}
                placeholder="SSEN-FLEX-2026-001" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Type</label>
              <select className="select w-full" value={form.type}
                onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
                <option value="AVAILABILITY">Availability</option>
                <option value="UTILISATION">Utilisation</option>
                <option value="COMBINED">Combined</option>
                <option value="FLOOR">Floor Price</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Program</label>
              <select className="select w-full" value={form.program_id}
                onChange={(e) => setForm((p) => ({ ...p, program_id: e.target.value }))}>
                <option value="">Select program...</option>
                {programs.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">CMZ ID</label>
              <input className="input w-full" value={form.cmz_id}
                onChange={(e) => setForm((p) => ({ ...p, cmz_id: e.target.value }))}
                placeholder="CMZ-LERWICK-01" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Capacity (kW) *</label>
              <input className="input w-full" type="number" step="1" value={form.contracted_capacity_kw}
                onChange={(e) => setForm((p) => ({ ...p, contracted_capacity_kw: e.target.value }))}
                placeholder="500" required />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Availability Rate (minor/kW/h)</label>
              <input className="input w-full" type="number" value={form.availability_rate_minor}
                onChange={(e) => setForm((p) => ({ ...p, availability_rate_minor: e.target.value }))}
                placeholder="500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Utilisation Rate (minor/kWh)</label>
              <input className="input w-full" type="number" value={form.utilisation_rate_minor}
                onChange={(e) => setForm((p) => ({ ...p, utilisation_rate_minor: e.target.value }))}
                placeholder="1500" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Start Date</label>
              <input className="input w-full" type="date" value={form.start_date}
                onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">End Date</label>
              <input className="input w-full" type="date" value={form.end_date}
                onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value }))} />
            </div>
          </div>
        </form>
      </Modal>
    </div>
  )
}
