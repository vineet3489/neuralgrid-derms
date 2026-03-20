import React from 'react'
import clsx from 'clsx'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface StatCardProps {
  title: string
  value: string | number
  unit?: string
  icon: React.ReactNode
  trend?: 'up' | 'down' | 'stable'
  trendValue?: string
  color?: 'green' | 'amber' | 'red' | 'blue' | 'indigo'
  subtitle?: string
  onClick?: () => void
}

const colorMap = {
  green: {
    icon: 'bg-green-900/50 text-green-400',
    value: 'text-green-400',
    trend: 'text-green-400',
  },
  amber: {
    icon: 'bg-amber-900/50 text-amber-400',
    value: 'text-amber-400',
    trend: 'text-amber-400',
  },
  red: {
    icon: 'bg-red-900/50 text-red-400',
    value: 'text-red-400',
    trend: 'text-red-400',
  },
  blue: {
    icon: 'bg-blue-900/50 text-blue-400',
    value: 'text-blue-400',
    trend: 'text-blue-400',
  },
  indigo: {
    icon: 'bg-indigo-900/50 text-indigo-400',
    value: 'text-indigo-400',
    trend: 'text-indigo-400',
  },
}

export default function StatCard({
  title,
  value,
  unit,
  icon,
  trend,
  trendValue,
  color = 'indigo',
  subtitle,
  onClick,
}: StatCardProps) {
  const colors = colorMap[color]

  return (
    <div
      className={clsx(
        'card flex flex-col gap-3 transition-all duration-200',
        onClick && 'cursor-pointer hover:border-indigo-600/50 hover:shadow-lg hover:shadow-indigo-900/20'
      )}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div className={clsx('p-2 rounded-lg', colors.icon)}>
          {icon}
        </div>
        {trend && trendValue && (
          <div className={clsx('flex items-center gap-1 text-xs', colors.trend)}>
            {trend === 'up' && <TrendingUp className="w-3.5 h-3.5" />}
            {trend === 'down' && <TrendingDown className="w-3.5 h-3.5" />}
            {trend === 'stable' && <Minus className="w-3.5 h-3.5" />}
            {trendValue}
          </div>
        )}
      </div>
      <div>
        <div className="flex items-baseline gap-1.5">
          <span className={clsx('text-2xl font-bold', colors.value)}>
            {typeof value === 'number' ? value.toLocaleString() : value}
          </span>
          {unit && (
            <span className="text-sm text-gray-400 font-medium">{unit}</span>
          )}
        </div>
        <div className="text-sm text-gray-400 mt-0.5">{title}</div>
        {subtitle && (
          <div className="text-xs text-gray-500 mt-0.5">{subtitle}</div>
        )}
      </div>
    </div>
  )
}
