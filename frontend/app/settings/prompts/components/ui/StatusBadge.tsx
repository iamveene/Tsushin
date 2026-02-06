'use client'

import React from 'react'

export interface StatusBadgeProps {
  isActive: boolean
  activeLabel?: string
  inactiveLabel?: string
}

export function StatusBadge({
  isActive,
  activeLabel = 'Active',
  inactiveLabel = 'Inactive'
}: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs ${
      isActive
        ? 'bg-green-500/20 text-green-400'
        : 'bg-yellow-500/20 text-yellow-400'
    }`}>
      {isActive ? activeLabel : inactiveLabel}
    </span>
  )
}

export interface TypeBadgeProps {
  isSystem: boolean
}

export function TypeBadge({ isSystem }: TypeBadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs ${
      isSystem
        ? 'bg-blue-500/20 text-blue-400'
        : 'bg-purple-500/20 text-purple-400'
    }`}>
      {isSystem ? 'System' : 'Custom'}
    </span>
  )
}
