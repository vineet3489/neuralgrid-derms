import React from 'react'
import clsx from 'clsx'
import { AlertTriangle, AlertCircle, Info, X, CheckCircle } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import type { GridAlert } from '../../types'

interface AlertBannerProps {
  alert: GridAlert
  onAcknowledge?: (id: string) => void
  compact?: boolean
}

const severityConfig = {
  CRITICAL: {
    bg: 'bg-red-900/30 border-red-700/50',
    text: 'text-red-300',
    icon: AlertCircle,
    iconColor: 'text-red-400',
    dot: 'bg-red-400',
  },
  WARNING: {
    bg: 'bg-amber-900/30 border-amber-700/50',
    text: 'text-amber-300',
    icon: AlertTriangle,
    iconColor: 'text-amber-400',
    dot: 'bg-amber-400',
  },
  INFO: {
    bg: 'bg-blue-900/30 border-blue-700/50',
    text: 'text-blue-300',
    icon: Info,
    iconColor: 'text-blue-400',
    dot: 'bg-blue-400',
  },
}

export default function AlertBanner({ alert, onAcknowledge, compact = false }: AlertBannerProps) {
  const config = severityConfig[alert.severity] || severityConfig.INFO
  const Icon = config.icon

  if (compact) {
    return (
      <div
        className={clsx(
          'flex items-start gap-2 p-2.5 rounded-lg border text-xs',
          config.bg,
          alert.is_acknowledged && 'opacity-50'
        )}
      >
        <div className={clsx('w-1.5 h-1.5 rounded-full mt-0.5 flex-shrink-0', config.dot)} />
        <div className="flex-1 min-w-0">
          <span className={clsx('font-medium', config.text)}>{alert.severity}</span>
          <span className="text-gray-400 ml-1">{alert.message}</span>
        </div>
        {!alert.is_acknowledged && onAcknowledge && (
          <button
            onClick={(e) => { e.stopPropagation(); onAcknowledge(alert.id) }}
            className="text-gray-500 hover:text-gray-300 flex-shrink-0"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    )
  }

  return (
    <div
      className={clsx(
        'flex items-start gap-3 p-3 rounded-lg border transition-opacity',
        config.bg,
        alert.is_acknowledged && 'opacity-50'
      )}
    >
      <Icon className={clsx('w-4 h-4 flex-shrink-0 mt-0.5', config.iconColor)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className={clsx('text-xs font-semibold uppercase tracking-wide', config.text)}>
            {alert.severity}
          </span>
          <span className="text-xs text-gray-500">
            {alert.alert_type?.replace(/_/g, ' ')}
          </span>
        </div>
        <p className="text-sm text-gray-300">{alert.message}</p>
        <div className="flex items-center gap-3 mt-1">
          <span className="text-xs text-gray-500">
            {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
          </span>
          {alert.is_acknowledged && (
            <span className="flex items-center gap-1 text-xs text-green-500">
              <CheckCircle className="w-3 h-3" /> Acknowledged
            </span>
          )}
        </div>
      </div>
      {!alert.is_acknowledged && onAcknowledge && (
        <button
          onClick={() => onAcknowledge(alert.id)}
          className="text-gray-500 hover:text-gray-200 transition-colors flex-shrink-0"
          title="Acknowledge"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
