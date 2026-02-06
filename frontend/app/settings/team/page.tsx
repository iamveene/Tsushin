'use client'

/**
 * Team Management Page
 * Shows team members, pending invitations, and invite actions
 * Phase 7.9: Connected to real API
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api, TeamMember, TeamInvitation } from '@/lib/client'
import { formatDate } from '@/lib/dateUtils'
import TeamMemberCard from '@/components/rbac/TeamMemberCard'
import PendingInvitations from '@/components/rbac/PendingInvitations'

export default function TeamManagementPage() {
  const { user, hasPermission } = useAuth()
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([])
  const [invitations, setInvitations] = useState<TeamInvitation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterRole, setFilterRole] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')

  const canManageTeam = hasPermission('users.invite')

  // Fetch team members
  const fetchTeamMembers = useCallback(async () => {
    try {
      const response = await api.getTeamMembers({
        role: filterRole !== 'all' ? filterRole : undefined,
        is_active: filterStatus === 'all' ? undefined : filterStatus === 'active',
      })
      setTeamMembers(response.members)
    } catch (err) {
      console.error('Failed to fetch team members:', err)
      setError('Failed to load team members')
    }
  }, [filterRole, filterStatus])

  // Fetch invitations
  const fetchInvitations = useCallback(async () => {
    if (!canManageTeam) return
    try {
      const response = await api.getTeamInvitations()
      setInvitations(response.invitations)
    } catch (err) {
      console.error('Failed to fetch invitations:', err)
    }
  }, [canManageTeam])

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([fetchTeamMembers(), fetchInvitations()])
      setLoading(false)
    }
    loadData()
  }, [fetchTeamMembers, fetchInvitations])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = async () => {
      await Promise.all([fetchTeamMembers(), fetchInvitations()])
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [fetchTeamMembers, fetchInvitations])

  if (!hasPermission('users.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
            Access Denied
          </h3>
          <p className="text-sm text-red-800 dark:text-red-200">
            You don't have permission to view team members.
          </p>
        </div>
      </div>
    )
  }

  // Filter team members locally (search)
  const filteredMembers = teamMembers.filter((member) => {
    const matchesSearch =
      (member.full_name?.toLowerCase().includes(searchQuery.toLowerCase()) || false) ||
      member.email.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesSearch
  })

  const handleRoleChange = async (memberId: number, newRole: string) => {
    try {
      await api.changeTeamMemberRole(memberId, newRole)
      await fetchTeamMembers()
    } catch (err: any) {
      alert(err.message || 'Failed to change role')
    }
  }

  const handleSuspend = async (memberId: number) => {
    // Note: This would need a separate API endpoint for suspend/unsuspend
    // For now, we'll show a message
    alert('User suspension is managed through the user details page')
  }

  const handleRemove = async (memberId: number) => {
    if (!confirm('Are you sure you want to remove this team member?')) return
    try {
      await api.removeTeamMember(memberId)
      await fetchTeamMembers()
    } catch (err: any) {
      alert(err.message || 'Failed to remove team member')
    }
  }

  const handleResendInvitation = async (invitationId: number) => {
    try {
      await api.resendInvitation(invitationId)
      await fetchInvitations()
      alert('Invitation resent successfully')
    } catch (err: any) {
      alert(err.message || 'Failed to resend invitation')
    }
  }

  const handleCancelInvitation = async (invitationId: number) => {
    if (!confirm('Are you sure you want to cancel this invitation?')) return
    try {
      await api.cancelInvitation(invitationId)
      await fetchInvitations()
    } catch (err: any) {
      alert(err.message || 'Failed to cancel invitation')
    }
  }

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-gray-600 dark:text-gray-400">Loading team members...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">Error</h3>
          <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          <button
            onClick={() => {
              setError(null)
              fetchTeamMembers()
            }}
            className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  // Transform TeamMember to the format expected by TeamMemberCard
  const membersForCard = filteredMembers.map((member) => ({
    id: member.id,
    name: member.full_name || member.email.split('@')[0],
    email: member.email,
    role: member.role,
    status: member.is_active ? ('active' as const) : ('suspended' as const),
    lastActive: member.last_login_at
      ? formatDate(member.last_login_at)
      : 'Never',
    authProvider: member.auth_provider,
    avatarUrl: member.avatar_url,
  }))

  // Transform invitations for PendingInvitations component
  const invitationsForComponent = invitations.map((inv) => ({
    id: inv.id,
    email: inv.email,
    role: inv.role,
    invitedBy: inv.invited_by_name,
    sentAt: formatDate(inv.created_at),
    expiresAt: formatDate(inv.expires_at),
  }))

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Team Members</h1>
            <p className="text-gray-600 dark:text-gray-400 mt-2">
              Manage your team and invite new members
            </p>
          </div>

          {canManageTeam && (
            <Link
              href="/settings/team/invite"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
            >
              + Invite Member
            </Link>
          )}
        </div>

        {/* Back to Settings */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Pending Invitations */}
        {canManageTeam && invitationsForComponent.length > 0 && (
          <div className="mb-6">
            <PendingInvitations
              invitations={invitationsForComponent}
              onResend={handleResendInvitation}
              onCancel={handleCancelInvitation}
            />
          </div>
        )}

        {/* Search and Filters */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Search
              </label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name or email..."
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Filter by Role
              </label>
              <select
                value={filterRole}
                onChange={(e) => setFilterRole(e.target.value)}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              >
                <option value="all">All Roles</option>
                <option value="owner">Owner</option>
                <option value="admin">Admin</option>
                <option value="member">Member</option>
                <option value="readonly">Read-Only</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                Filter by Status
              </label>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              >
                <option value="all">All Status</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>
            </div>
          </div>
        </div>

        {/* Team Members List */}
        <div className="space-y-4">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              Members ({filteredMembers.length})
            </h2>
          </div>

          {membersForCard.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center">
              <p className="text-gray-600 dark:text-gray-400">
                No members found matching your filters.
              </p>
            </div>
          ) : (
            membersForCard.map((member) => (
              <TeamMemberCard
                key={member.id}
                member={member}
                canEdit={canManageTeam}
                onRoleChange={handleRoleChange}
                onSuspend={handleSuspend}
                onRemove={handleRemove}
              />
            ))
          )}
        </div>
      </div>
    </div>
  )
}
