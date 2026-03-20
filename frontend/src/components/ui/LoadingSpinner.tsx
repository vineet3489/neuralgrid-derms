import React from 'react'
import clsx from 'clsx'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
  fullPage?: boolean
  label?: string
}

export default function LoadingSpinner({
  size = 'md',
  className,
  fullPage = false,
  label,
}: LoadingSpinnerProps) {
  const sizeClass = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-2',
    lg: 'w-12 h-12 border-3',
  }[size]

  const spinner = (
    <div className={clsx('flex flex-col items-center gap-3', className)}>
      <div
        className={clsx(
          'rounded-full border-gray-700 border-t-indigo-500 animate-spin',
          sizeClass
        )}
      />
      {label && (
        <span className="text-sm text-gray-400">{label}</span>
      )}
    </div>
  )

  if (fullPage) {
    return (
      <div className="flex items-center justify-center h-full min-h-[200px]">
        {spinner}
      </div>
    )
  }

  return spinner
}
