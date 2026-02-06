/**
 * Permission Hook
 * Provides permission checking functionality
 */

import { useAuth } from '@/contexts/AuthContext'

export function usePermission() {
  const { user, hasPermission } = useAuth()

  return {
    user,
    hasPermission,
    isGlobalAdmin: user?.is_global_admin || false,
    canManageUsers: hasPermission('users.manage'),
    canInviteUsers: hasPermission('users.invite'),
    canManageBilling: hasPermission('billing.manage'),
    canEditOrg: hasPermission('org.settings.write'),
    canCreateAgents: hasPermission('agents.write'),
    canExecuteAgents: hasPermission('agents.execute'),
  }
}
