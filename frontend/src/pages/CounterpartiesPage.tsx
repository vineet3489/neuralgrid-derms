import React, { useEffect, useState, useCallback } from 'react'
import { Plus, Users, Building2, ChevronRight, RefreshCw, Zap, CheckCircle } from 'lucide-react'
import { api } from '../api/client'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { Counterparty } from '../types'

interface CreateCounterpartyForm {
  name: string
  type: string
  comm_capability: string
  contact_name: string
  contact_email: string
  portfolio_kw: string
}

const PREQUALIFICATION_CHECKLIST = [
  'Grid connection agreement in place',
  'Insurance certificates provided',
  'Technical specification approved',
  'Communication system tested',
  'Site visit completed',
  'Compliance documentation submitted',
]

function CounterpartyCard({
  counterparty,
  onClick,
}: {
  counterparty: Counterparty
  onClick: () => void
}) {
  const typeIcons: Record<string, React.ReactNode> = {
    AGGREGATOR: <Users className="w-4 h-4" />,
    INDUSTRIAL: <Building2 className="w-4 h-4" />,
    GENERATOR: <Zap className="w-4 h-4" />,
    STORAGE: <Zap className="w-4 h-4" />,
    RESIDENTIAL: <Building2 className="w-4 h-4" />,
  }

  const preqColors: Record<string, string> = {
    PREQUALIFIED: 'text-green-400 bg-green-900/30 border-green-700/30',
    PENDING: 'text-amber-400 bg-amber-900/30 border-amber-700/30',
    REJECTED: 'text-red-400 bg-red-900/30 border-red-700/30',
    NOT_STARTED: 'text-gray-400 bg-gray-800 border-gray-700',
  }

  return (
    <div
      className="card cursor-pointer hover:border-indigo-600/50 transition-all duration-200"
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-gray-700 rounded-lg flex items-center justify-center text-indigo-400">
            {typeIcons[counterparty.type] || <Building2 className="w-4 h-4" />}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-100 leading-tight">{counterparty.name}</h3>
            <div className="text-xs text-gray-500 mt-0.5">{counterparty.type?.replace(/_/g, ' ')}</div>
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
      </div>

      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <StatusBadge status={counterparty.status} />
        <span
          className={`text-xs px-2 py-0.5 rounded-full border font-medium ${
            preqColors[counterparty.prequalification_status] || preqColors.NOT_STARTED
          }`}
        >
          {counterparty.prequalification_status?.replace(/_/g, ' ') || 'Not Started'}
        </span>
      </div>

      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-gray-400">
          <Zap className="w-3.5 h-3.5 text-indigo-400" />
          <span>{counterparty.portfolio_kw?.toFixed(0)} kW portfolio</span>
        </div>
        <div className="text-gray-500">
          {counterparty.comm_capability?.replace(/_/g, ' ')}
        </div>
      </div>

      {counterparty.contact_name && (
        <div className="mt-2 text-xs text-gray-500">
          Contact: {counterparty.contact_name}
        </div>
      )}
    </div>
  )
}

