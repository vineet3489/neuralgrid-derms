import React, { useEffect, useState, useCallback } from 'react'
import { Plus, FileText, Calendar, TrendingUp, RefreshCw, ChevronRight, Target } from 'lucide-react'
import { format } from 'date-fns'
import { api } from '../api/client'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { Program } from '../types'

interface CreateProgramForm {
  name: string
  type: string
  target_mw: string
  regulatory_basis: string
  start_date: string
  end_date: string
}

interface ProgramKPIs {
  events_dispatched: number
  avg_delivery_pct: number
  total_cost_minor: number
  reinforcement_savings_minor: number
  enrolled_assets: number
}

function ProgramCard({
  program,
  onClick,
}: {
  program: Program
  onClick: () => void
}) {
  const enrollPct =
    program.target_mw > 0
      ? Math.min((program.enrolled_mw / program.target_mw) * 100, 100)
      : 0

  const typeColors: Record<string, string> = {
    FLEXIBILITY: 'text-indigo-400 bg-indigo-900/40',
    DEMAND_RESPONSE: 'text-blue-400 bg-blue-900/40',
    PEAK_SHAVING: 'text-amber-400 bg-amber-900/40',
    FREQUENCY_RESPONSE: 'text-green-400 bg-green-900/40',
    VOLTAGE_SUPPORT: 'text-purple-400 bg-purple-900/40',
  }
  const typeColor = typeColors[program.type] || 'text-gray-400 bg-gray-800'

  return (
    <div
      className="card cursor-pointer hover:border-indigo-600/50 transition-all duration-200 hover:shadow-lg hover:shadow-indigo-900/10"
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <h3 className="text-sm font-semibold text-gray-100">{program.name}</h3>
          <div className="flex items-center gap-2 mt-1.5">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeColor}`}>
              {program.type?.replace(/_/g, ' ')}
            </span>
            <StatusBadge status={program.status} />
          </div>
        </div>
        <ChevronRight className="w-4 h-4 text-gray-500 mt-1 flex-shrink-0" />
      </div>

      {/* MW Progress */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-xs text-gray-400 mb-1.5">
          <span>Enrolled Capacity</span>
          <span className="font-medium text-gray-300">
            {program.enrolled_mw?.toFixed(1)} / {program.target_mw?.toFixed(1)} MW
          </span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all bg-gradient-to-r from-indigo-600 to-indigo-400"
            style={{ width: `${enrollPct}%` }}
          />
        </div>
        <div className="text-xs text-gray-500 mt-1">{enrollPct.toFixed(0)}% of target</div>
      </div>

      {/* Dates */}
      <div className="flex items-center gap-3 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <Calendar className="w-3 h-3" />
          {format(new Date(program.start_date), 'dd MMM yyyy')}
        </span>
        <span>→</span>
        <span>{format(new Date(program.end_date), 'dd MMM yyyy')}</span>
      </div>

      {program.regulatory_basis && (
        <div className="mt-2 text-xs text-gray-600">
          Regulatory basis: {program.regulatory_basis}
        </div>
      )}
    </div>
  )
}

function ProgramDetailModal({
  program,
  onClose,
}: {
  program: Program
  onClose: () => void
}) {
  const [kpis, setKpis] = useState<ProgramKPIs | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .programKpis(program.id)
      .then((r) => setKpis(r.data))
      .catch(() => setKpis(null))
      .finally(() => setLoading(false))
  }, [program.id])

  const enrollPct =
    program.target_mw > 0
      ? Math.min((program.enrolled_mw / program.target_mw) * 100, 100)
      : 0

  return (
    <Modal isOpen onClose={onClose} title={program.name} size="lg">
      <div className="space-y-5">
        {/* Header Info */}
        <div className="flex items-center gap-3 flex-wrap">
          <StatusBadge status={program.status} />
          <span className="badge-info">{program.type?.replace(/_/g, ' ')}</span>
          {program.regulatory_basis && (
            <span className="badge-gray">{program.regulatory_basis}</span>
          )}
        </div>

        {/* Capacity */}
        <div>
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="text-gray-400">Enrolled Capacity</span>
            <span className="text-gray-200 font-semibold">
              {program.enrolled_mw?.toFixed(1)} / {program.target_mw?.toFixed(1)} MW
            </span>
          </div>
          <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-indigo-400"
              style={{ width: `${enrollPct}%` }}
            />
          </div>
        </div>

        {/* Date range */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-800 rounded-lg p-3">
            <div className="text-xs text-gray-500">Start Date</div>
            <div className="text-sm text-gray-200 font-medium mt-0.5">
              {format(new Date(program.start_date), 'dd MMMM yyyy')}
            </div>
          </div>
          <div className="bg-gray-800 rounded-lg p-3">
            <div className="text-xs text-gray-500">End Date</div>
            <div className="text-sm text-gray-200 font-medium mt-0.5">
              {format(new Date(program.end_date), 'dd MMMM yyyy')}
            </div>
          </div>
        </div>

        {/* KPIs */}
        <div>
          <h4 className="text-sm font-medium text-gray-300 mb-3">Program KPIs</h4>
          {loading ? (
            <LoadingSpinner size="sm" className="py-4" />
          ) : kpis ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-indigo-400">{kpis.events_dispatched}</div>
                <div className="text-xs text-gray-500 mt-0.5">Events Dispatched</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-green-400">
                  {kpis.avg_delivery_pct?.toFixed(1)}%
                </div>
                <div className="text-xs text-gray-500 mt-0.5">Avg Delivery</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-amber-400">{kpis.enrolled_assets}</div>
                <div className="text-xs text-gray-500 mt-0.5">Enrolled Assets</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-3 text-center">
                <div className="text-xl font-bold text-blue-400">
                  {((kpis.reinforcement_savings_minor || 0) / 100000).toFixed(0)}k
                </div>
                <div className="text-xs text-gray-500 mt-0.5">Grid Savings</div>
              </div>
            </div>
          ) : (
            <div className="text-center text-gray-500 text-sm py-4">
              KPI data not available
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default function ProgramsPage() {
  const [programs, setPrograms] = useState<Program[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedProgram, setSelectedProgram] = useState<Program | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [form, setForm] = useState<CreateProgramForm>({
    name: '',
    type: 'FLEXIBILITY',
    target_mw: '',
    regulatory_basis: '',
    start_date: '',
    end_date: '',
  })
  const [creating, setCreating] = useState(false)

  const loadPrograms = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.programs(statusFilter !== 'ALL' ? statusFilter : undefined)
      setPrograms(res.data || [])
    } catch {
      setPrograms([])
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    loadPrograms()
  }, [loadPrograms])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const res = await api.createProgram({
        ...form,
        target_mw: parseFloat(form.target_mw),
      })
      setPrograms((prev) => [res.data, ...prev])
      setShowCreateModal(false)
    } catch {
      alert('Failed to create program.')
    } finally {
      setCreating(false)
    }
  }

  const activePrograms = programs.filter((p) => p.status === 'ACTIVE')
  const draftPrograms = programs.filter((p) => p.status === 'DRAFT')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Flexibility Programs</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {activePrograms.length} active · {draftPrograms.length} draft
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="select text-sm"
          >
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="DRAFT">Draft</option>
            <option value="COMPLETED">Completed</option>
            <option value="SUSPENDED">Suspended</option>
          </select>
          <button onClick={loadPrograms} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            New Program
          </button>
        </div>
      </div>

      {/* Summary cards */}
      {!loading && programs.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <div className="card text-center">
            <div className="text-2xl font-bold text-indigo-400">{programs.length}</div>
            <div className="text-xs text-gray-400 mt-1">Total Programs</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold text-green-400">
              {programs.reduce((s, p) => s + (p.enrolled_mw || 0), 0).toFixed(1)}
            </div>
            <div className="text-xs text-gray-400 mt-1">Total Enrolled MW</div>
          </div>
          <div className="card text-center">
            <div className="text-2xl font-bold text-amber-400">
              {programs.reduce((s, p) => s + (p.target_mw || 0), 0).toFixed(1)}
            </div>
            <div className="text-xs text-gray-400 mt-1">Total Target MW</div>
          </div>
        </div>
      )}

      {/* Program cards grid */}
      {loading ? (
        <LoadingSpinner fullPage label="Loading programs..." />
      ) : programs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <FileText className="w-12 h-12 mb-4 opacity-40" />
          <p className="text-lg font-medium">No programs found</p>
          <p className="text-sm mt-1">Create your first flexibility program to get started</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary mt-4 flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Program
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {programs.map((program) => (
            <ProgramCard
              key={program.id}
              program={program}
              onClick={() => setSelectedProgram(program)}
            />
          ))}
        </div>
      )}

      {/* Program detail modal */}
      {selectedProgram && (
        <ProgramDetailModal
          program={selectedProgram}
          onClose={() => setSelectedProgram(null)}
        />
      )}

      {/* Create Program Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Flexibility Program"
        size="md"
        footer={
          <>
            <button onClick={() => setShowCreateModal(false)} className="btn-secondary">Cancel</button>
            <button
              onClick={handleCreate}
              disabled={creating || !form.name || !form.target_mw}
              className="btn-primary flex items-center gap-2"
            >
              {creating ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Target className="w-4 h-4" />
              )}
              Create Program
            </button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Program Name *</label>
            <input
              className="input w-full"
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="e.g. SSEN Shetland Flexibility 2026"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Program Type</label>
              <select
                className="select w-full"
                value={form.type}
                onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}
              >
                <option value="FLEXIBILITY">Flexibility</option>
                <option value="DEMAND_RESPONSE">Demand Response</option>
                <option value="PEAK_SHAVING">Peak Shaving</option>
                <option value="FREQUENCY_RESPONSE">Frequency Response</option>
                <option value="VOLTAGE_SUPPORT">Voltage Support</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Target (MW) *</label>
              <input
                className="input w-full"
                type="number"
                step="0.1"
                min="0.1"
                value={form.target_mw}
                onChange={(e) => setForm((p) => ({ ...p, target_mw: e.target.value }))}
                placeholder="5.0"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Start Date</label>
              <input
                className="input w-full"
                type="date"
                value={form.start_date}
                onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">End Date</label>
              <input
                className="input w-full"
                type="date"
                value={form.end_date}
                onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Regulatory Basis</label>
            <input
              className="input w-full"
              value={form.regulatory_basis}
              onChange={(e) => setForm((p) => ({ ...p, regulatory_basis: e.target.value }))}
              placeholder="e.g. ENA-CPP-2024 SLC 31E"
            />
          </div>
        </form>
      </Modal>
    </div>
  )
}
