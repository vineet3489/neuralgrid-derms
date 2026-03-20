import React, { useEffect, useState } from 'react'
import {
  Settings, Users, Shield, Activity, RefreshCw,
  Plus, CheckCircle, AlertCircle, Clock, Server,
} from 'lucide-react'
import { format, formatDistanceToNow } from 'date-fns'
import { api } from '../api/client'
import { useAuthStore } from '../stores/authStore'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import LoadingSpinner from '../components/ui/LoadingSpinner'
import type { AuditLog, SystemHealth } from '../types'

type AdminTab = 'users' | 'config' | 'audit' | 'health'

interface UserRecord {
  id: string
  email: string
  full_name: string
  is_active: boolean
  is_superuser: boolean
  deployments: Array<{ deployment_id: string; role: string }>
}

interface ConfigEntry {
  key: string
  value: string
  description?: string
  editable: boolean
}

function HealthStatusIcon({ status }: { status: string }) {
  if (status === 'healthy') return <CheckCircle className="w-5 h-5 text-green-400" />
  if (status === 'degraded') return <AlertCircle className="w-5 h-5 text-amber-400" />
  return <AlertCircle className="w-5 h-5 text-red-400" />
}

export default function AdminPage() {
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<AdminTab>('health')
  const [users, setUsers] = useState<UserRecord[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [config, setConfig] = useState<ConfigEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [inviteForm, setInviteForm] = useState({ email: '', full_name: '', role: 'OPERATOR' })
  const [inviting, setInviting] = useState(false)
  const [editingConfig, setEditingConfig] = useState<string | null>(null)
  const [configEdit, setConfigEdit] = useState('')

  const loadTabData = async (tab: AdminTab) => {
    setLoading(true)
    try {
      switch (tab) {
        case 'users': {
          const res = await api.users()
          setUsers(res.data || [])
          break
        }
        case 'audit': {
          const res = await api.auditLogs()
          setAuditLogs(res.data || [])
          break
        }
        case 'health': {
          const res = await api.systemHealth()
          setHealth(res.data)
          break
        }
        case 'config': {
          const res = await api.deploymentConfig()
          setConfig(res.data || [])
          break
        }
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTabData(activeTab)
  }, [activeTab])

  // Auto-refresh health every 30s
  useEffect(() => {
    if (activeTab !== 'health') return
    const interval = setInterval(() => loadTabData('health'), 30000)
    return () => clearInterval(interval)
  }, [activeTab])

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setInviting(true)
    try {
      const res = await api.inviteUser(inviteForm)
      setUsers((prev) => [res.data, ...prev])
      setShowInviteModal(false)
      setInviteForm({ email: '', full_name: '', role: 'OPERATOR' })
    } catch {
      alert('Failed to invite user.')
    } finally {
      setInviting(false)
    }
  }

  const handleSaveConfig = async (key: string) => {
    try {
      await api.updateConfig({ key, value: configEdit })
      setConfig((prev) => prev.map((c) => (c.key === key ? { ...c, value: configEdit } : c)))
      setEditingConfig(null)
    } catch {
      alert('Failed to update configuration.')
    }
  }

  const isAdmin = user?.is_superuser

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-header">Administration</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            System configuration, user management & audit logs
          </p>
        </div>
        <button
          onClick={() => loadTabData(activeTab)}
          className="btn-secondary flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {([
          { id: 'health', label: 'System Health', icon: Activity },
          { id: 'users', label: 'Users', icon: Users },
          { id: 'config', label: 'Configuration', icon: Settings },
          { id: 'audit', label: 'Audit Log', icon: Shield },
        ] as { id: AdminTab; label: string; icon: React.ComponentType<{ className?: string }> }[]).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={activeTab === id ? 'tab-active flex items-center gap-1.5' : 'tab-inactive flex items-center gap-1.5'}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingSpinner fullPage label="Loading..." />
      ) : (
        <>
          {/* System Health */}
          {activeTab === 'health' && (
            <div className="space-y-4">
              {health ? (
                <>
                  <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                    {[
                      { label: 'Database', key: 'database', icon: Server },
                      { label: 'Simulation Engine', key: 'simulation_engine', icon: Activity },
                      { label: 'API Server', key: 'api_server', icon: Server },
                      { label: 'WebSocket', key: 'websocket', icon: Activity },
                    ].map(({ label, key, icon: Icon }) => {
                      const status = (health as unknown as Record<string, string>)[key] || 'unknown'
                      return (
                        <div
                          key={key}
                          className={`card border ${
                            status === 'healthy'
                              ? 'border-green-700/30 bg-green-900/10'
                              : status === 'degraded'
                              ? 'border-amber-700/30 bg-amber-900/10'
                              : 'border-red-700/30 bg-red-900/10'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <Icon className="w-5 h-5 text-gray-400" />
                            <HealthStatusIcon status={status} />
                          </div>
                          <div className="text-sm font-medium text-gray-200">{label}</div>
                          <div
                            className={`text-xs mt-1 capitalize font-medium ${
                              status === 'healthy'
                                ? 'text-green-400'
                                : status === 'degraded'
                                ? 'text-amber-400'
                                : 'text-red-400'
                            }`}
                          >
                            {status}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  <div className="card">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-gray-400">System Uptime</div>
                      <div className="text-sm font-medium text-gray-200">
                        {health.uptime_seconds
                          ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m`
                          : '—'}
                      </div>
                    </div>
                    {health.last_checked && (
                      <div className="flex items-center gap-1.5 mt-2 text-xs text-gray-500">
                        <Clock className="w-3.5 h-3.5" />
                        Last checked {formatDistanceToNow(new Date(health.last_checked), { addSuffix: true })}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="card text-center py-12">
                  <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
                  <p className="text-gray-400">Health check data unavailable</p>
                  <p className="text-sm text-gray-500 mt-1">Ensure the backend is running</p>
                </div>
              )}
            </div>
          )}

          {/* Users */}
          {activeTab === 'users' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button
                  onClick={() => setShowInviteModal(true)}
                  disabled={!isAdmin}
                  className="btn-primary flex items-center gap-2 disabled:opacity-50"
                >
                  <Plus className="w-4 h-4" />
                  Invite User
                </button>
              </div>
              <div className="card p-0">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-gray-800/50">
                        <th className="table-header text-left">Name</th>
                        <th className="table-header text-left">Email</th>
                        <th className="table-header text-left">Role</th>
                        <th className="table-header text-left">Status</th>
                        <th className="table-header text-left">Deployments</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="text-center py-12 text-gray-500">
                            No users found
                          </td>
                        </tr>
                      ) : (
                        users.map((u) => (
                          <tr key={u.id} className="table-row">
                            <td className="table-cell font-medium text-gray-200">
                              <div className="flex items-center gap-2">
                                <div className="w-6 h-6 bg-indigo-600/80 rounded-full flex items-center justify-center text-xs font-bold text-white">
                                  {u.full_name?.[0]?.toUpperCase() || 'U'}
                                </div>
                                {u.full_name}
                              </div>
                            </td>
                            <td className="table-cell text-gray-400">{u.email}</td>
                            <td className="table-cell">
                              <span className={u.is_superuser ? 'badge-warning' : 'badge-info'}>
                                {u.is_superuser ? 'Super Admin' : 'Operator'}
                              </span>
                            </td>
                            <td className="table-cell">
                              <StatusBadge status={u.is_active ? 'ACTIVE' : 'INACTIVE'} />
                            </td>
                            <td className="table-cell text-xs text-gray-500">
                              {u.deployments?.length || 0} deployment{u.deployments?.length !== 1 ? 's' : ''}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Configuration */}
          {activeTab === 'config' && (
            <div className="card p-0">
              <div className="p-4 border-b border-gray-700">
                <h2 className="text-sm font-semibold text-gray-200">Deployment Configuration</h2>
              </div>
              {config.length === 0 ? (
                <div className="text-center py-12 text-gray-500">No configuration data available</div>
              ) : (
                <div className="divide-y divide-gray-700">
                  {config.map((entry) => (
                    <div key={entry.key} className="p-4 flex items-start gap-4">
                      <div className="flex-1">
                        <div className="text-xs font-mono text-indigo-400">{entry.key}</div>
                        {entry.description && (
                          <div className="text-xs text-gray-500 mt-0.5">{entry.description}</div>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {editingConfig === entry.key ? (
                          <>
                            <input
                              className="input text-xs py-1.5 px-2 w-48"
                              value={configEdit}
                              onChange={(e) => setConfigEdit(e.target.value)}
                              autoFocus
                            />
                            <button
                              onClick={() => handleSaveConfig(entry.key)}
                              className="btn-primary text-xs py-1.5 px-2.5"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingConfig(null)}
                              className="btn-secondary text-xs py-1.5 px-2.5"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <span className="text-sm text-gray-200 font-mono">{entry.value}</span>
                            {entry.editable && isAdmin && (
                              <button
                                onClick={() => { setEditingConfig(entry.key); setConfigEdit(entry.value) }}
                                className="text-xs text-indigo-400 hover:text-indigo-300"
                              >
                                Edit
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Audit Log */}
          {activeTab === 'audit' && (
            <div className="card p-0">
              <div className="flex items-center justify-between p-4 border-b border-gray-700">
                <h2 className="text-sm font-semibold text-gray-200">Audit Log</h2>
                <span className="text-xs text-gray-500">{auditLogs.length} entries</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="table-header text-left">Timestamp</th>
                      <th className="table-header text-left">User</th>
                      <th className="table-header text-left">Action</th>
                      <th className="table-header text-left">Resource</th>
                      <th className="table-header text-left">Details</th>
                      <th className="table-header text-left">IP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="text-center py-12 text-gray-500">
                          No audit log entries found
                        </td>
                      </tr>
                    ) : (
                      auditLogs.map((log) => (
                        <tr key={log.id} className="table-row">
                          <td className="table-cell text-xs text-gray-400 font-mono">
                            {format(new Date(log.created_at), 'dd MMM HH:mm:ss')}
                          </td>
                          <td className="table-cell text-xs text-gray-300">
                            {log.user_email}
                          </td>
                          <td className="table-cell">
                            <span className={`text-xs font-medium font-mono ${
                              log.action.includes('DELETE') ? 'text-red-400' :
                              log.action.includes('CREATE') ? 'text-green-400' :
                              log.action.includes('UPDATE') ? 'text-amber-400' : 'text-gray-400'
                            }`}>
                              {log.action}
                            </span>
                          </td>
                          <td className="table-cell text-xs text-gray-400">
                            <div>{log.resource_type}</div>
                            <div className="font-mono text-gray-600">{log.resource_id?.slice(0, 8)}...</div>
                          </td>
                          <td className="table-cell text-xs text-gray-500 max-w-xs truncate">
                            {log.details}
                          </td>
                          <td className="table-cell text-xs font-mono text-gray-500">
                            {log.ip_address || '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Invite User Modal */}
      <Modal
        isOpen={showInviteModal}
        onClose={() => setShowInviteModal(false)}
        title="Invite User"
        size="sm"
        footer={
          <>
            <button onClick={() => setShowInviteModal(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleInvite} disabled={inviting || !inviteForm.email}
              className="btn-primary flex items-center gap-2">
              {inviting ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              Send Invite
            </button>
          </>
        }
      >
        <form onSubmit={handleInvite} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Full Name</label>
            <input className="input w-full" value={inviteForm.full_name}
              onChange={(e) => setInviteForm((p) => ({ ...p, full_name: e.target.value }))}
              placeholder="Jane Smith" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Email *</label>
            <input className="input w-full" type="email" value={inviteForm.email}
              onChange={(e) => setInviteForm((p) => ({ ...p, email: e.target.value }))}
              placeholder="jane@example.com" required />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Role</label>
            <select className="select w-full" value={inviteForm.role}
              onChange={(e) => setInviteForm((p) => ({ ...p, role: e.target.value }))}>
              <option value="VIEWER">Viewer</option>
              <option value="OPERATOR">Operator</option>
              <option value="DEPLOY_ADMIN">Deployment Admin</option>
            </select>
          </div>
        </form>
      </Modal>
    </div>
  )
}
