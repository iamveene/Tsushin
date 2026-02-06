'use client'

/**
 * Invite User Page
 * Form to invite new team members
 * Phase 7.9: Connected to real API
 */

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api, RoleInfo } from '@/lib/client'
import { copyToClipboard } from '@/lib/clipboard'
import { Input } from '@/components/ui/form-input'
import RoleBadge from '@/components/rbac/RoleBadge'

export default function InviteUserPage() {
  const router = useRouter()
  const { user, hasPermission } = useAuth()
  const [formData, setFormData] = useState({
    email: '',
    role: 'member',
    message: '',
  })
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState(false)
  const [invitationLink, setInvitationLink] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [loadingRoles, setLoadingRoles] = useState(true)

  const canInvite = hasPermission('users.invite')

  // Fetch available roles
  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const response = await api.getAvailableRoles()
        setRoles(response.roles)
      } catch (err) {
        console.error('Failed to fetch roles:', err)
        // Fallback to default roles
        setRoles([
          { name: 'admin', display_name: 'Admin', description: 'Full administrative access except billing', can_assign: false },
          { name: 'member', display_name: 'Member', description: 'Standard user role', can_assign: true },
          { name: 'readonly', display_name: 'Read-Only', description: 'View-only access', can_assign: true },
        ])
      } finally {
        setLoadingRoles(false)
      }
    }
    fetchRoles()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const response = await api.inviteTeamMember({
        email: formData.email,
        role: formData.role,
        message: formData.message || undefined,
      })

      // Use the invitation link from the response
      const baseUrl = window.location.origin
      setInvitationLink(`${baseUrl}${response.invitation_link}`)
      setSuccess(true)

      // Reset form after 10 seconds
      setTimeout(() => {
        setSuccess(false)
        setFormData({ email: '', role: 'member', message: '' })
        setInvitationLink('')
      }, 10000)
    } catch (err: any) {
      setError(err.message || 'Failed to send invitation')
    } finally {
      setLoading(false)
    }
  }

  const selectedRole = roles.find((r) => r.name === formData.role)

  if (!canInvite) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to invite team members.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => router.back()}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-4"
          >
            ← Back to Team
          </button>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            Invite Team Member
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
            Send an invitation to join your organization
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}

        {/* Success Message */}
        {success && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-green-900 dark:text-green-100 mb-2">
              ✓ Invitation Sent!
            </h3>
            <p className="text-sm text-green-800 dark:text-green-200 mb-4">
              An invitation has been sent to <strong>{formData.email}</strong>
            </p>

            <div className="bg-white dark:bg-gray-800 rounded-md p-4">
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Invitation Link:
              </label>
              <div className="flex items-center space-x-2">
                <input
                  type="text"
                  value={invitationLink}
                  readOnly
                  className="flex-1 px-3 py-2 border dark:border-gray-700 rounded-md text-sm text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900"
                />
                <button
                  onClick={() => {
                    copyToClipboard(invitationLink)
                    alert('Link copied!')
                  }}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
                >
                  Copy
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                This link will expire in 7 days
              </p>
            </div>
          </div>
        )}

        {/* Invitation Form */}
        <form onSubmit={handleSubmit}>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 space-y-6">
            {/* Email */}
            <Input
              label="Email Address"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
              placeholder="colleague@example.com"
              helperText="The person you're inviting will receive an email with instructions"
            />

            {/* Role Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Role
              </label>
              {loadingRoles ? (
                <div className="text-gray-500">Loading roles...</div>
              ) : (
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
                >
                  {roles.filter(r => r.can_assign).map((role) => (
                    <option key={role.name} value={role.name}>
                      {role.display_name} - {role.description}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Role Preview */}
            {selectedRole && (
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <div className="flex items-center space-x-3 mb-3">
                  <RoleBadge role={selectedRole.name} />
                  <span className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                    {selectedRole.display_name}
                  </span>
                </div>
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  {selectedRole.description}
                </p>
              </div>
            )}

            {/* Custom Message */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Personal Message (Optional)
              </label>
              <textarea
                value={formData.message}
                onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                rows={4}
                placeholder="Add a personal message to the invitation email..."
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Actions */}
            <div className="flex items-center space-x-3 pt-4">
              <button
                type="submit"
                disabled={loading || !formData.email}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Sending...' : 'Send Invitation'}
              </button>
              <button
                type="button"
                onClick={() => router.back()}
                className="px-6 py-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 font-medium rounded-md transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
