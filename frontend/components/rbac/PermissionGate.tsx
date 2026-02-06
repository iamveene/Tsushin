'use client'

/**
 * Permission Gate Component
 * Conditionally renders children based on permission
 */

import { useAuth } from '@/contexts/AuthContext'

interface PermissionGateProps {
  permission: string | string[]
  fallback?: React.ReactNode
  children: React.ReactNode
}

export default function PermissionGate({ permission, fallback, children }: PermissionGateProps) {
  const { hasPermission } = useAuth()

  // Check if user has any of the required permissions
  const hasAccess = Array.isArray(permission)
    ? permission.some((p) => hasPermission(p))
    : hasPermission(permission)

  if (!hasAccess) {
    return fallback ? <>{fallback}</> : null
  }

  return <>{children}</>
}
