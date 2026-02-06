'use client'

/**
 * Role Selector Component
 * Dropdown to change user role
 */

import { Select } from '@/components/ui/form-input'

interface RoleSelectorProps {
  currentRole: string
  onChange: (newRole: string) => void
  disabled?: boolean
}

const ROLES = [
  { value: 'owner', label: 'Owner', description: 'Full control including billing' },
  { value: 'admin', label: 'Admin', description: 'All permissions except billing' },
  { value: 'member', label: 'Member', description: 'Can manage own resources' },
  { value: 'readonly', label: 'Read-Only', description: 'View-only access' },
]

export default function RoleSelector({ currentRole, onChange, disabled }: RoleSelectorProps) {
  return (
    <Select
      value={currentRole}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="w-full"
    >
      {ROLES.map((role) => (
        <option key={role.value} value={role.value}>
          {role.label} - {role.description}
        </option>
      ))}
    </Select>
  )
}
