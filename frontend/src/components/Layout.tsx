import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { useGridStore } from '../stores/gridStore'
import {
  LayoutDashboard,
  Zap,
  FileText,
  Users,
  Radio,
  BarChart3,
  TrendingUp,
  Shield,
  LogOut,
  Bell,
  Cpu,
  DollarSign,
  Settings,
  Network,
  ServerCog,
  BookOpen,
} from 'lucide-react'
import clsx from 'clsx'

// roles: DEPLOY_ADMIN > OPERATOR > AGGREGATOR
// Each item has an optional `roles` allowlist; omit = visible to all roles
const NAV_ITEMS: {
  path: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  roles?: string[]
}[] = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/grid', label: 'Grid & Assets', icon: Zap },
  { path: '/dispatch', label: 'Flex Dispatch', icon: Radio },
  { path: '/programs', label: 'Programs', icon: FileText, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/contracts', label: 'Contracts', icon: Shield, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/counterparties', label: 'Counterparties', icon: Users, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/settlement', label: 'Settlement', icon: DollarSign, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/forecasting', label: 'Forecasting', icon: TrendingUp, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/optimization', label: 'Optimization', icon: Cpu, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/reports', label: 'Reports', icon: BarChart3, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/integrations', label: 'Integrations & OE', icon: Network },
  { path: '/scada', label: 'SCADA Gateway', icon: ServerCog, roles: ['OPERATOR', 'DEPLOY_ADMIN'] },
  { path: '/admin', label: 'Admin', icon: Settings, roles: ['DEPLOY_ADMIN'] },
  { path: '/glossary', label: 'Glossary & Docs', icon: BookOpen },
]

const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  DEPLOY_ADMIN: { label: 'Admin', color: 'text-purple-400' },
  OPERATOR:     { label: 'Operator', color: 'text-blue-400' },
  AGGREGATOR:   { label: 'Aggregator', color: 'text-green-400' },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, currentDeployment, deployments, setDeployment, logout } = useAuthStore()
  const { alerts, wsConnected } = useGridStore()
  const navigate = useNavigate()

  const unacknowledgedAlerts = alerts.filter((a) => !a.is_acknowledged)
  const criticalAlerts = unacknowledgedAlerts.filter((a) => a.severity === 'CRITICAL')
  const currentDep = deployments.find((d) => d.slug === currentDeployment)
  const isSSEN = currentDeployment === 'ssen'

  // Resolve current user role for this deployment
  const currentRole: string = (() => {
    if (user?.is_superuser) return 'DEPLOY_ADMIN'
    const match = user?.deployments?.find((ud) => ud.deployment_id === currentDep?.id)
    return match?.role ?? 'OPERATOR'
  })()

  const visibleNav = NAV_ITEMS.filter(
    (item) => !item.roles || item.roles.includes(currentRole)
  )
  const roleInfo = ROLE_LABELS[currentRole] ?? { label: currentRole, color: 'text-gray-400' }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center flex-shrink-0">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <div>
              <div className="text-sm font-bold text-white">Neural Grid</div>
              <div className="text-xs text-gray-400">L&T Digital Energy Solutions</div>
            </div>
          </div>
        </div>

        {/* Deployment Selector */}
        <div className="p-3 border-b border-gray-800">
          <select
            value={currentDeployment}
            onChange={(e) => setDeployment(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 text-gray-100 px-3 py-2 rounded-lg text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
          >
            {deployments.length > 0 ? (
              deployments.map((d) => (
                <option key={d.slug} value={d.slug}>
                  {d.name}
                </option>
              ))
            ) : (
              <>
                <option value="ssen">SSEN — Scotland</option>
                <option value="puvvnl">PUVVNL — Varanasi</option>
              </>
            )}
          </select>
          <div
            className={clsx(
              'mt-2 flex items-center gap-1.5 text-xs',
              isSSEN ? 'text-blue-400' : 'text-amber-400'
            )}
          >
            <div
              className={clsx(
                'w-1.5 h-1.5 rounded-full',
                isSSEN ? 'bg-blue-400' : 'bg-amber-400'
              )}
            />
            {isSSEN ? 'ENA-CPP-2024 / RIIO-ED2' : 'UPERC-DR-2025'}
          </div>
        </div>

        {/* Nav Items */}
        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {visibleNav.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800'
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="flex-1">{label}</span>
              {path === '/dispatch' && unacknowledgedAlerts.length > 0 && (
                <span className="bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center font-bold">
                  {unacknowledgedAlerts.length > 9 ? '9+' : unacknowledgedAlerts.length}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User footer */}
        <div className="p-3 border-t border-gray-800">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 bg-indigo-600 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
              {user?.full_name?.[0]?.toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-gray-200 truncate">
                {user?.full_name || 'User'}
              </div>
              <div className="text-xs text-gray-500 truncate">{user?.email}</div>
              <div className={`text-xs font-medium ${roleInfo.color}`}>{roleInfo.label}</div>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div
              className={clsx(
                'flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full',
                wsConnected
                  ? 'bg-green-900/50 text-green-400'
                  : 'bg-red-900/50 text-red-400'
              )}
            >
              <div
                className={clsx(
                  'w-1.5 h-1.5 rounded-full',
                  wsConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'
                )}
              />
              {wsConnected ? 'Live' : 'Reconnecting...'}
            </div>
            <span className="text-sm text-gray-400">
              {currentDep?.name || (isSSEN ? 'SSEN Network' : 'PUVVNL Network')}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {criticalAlerts.length > 0 && (
              <div className="flex items-center gap-1.5 bg-red-900/50 text-red-400 px-3 py-1 rounded-full text-xs border border-red-800/50">
                <Bell className="w-3.5 h-3.5 animate-pulse" />
                {criticalAlerts.length} Critical Alert{criticalAlerts.length > 1 ? 's' : ''}
              </div>
            )}
            <div className="text-xs text-gray-500 font-mono">
              {new Date().toLocaleTimeString('en-GB', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              })}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6 bg-gray-950">
          {children}
        </main>
      </div>
    </div>
  )
}
