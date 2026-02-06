'use client'

/**
 * Pending Invitations Component
 * Shows invitations that haven't been accepted yet
 */

import RoleBadge from './RoleBadge'

interface Invitation {
  id: number
  email: string
  role: string
  invitedBy: string
  sentAt: string
  expiresAt: string
}

interface PendingInvitationsProps {
  invitations: Invitation[]
  onResend?: (invitationId: number) => void
  onCancel?: (invitationId: number) => void
}

export default function PendingInvitations({
  invitations,
  onResend,
  onCancel,
}: PendingInvitationsProps) {
  if (invitations.length === 0) {
    return null
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Pending Invitations ({invitations.length})
      </h3>

      <div className="space-y-3">
        {invitations.map((invitation) => (
          <div
            key={invitation.id}
            className="flex items-center justify-between p-4 bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-800 rounded-lg"
          >
            <div className="flex-1">
              <div className="flex items-center space-x-3">
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {invitation.email}
                </span>
                <RoleBadge role={invitation.role} size="sm" />
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                Invited by {invitation.invitedBy} • Sent {invitation.sentAt} • Expires{' '}
                {invitation.expiresAt}
              </p>
            </div>

            <div className="flex items-center space-x-2">
              {onResend && (
                <button
                  onClick={() => onResend(invitation.id)}
                  className="px-3 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-md transition-colors"
                >
                  Resend
                </button>
              )}
              {onCancel && (
                <button
                  onClick={() => {
                    if (confirm('Cancel this invitation?')) {
                      onCancel(invitation.id)
                    }
                  }}
                  className="px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
                >
                  Cancel
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
