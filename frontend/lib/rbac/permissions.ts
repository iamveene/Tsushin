/**
 * Permission Constants
 * Defines all available permissions in the system
 */

export const PERMISSIONS = {
  // Global Admin
  GLOBAL_ALL: 'global.*',
  GLOBAL_SYSTEM_INTEGRATIONS: 'global.system.integrations',
  GLOBAL_TENANTS: 'global.tenants',
  GLOBAL_BILLING: 'global.billing.*',

  // Agents
  AGENTS_READ: 'agents.read',
  AGENTS_WRITE: 'agents.write',
  AGENTS_DELETE: 'agents.delete',
  AGENTS_EXECUTE: 'agents.execute',
  AGENTS_ALL: 'agents.*',

  // Contacts
  CONTACTS_READ: 'contacts.read',
  CONTACTS_WRITE: 'contacts.write',
  CONTACTS_DELETE: 'contacts.delete',
  CONTACTS_ALL: 'contacts.*',

  // Memory
  MEMORY_READ: 'memory.read',
  MEMORY_WRITE: 'memory.write',
  MEMORY_CLEAR: 'memory.clear',
  MEMORY_ALL: 'memory.*',

  // Integrations
  INTEGRATIONS_READ: 'integrations.read',
  INTEGRATIONS_LINK: 'integrations.link',
  INTEGRATIONS_CONFIGURE: 'integrations.configure',
  INTEGRATIONS_UNLINK: 'integrations.unlink',
  INTEGRATIONS_ALL: 'integrations.*',

  // Users & Team Management
  USERS_READ: 'users.read',
  USERS_INVITE: 'users.invite',
  USERS_MANAGE: 'users.manage',
  USERS_REMOVE: 'users.remove',
  USERS_ALL: 'users.*',

  // Organization Settings
  ORG_READ: 'org.settings.read',
  ORG_WRITE: 'org.settings.write',
  ORG_DELETE: 'org.settings.delete',
  ORG_ALL: 'org.*',

  // Billing
  BILLING_READ: 'billing.read',
  BILLING_MANAGE: 'billing.manage',
  BILLING_ALL: 'billing.*',

  // Audit Logs
  AUDIT_READ: 'audit.read',
  AUDIT_ALL: 'audit.*',
} as const

export type PermissionKey = keyof typeof PERMISSIONS
export type PermissionValue = (typeof PERMISSIONS)[PermissionKey]

/**
 * Check if a permission string matches a required permission
 * Supports wildcard matching (e.g., 'agents.*' matches 'agents.read')
 */
export function matchesPermission(userPermission: string, requiredPermission: string): boolean {
  // Global admin has all permissions
  if (userPermission === 'global.*') return true

  // Exact match
  if (userPermission === requiredPermission) return true

  // Wildcard match
  const parts = requiredPermission.split('.')
  for (let i = parts.length; i > 0; i--) {
    const wildcardPerm = parts.slice(0, i).join('.') + '.*'
    if (userPermission === wildcardPerm) return true
  }

  return false
}

/**
 * Get all permissions for a role
 */
export function getPermissionsForRole(role: string): string[] {
  switch (role) {
    case 'owner':
      return [
        PERMISSIONS.AGENTS_ALL,
        PERMISSIONS.CONTACTS_ALL,
        PERMISSIONS.MEMORY_ALL,
        PERMISSIONS.INTEGRATIONS_ALL,
        PERMISSIONS.USERS_ALL,
        PERMISSIONS.ORG_ALL,
        PERMISSIONS.BILLING_ALL,
        PERMISSIONS.AUDIT_READ,
      ]

    case 'admin':
      return [
        PERMISSIONS.AGENTS_ALL,
        PERMISSIONS.CONTACTS_ALL,
        PERMISSIONS.MEMORY_ALL,
        PERMISSIONS.INTEGRATIONS_ALL,
        PERMISSIONS.USERS_ALL,
        PERMISSIONS.ORG_WRITE,
        PERMISSIONS.ORG_READ,
        PERMISSIONS.AUDIT_READ,
      ]

    case 'member':
      return [
        PERMISSIONS.AGENTS_READ,
        PERMISSIONS.AGENTS_WRITE,
        PERMISSIONS.AGENTS_EXECUTE,
        PERMISSIONS.CONTACTS_READ,
        PERMISSIONS.CONTACTS_WRITE,
        PERMISSIONS.MEMORY_READ,
        PERMISSIONS.MEMORY_WRITE,
        PERMISSIONS.INTEGRATIONS_READ,
        PERMISSIONS.INTEGRATIONS_LINK,
        PERMISSIONS.INTEGRATIONS_CONFIGURE,
      ]

    case 'readonly':
      return [
        PERMISSIONS.AGENTS_READ,
        PERMISSIONS.CONTACTS_READ,
        PERMISSIONS.MEMORY_READ,
        PERMISSIONS.INTEGRATIONS_READ,
      ]

    case 'global_admin':
      return [PERMISSIONS.GLOBAL_ALL]

    default:
      return []
  }
}
