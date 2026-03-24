import React, { useEffect, useState, useCallback } from 'react'
import {
  Plus,
  Radio,
  Clock,
  Target,
  CheckCircle2,
  XCircle,
  Cpu,
  RefreshCw,
  ChevronRight,
  AlertTriangle,
  Zap,
} from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'
import { api } from '../api/client'
import { useGridStore } from '../stores/gridStore'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { FlexEvent } from '../types'

interface CreateEventForm {
  event_type: string
  target_kw: string
  duration_minutes: string
  cmz_id: string
  notes: string
}

interface EventDetailPanelProps {
  event: FlexEvent
  onClose: () => void
  onDispatch: (id: string) => void
  onCancel: (id: string) => void
}

function EventDetailPanel({ event, onClose, onDispatch, onCancel }: EventDetailPanelProps) {
  const [aiInsight, setAiInsight] = useState<string>('')
  const [loadingAI, setLoadingAI] = useState(false)

  const deliveryPct =
    event.target_kw > 0 && event.delivered_kw != null
      ? ((event.delivered_kw / event.target_kw) * 100).toFixed(1)
      : null

  const dispatchPct =
    event.target_kw > 0
      ? ((event.dispatched_kw / event.target_kw) * 100).toFixed(1)
      : '0'

  const getAIInsight = async () => {
    setLoadingAI(true)
    try {
      const res = await api.optimizationRecommendations()
      setAiInsight(res.data?.recommendation || res.data?.message || 'No recommendation available.')
    } catch {
      setAiInsight('Could not load AI recommendation. Ensure backend is running.')
    } finally {
      setLoadingAI(false)
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 w-[420px] bg-gray-900 border-l border-gray-700 shadow-2xl z-40 flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div>
          <h3 className="text-sm font-semibold text-gray-100">{event.event_ref}</h3>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={event.status} />
            <span className="text-xs text-gray-500">{event.event_type?.replace(/_/g, ' ')}</span>
          </div>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-200">
          <XCircle className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Key metrics */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-800 rounded-lg p-3">
            <div className="text-xs text-gray-500">Target</div>
            <div className="text-lg font-bold text-white">{event.target_kw?.toFixed(0)}</div>
            <div className="text-xs text-gray-500">kW</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-3">
            <div className="text-xs text-gray-500">Dispatched</div>
            <div className="text-lg font-bold text-indigo-400">{event.dispatched_kw?.toFixed(0)}</div>
            <div className="text-xs text-gray-500">kW ({dispatchPct}%)</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-3">
            <div className="text-xs text-gray-500">Delivered</div>
            <div className="text-lg font-bold text-green-400">
              {event.delivered_kw?.toFixed(0) ?? '—'}
            </div>
            <div className="text-xs text-gray-500">
              kW{deliveryPct ? ` (${deliveryPct}%)` : ''}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        {event.status === 'IN_PROGRESS' && (
          <div>
            <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
              <span>Dispatch Progress</span>
              <span>{dispatchPct}%</span>
            </div>
            <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all"
                style={{ width: `${Math.min(parseFloat(dispatchPct), 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Timeline */}
        <div className="space-y-2">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">Timeline</div>
          <div className="space-y-2">
            {[
              { label: 'Created', time: event.start_time, icon: Clock },
              { label: 'Start Time', time: event.start_time, icon: Radio },
              ...(event.end_time ? [{ label: 'End Time', time: event.end_time, icon: CheckCircle2 }] : []),
            ].map(({ label, time, icon: Icon }) => (
              <div key={label} className="flex items-center gap-3">
                <div className="w-6 h-6 bg-gray-800 rounded-full flex items-center justify-center flex-shrink-0">
                  <Icon className="w-3 h-3 text-indigo-400" />
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-300">{label}</div>
                  <div className="text-xs text-gray-500">
                    {format(new Date(time), 'dd MMM yyyy HH:mm')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Details */}
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: 'Duration', value: `${event.duration_minutes} min` },
            { label: 'CMZ', value: event.cmz_id },
            { label: 'Trigger', value: event.trigger },
            { label: 'Auto-generated', value: event.auto_generated ? 'Yes' : 'No' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-gray-800/50 rounded-lg p-2.5">
              <div className="text-xs text-gray-500">{label}</div>
              <div className="text-sm text-gray-200 mt-0.5">{value}</div>
            </div>
          ))}
        </div>

        {/* Notes */}
        {event.notes && (
          <div className="bg-gray-800/50 rounded-lg p-3">
            <div className="text-xs text-gray-500 mb-1">Notes</div>
            <p className="text-sm text-gray-300">{event.notes}</p>
          </div>
        )}

        {/* AI Insight */}
        <div className="bg-indigo-900/20 border border-indigo-800/30 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span className="text-xs font-medium text-indigo-300">AI Recommendation</span>
            </div>
            <button
              onClick={getAIInsight}
              disabled={loadingAI}
              className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
            >
              {loadingAI ? (
                <div className="w-3 h-3 border border-indigo-400/50 border-t-indigo-400 rounded-full animate-spin" />
              ) : (
                <RefreshCw className="w-3 h-3" />
              )}
              Get Insight
            </button>
          </div>
          {aiInsight ? (
            <p className="text-xs text-gray-300 leading-relaxed">{aiInsight}</p>
          ) : (
            <p className="text-xs text-gray-500">Click "Get Insight" for AI-powered analysis.</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          {event.status === 'SCHEDULED' && (
            <button
              onClick={() => onDispatch(event.id)}
              className="btn-primary flex items-center gap-2 flex-1 justify-center"
            >
              <Radio className="w-4 h-4" />
              Dispatch Now
            </button>
          )}
          {['SCHEDULED', 'DISPATCHED', 'IN_PROGRESS'].includes(event.status) && (
            <button
              onClick={() => onCancel(event.id)}
              className="btn-danger flex items-center gap-2 flex-1 justify-center"
            >
              <XCircle className="w-4 h-4" />
              Cancel Event
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function DispatchPage() {
  const { alerts } = useGridStore()
  const [events, setEvents] = useState<FlexEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedEvent, setSelectedEvent] = useState<FlexEvent | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createForm, setCreateForm] = useState<CreateEventForm>({
    event_type: 'CURTAILMENT',
    target_kw: '',
    duration_minutes: '30',
    cmz_id: '',
    notes: '',
  })
  const [creating, setCreating] = useState(false)
  const [dispatching, setDispatching] = useState<string | null>(null)

  const loadEvents = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.events()
      setEvents(res.data || [])
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadEvents()
    const interval = setInterval(loadEvents, 15000)
    return () => clearInterval(interval)
  }, [loadEvents])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const res = await api.createEvent({
        ...createForm,
        target_kw: parseFloat(createForm.target_kw),
        duration_minutes: parseInt(createForm.duration_minutes),
      })
      setEvents((prev) => [res.data, ...prev])
      setShowCreateModal(false)
      setCreateForm({ event_type: 'CURTAILMENT', target_kw: '', duration_minutes: '30', cmz_id: '', notes: '' })
    } catch {
      alert('Failed to create event.')
    } finally {
      setCreating(false)
    }
  }

  const handleDispatch = async (id: string) => {
    setDispatching(id)
    try {
      const res = await api.dispatchEvent(id)
      setEvents((prev) => prev.map((e) => (e.id === id ? { ...e, ...res.data } : e)))
      if (selectedEvent?.id === id) setSelectedEvent(res.data)
    } catch {
      alert('Failed to dispatch event.')
    } finally {
      setDispatching(null)
    }
  }

  const handleCancel = async (id: string) => {
    if (!window.confirm('Cancel this flex event?')) return
    try {
      await api.cancelEvent(id)
      setEvents((prev) =>
        prev.map((e) => (e.id === id ? { ...e, status: 'CANCELLED' } : e))
      )
      if (selectedEvent?.id === id) setSelectedEvent(null)
    } catch {
      alert('Failed to cancel event.')
    }
  }

  const activeEvents = events.filter((e) =>
    ['IN_PROGRESS', 'DISPATCHED'].includes(e.status)
  )
  const scheduledEvents = events.filter((e) => e.status === 'SCHEDULED')
  const pastEvents = events.filter((e) =>
    ['COMPLETED', 'CANCELLED', 'FAILED'].includes(e.status)
  )

  const criticalAlerts = alerts.filter((a) => a.severity === 'CRITICAL' && !a.is_acknowledged)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Flex Dispatch</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {activeEvents.length} active · {scheduledEvents.length} scheduled
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={loadEvents} className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button onClick={() => setShowCreateModal(true)} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Create Event
          </button>
        </div>
      </div>

      {/* Critical alerts banner */}
      {criticalAlerts.length > 0 && (
        <div className="flex items-center gap-3 bg-red-900/30 border border-red-800/50 rounded-lg p-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <div>
            <span className="text-sm font-medium text-red-300">
              {criticalAlerts.length} Critical Alert{criticalAlerts.length > 1 ? 's' : ''}
            </span>
            <p className="text-xs text-red-400 mt-0.5">
              {criticalAlerts[0]?.message}
              {criticalAlerts.length > 1 ? ` +${criticalAlerts.length - 1} more` : ''}
            </p>
          </div>
        </div>
      )}

      {/* Active Events */}
      {activeEvents.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            Active Events
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {activeEvents.map((event) => {
              const dispatchPct =
                event.target_kw > 0
                  ? Math.min((event.dispatched_kw / event.target_kw) * 100, 100)
                  : 0
              const deliveryPct =
                event.target_kw > 0 && event.delivered_kw != null
                  ? Math.min((event.delivered_kw / event.target_kw) * 100, 100)
                  : null

              return (
                <div
                  key={event.id}
                  className="card border-green-700/30 bg-green-900/10 cursor-pointer hover:border-green-600/50 transition-colors"
                  onClick={() => setSelectedEvent(event)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="text-sm font-semibold text-gray-100">{event.event_ref}</div>
                      <div className="text-xs text-gray-400 mt-0.5">
                        {event.event_type?.replace(/_/g, ' ')}
                      </div>
                    </div>
                    <StatusBadge status={event.status} />
                  </div>

                  <div className="grid grid-cols-3 gap-2 mb-3">
                    <div className="text-center">
                      <div className="text-xs text-gray-500">Target</div>
                      <div className="text-base font-bold text-white">{event.target_kw?.toFixed(0)}</div>
                      <div className="text-xs text-gray-500">kW</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs text-gray-500">Dispatched</div>
                      <div className="text-base font-bold text-indigo-400">{event.dispatched_kw?.toFixed(0)}</div>
                      <div className="text-xs text-gray-500">kW</div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs text-gray-500">Delivered</div>
                      <div className="text-base font-bold text-green-400">
                        {event.delivered_kw?.toFixed(0) ?? '—'}
                      </div>
                      <div className="text-xs text-gray-500">kW</div>
                    </div>
                  </div>

                  {/* Progress */}
                  <div className="space-y-1.5">
                    <div>
                      <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                        <span>Dispatch</span>
                        <span>{dispatchPct.toFixed(0)}%</span>
                      </div>
                      <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{ width: `${dispatchPct}%` }}
                        />
                      </div>
                    </div>
                    {deliveryPct != null && (
                      <div>
                        <div className="flex justify-between text-xs text-gray-500 mb-0.5">
                          <span>Delivery</span>
                          <span>{deliveryPct.toFixed(0)}%</span>
                        </div>
                        <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-green-500 rounded-full"
                            style={{ width: `${deliveryPct}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {event.duration_minutes}min · {event.cmz_id}
                    </span>
                    <span>
                      {formatDistanceToNow(new Date(event.start_time), { addSuffix: true })}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Event List Table */}
      <div className="card p-0">
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-sm font-semibold text-gray-200">All Events</h2>
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span>{scheduledEvents.length} scheduled</span>
            <span>·</span>
            <span>{pastEvents.length} completed</span>
          </div>
        </div>

        {loading ? (
          <LoadingSpinner fullPage label="Loading events..." />
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-500">
            <Radio className="w-10 h-10 mb-3 opacity-50" />
            <p>No flex events found</p>
            <p className="text-sm mt-1">Create your first event to begin dispatching</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-800/50">
                  <th className="table-header text-left">Event Ref</th>
                  <th className="table-header text-left">Type</th>
                  <th className="table-header text-left">Status</th>
                  <th className="table-header text-left">CMZ</th>
                  <th className="table-header text-right">Target kW</th>
                  <th className="table-header text-right">Dispatched kW</th>
                  <th className="table-header text-right">Delivered kW</th>
                  <th className="table-header text-left">Start Time</th>
                  <th className="table-header text-left">Duration</th>
                  <th className="table-header text-left">Trigger</th>
                  <th className="table-header" />
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr
                    key={event.id}
                    className="table-row"
                    onClick={() => setSelectedEvent(event)}
                  >
                    <td className="table-cell font-mono text-xs text-indigo-400">
                      {event.event_ref}
                    </td>
                    <td className="table-cell text-xs text-gray-400">
                      {event.event_type?.replace(/_/g, ' ')}
                    </td>
                    <td className="table-cell">
                      <StatusBadge status={event.status} />
                    </td>
                    <td className="table-cell text-gray-400">{event.cmz_id}</td>
                    <td className="table-cell text-right font-mono text-sm text-white">
                      {event.target_kw?.toFixed(0)}
                    </td>
                    <td className="table-cell text-right font-mono text-sm text-indigo-400">
                      {event.dispatched_kw?.toFixed(0)}
                    </td>
                    <td className="table-cell text-right font-mono text-sm">
                      <span className={event.delivered_kw ? 'text-green-400' : 'text-gray-600'}>
                        {event.delivered_kw?.toFixed(0) ?? '—'}
                      </span>
                    </td>
                    <td className="table-cell text-xs text-gray-400">
                      {format(new Date(event.start_time), 'dd MMM HH:mm')}
                    </td>
                    <td className="table-cell text-gray-400">{event.duration_minutes}m</td>
                    <td className="table-cell text-xs text-gray-400">
                      <div className="flex items-center gap-1">
                        {event.auto_generated && (
                          <Zap className="w-3 h-3 text-amber-400" />
                        )}
                        {event.trigger}
                      </div>
                    </td>
                    <td className="table-cell">
                      {event.status === 'SCHEDULED' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDispatch(event.id) }}
                          disabled={dispatching === event.id}
                          className="btn-primary text-xs px-2 py-1 flex items-center gap-1"
                        >
                          {dispatching === event.id ? (
                            <div className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                          ) : (
                            <Radio className="w-3 h-3" />
                          )}
                          Dispatch
                        </button>
                      )}
                      {!['SCHEDULED'].includes(event.status) && (
                        <ChevronRight className="w-4 h-4 text-gray-500" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Event Detail Panel */}
      {selectedEvent && (
        <EventDetailPanel
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
          onDispatch={handleDispatch}
          onCancel={handleCancel}
        />
      )}

      {/* Create Event Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Flex Event"
        size="md"
        footer={
          <>
            <button onClick={() => setShowCreateModal(false)} className="btn-secondary">Cancel</button>
            <button
              onClick={handleCreate}
              disabled={creating || !createForm.target_kw}
              className="btn-primary flex items-center gap-2"
            >
              {creating ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Radio className="w-4 h-4" />
              )}
              Create Event
            </button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Event Type *</label>
              <select
                className="select w-full"
                value={createForm.event_type}
                onChange={(e) => setCreateForm((p) => ({ ...p, event_type: e.target.value }))}
              >
                <option value="CURTAILMENT">Curtailment</option>
                <option value="TURN_UP">Turn Up (DRU)</option>
                <option value="TURN_DOWN">Turn Down (DRD)</option>
                <option value="PEAK_SHAVING">Peak Shaving</option>
                <option value="FREQUENCY_RESPONSE">Frequency Response</option>
                <option value="VOLTAGE_SUPPORT">Voltage Support</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Target (kW) *</label>
              <input
                className="input w-full"
                type="number"
                step="1"
                min="1"
                value={createForm.target_kw}
                onChange={(e) => setCreateForm((p) => ({ ...p, target_kw: e.target.value }))}
                placeholder="500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Duration (minutes)</label>
              <input
                className="input w-full"
                type="number"
                min="5"
                max="480"
                value={createForm.duration_minutes}
                onChange={(e) => setCreateForm((p) => ({ ...p, duration_minutes: e.target.value }))}
                placeholder="30"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">CMZ ID</label>
              <input
                className="input w-full"
                value={createForm.cmz_id}
                onChange={(e) => setCreateForm((p) => ({ ...p, cmz_id: e.target.value }))}
                placeholder="CMZ-LERWICK-01"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Notes</label>
            <textarea
              className="input w-full resize-none"
              rows={3}
              value={createForm.notes}
              onChange={(e) => setCreateForm((p) => ({ ...p, notes: e.target.value }))}
              placeholder="Optional notes about this event..."
            />
          </div>
          <div className="bg-amber-900/20 border border-amber-800/30 rounded-lg p-3 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-amber-300">
              Creating a flex event will schedule dispatch instructions to enrolled assets.
              Confirm target and CMZ are correct before proceeding.
            </p>
          </div>
        </form>
      </Modal>
    </div>
  )
}
