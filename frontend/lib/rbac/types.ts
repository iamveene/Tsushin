/**
 * RBAC Type Definitions
 * Type definitions for role-based access control system
 */

export type Role = 'owner' | 'admin' | 'member' | 'readonly' | 'global_admin'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  tenant_id: string | null
  tenant_name: string | null
  is_global_admin: boolean
  permissions: string[]
  created_at: string
}

export interface Tenant {
  id: string
  name: string
  slug: string
  plan: string
  maxUsers: number
  maxAgents: number
  maxRequests: number
  isActive: boolean
  createdAt: string
}

export interface Permission {
  name: string
  resource: string
  action: string
  description: string
}

export interface RoleDefinition {
  name: Role
  displayName: string
  description: string
  permissions: Permission[]
}

export interface TeamMember {
  id: number
  name: string
  email: string
  role: Role
  status: 'active' | 'suspended'
  lastActive: string
  joinedAt: string
}

export interface Invitation {
  id: number
  email: string
  role: Role
  invitedBy: string
  sentAt: string
  expiresAt: string
}
