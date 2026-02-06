'use client'

/**
 * UserNode - Node component for displaying users in the graph
 * Phase 5: Users View Implementation
 */

import { memo, useState } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { UserNodeData, UserRole } from '../types'

// Role badge configuration
const roleBadgeConfig: Record<UserRole, { icon: JSX.Element; label: string; bgColor: string; textColor: string }> = {
  owner: {
    icon: (
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
      </svg>
    ),
    label: 'Owner',
    bgColor: 'bg-amber-500/20',
    textColor: 'text-amber-400',
  },
  admin: {
    icon: (
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
      </svg>
    ),
    label: 'Admin',
    bgColor: 'bg-purple-500/20',
    textColor: 'text-purple-400',
  },
  member: {
    icon: (
      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
    label: 'Member',
    bgColor: 'bg-blue-500/20',
    textColor: 'text-blue-400',
  },
}

function UserNode(props: NodeProps<UserNodeData>) {
  const { data, selected } = props
  const [showTooltip, setShowTooltip] = useState(false)

  const roleConfig = roleBadgeConfig[data.role]

  // Get avatar initials from name
  const getInitials = (name: string) => {
    const parts = name.split(' ')
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
    }
    return name.substring(0, 2).toUpperCase()
  }

  // Format last login date
  const formatLastLogin = (dateStr: string | null) => {
    if (!dateStr) return 'Never'
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays} days ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
    return date.toLocaleDateString()
  }

  return (
    <div
      className={`
        relative px-4 py-3 rounded-lg border-2 min-w-[200px]
        transition-all duration-200
        ${selected
          ? 'border-tsushin-indigo bg-tsushin-surface shadow-lg shadow-tsushin-indigo/20'
          : 'border-tsushin-border bg-tsushin-deep hover:border-tsushin-border-hover'
        }
        ${!data.isActive ? 'opacity-50' : ''}
      `}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      {/* Connection handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-tsushin-indigo !w-2 !h-2 !border-2 !border-tsushin-deep"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-tsushin-indigo !w-2 !h-2 !border-2 !border-tsushin-deep"
      />

      <div className="flex items-center gap-3">
        {/* User Avatar */}
        <div className="relative">
          {data.avatarUrl ? (
            <img
              src={data.avatarUrl}
              alt={data.name}
              className="w-10 h-10 rounded-full object-cover"
            />
          ) : (
            <div className="w-10 h-10 rounded-full bg-tsushin-indigo/20 flex items-center justify-center">
              <span className="text-sm font-medium text-tsushin-indigo">
                {getInitials(data.name)}
              </span>
            </div>
          )}
          {/* Active status indicator */}
          <span
            className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-tsushin-deep ${
              data.isActive ? 'bg-green-500' : 'bg-gray-500'
            }`}
            title={data.isActive ? 'Active' : 'Inactive'}
          />
        </div>

        {/* User Info */}
        <div className="flex flex-col min-w-0 flex-1">
          <div className="font-medium text-white text-sm truncate max-w-[140px]">
            {data.name}
          </div>
          <div className="text-xs text-tsushin-slate truncate max-w-[140px]">
            {data.email}
          </div>

          {/* Badges row */}
          <div className="flex items-center gap-1 mt-1 flex-wrap">
            {/* Role badge */}
            <span
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${roleConfig.bgColor} ${roleConfig.textColor}`}
              title={roleConfig.label}
            >
              {roleConfig.icon}
              <span className="text-[10px] font-medium">{roleConfig.label}</span>
            </span>

            {/* Linked Contact badge */}
            {data.linkedContactId && (
              <span
                className="flex items-center justify-center w-4 h-4 rounded bg-green-500/20"
                title={`Linked to: ${data.linkedContactName || 'Contact'}`}
              >
                <svg className="w-2.5 h-2.5 text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                </svg>
              </span>
            )}
          </div>
        </div>

        {/* Hover Tooltip */}
        {showTooltip && (
          <div className="absolute left-full ml-2 top-0 z-50 bg-tsushin-deep border border-tsushin-border rounded-lg p-3 shadow-xl min-w-[180px] pointer-events-none">
            <div className="text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Role:</span>
                <span className={`font-medium ${roleConfig.textColor}`}>{data.roleDisplayName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Status:</span>
                <span className={`font-medium ${data.isActive ? 'text-green-400' : 'text-gray-400'}`}>
                  {data.isActive ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-tsushin-slate">Last Login:</span>
                <span className="text-white font-medium">{formatLastLogin(data.lastLoginAt)}</span>
              </div>
              {data.linkedContactName && (
                <div className="flex justify-between">
                  <span className="text-tsushin-slate">Contact:</span>
                  <span className="text-green-400 font-medium truncate max-w-[100px]">{data.linkedContactName}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(UserNode)