function CounterpartyDetailModal({
  counterparty,
  onClose,
}: {
  counterparty: Counterparty
  onClose: () => void
}) {
  return (
    <Modal isOpen onClose={onClose} title={counterparty.name} size="md">
      <div className="space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={counterparty.status} />
          <span className="badge-info">{counterparty.type?.replace(/_/g, ' ')}</span>
          <span className="badge-gray">{counterparty.prequalification_status?.replace(/_/g, ' ')}</span>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Portfolio', value: `${counterparty.portfolio_kw?.toFixed(0)} kW` },
            { label: 'Comms', value: counterparty.comm_capability?.replace(/_/g, ' ') },
            { label: 'Contact', value: counterparty.contact_name },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-800 rounded-lg p-2.5">
              <div className="text-xs text-gray-500">{label}</div>
              <div className="text-sm text-gray-200 font-medium mt-0.5">{value || '—'}</div>
            </div>
          ))}
        </div>

        {/* Prequalification checklist */}
        <div>
          <h4 className="text-sm font-medium text-gray-300 mb-2">Prequalification Checklist</h4>
          <div className="space-y-2">
            {PREQUALIFICATION_CHECKLIST.map((item, i) => {
              const done = counterparty.prequalification_status === 'PREQUALIFIED' || i < 3
              return (
                <div key={item} className="flex items-center gap-2 text-sm">
                  <CheckCircle
                    className={`w-4 h-4 flex-shrink-0 ${done ? 'text-green-500' : 'text-gray-600'}`}
                  />
                  <span className={done ? 'text-gray-300' : 'text-gray-500'}>{item}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default function CounterpartiesPage() {
  const [counterparties, setCounterparties] = useState<Counterparty[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [typeFilter, setTypeFilter] = useState('ALL')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Counterparty | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [form, setForm] = useState<CreateCounterpartyForm>({
    name: '',
    type: 'AGGREGATOR',
    comm_capability: 'DIRECT_API',
    contact_name: '',
    contact_email: '',
    portfolio_kw: '',
  })
  const [creating, setCreating] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.counterparties(statusFilter !== 'ALL' ? statusFilter : undefined)
      setCounterparties(res.data || [])
    } catch {
      setCounterparties([])
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    loadData()
  }, [loadData])

  const filtered = counterparties.filter((c) => {
    const matchType = typeFilter === 'ALL' || c.type === typeFilter
    const matchSearch =
      !search || c.name.toLowerCase().includes(search.toLowerCase())
    return matchType && matchSearch
  })

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const res = await api.createCounterparty({
        ...form,
        portfolio_kw: parseFloat(form.portfolio_kw) || 0,
      })
      setCounterparties((prev) => [res.data, ...prev])
      setShowCreateModal(false)
    } catch {
      alert('Failed to register counterparty.')
    } finally {
      setCreating(false)
    }
  }

  const totalPortfolioKw = counterparties.reduce((s, c) => s + (c.portfolio_kw || 0), 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Counterparties</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {counterparties.length} registered · {totalPortfolioKw.toFixed(0)} kW total portfolio
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadData} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Register
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Search counterparties..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input w-56"
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="select text-sm">
          <option value="ALL">All Statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
          <option value="SUSPENDED">Suspended</option>
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="select text-sm">
          <option value="ALL">All Types</option>
          <option value="AGGREGATOR">Aggregator</option>
          <option value="INDUSTRIAL">Industrial</option>
          <option value="GENERATOR">Generator</option>
          <option value="STORAGE">Storage</option>
          <option value="RESIDENTIAL">Residential</option>
        </select>
      </div>

      {/* Cards grid */}
      {loading ? (
        <LoadingSpinner fullPage label="Loading counterparties..." />
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <Users className="w-12 h-12 mb-4 opacity-40" />
          <p className="text-lg font-medium">No counterparties found</p>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary mt-4 flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Register First Counterparty
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((cp) => (
            <CounterpartyCard key={cp.id} counterparty={cp} onClick={() => setSelected(cp)} />
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selected && (
        <CounterpartyDetailModal counterparty={selected} onClose={() => setSelected(null)} />
      )}

      {/* Create Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Register Counterparty"
        size="md"
        footer={
          <>
            <button onClick={() => setShowCreateModal(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleCreate} disabled={creating || !form.name} className="btn-primary flex items-center gap-2">
              {creating ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Users className="w-4 h-4" />
              )}
              Register
            </button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Company Name *</label>
            <input className="input w-full" value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Shetland Energy Ltd" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Type</label>
              <select className="select w-full" value={form.type}
                onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
                <option value="AGGREGATOR">Aggregator</option>
                <option value="INDUSTRIAL">Industrial</option>
                <option value="GENERATOR">Generator</option>
                <option value="STORAGE">Storage</option>
                <option value="RESIDENTIAL">Residential</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Communication</label>
              <select className="select w-full" value={form.comm_capability}
                onChange={(e) => setForm((p) => ({ ...p, comm_capability: e.target.value }))}>
                <option value="DIRECT_API">Direct API</option>
                <option value="SMART_METER">Smart Meter</option>
                <option value="MODBUS">Modbus</option>
                <option value="MANUAL">Manual</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Contact Name</label>
              <input className="input w-full" value={form.contact_name}
                onChange={(e) => setForm((p) => ({ ...p, contact_name: e.target.value }))}
                placeholder="Jane Smith" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Portfolio (kW)</label>
              <input className="input w-full" type="number" step="1" value={form.portfolio_kw}
                onChange={(e) => setForm((p) => ({ ...p, portfolio_kw: e.target.value }))}
                placeholder="1000" />
            </div>
          </div>
        </form>
      </Modal>
    </div>
  )
}
