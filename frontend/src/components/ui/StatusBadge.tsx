import React from 'react'
import clsx from 'clsx'

interface StatusBadgeProps {
  status: string
  className?: string
}

function getStatusClass(status: string): string {
  const s = status?.toUpperCase() || ''

  if (
    ['ONLINE', 'ACTIVE', 'APPROVED', 'CONNECTED', 'HEALTHY',
     'PREQUALIFIED', 'PAID', 'DELIVERED'].includes(s)
  ) {
    return 'badge-online'
  }
  if (
    ['OFFLINE', 'TERMINATED', 'REJECTED', 'FAILED',
     'CANCELLED', 'INACTIVE', 'DOWN'].includes(s)
  ) {
    return 'badge-offline'
  }
  if (
    ['WARNING', 'CURTAILED', 'PENDING', 'PENDING_APPROVAL',
     'DISPATCHED', 'IN_PROGRESS', 'PARTIAL', 'DEGRADED'].includes(s)
  ) {
    return 'badge-warning'
  }
  if (
    ['DRAFT', 'PLANNED', 'SCHEDULED', 'INFO',
     'CALCULATING', 'ENROLLED'].includes(s)
  ) {
    return 'badge-info'
  }
  if (['SUSPENDED', 'EXPIRED', 'COMPLETED'].includes(s)) {
    return 'badge-gray'
  }
  return 'badge-gray'
}

function formatStatus(status: string): string {
  return status
    ?.replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase()) || 'Unknown'
}

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span className={clsx(getStatusClass(status), className)}>
      {formatStatus(status)}
    </span>
  )
}
