'use client'

/**
 * Phase 14.2: Message Actions
 *
 * Action buttons for individual messages: edit, regenerate, delete, copy, bookmark.
 */

import React, { useState } from 'react'
import { api, PlaygroundMessage } from '@/lib/client'
import { copyToClipboard } from '@/lib/clipboard'

interface MessageActionsProps {
  message: PlaygroundMessage
  agentId: number
  threadId: number
  onMessageUpdated: () => void
}

export default function MessageActions({ message, agentId, threadId, onMessageUpdated }: MessageActionsProps) {
  const [showActions, setShowActions] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState(message.content)
  const [isLoading, setIsLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const messageId = message.message_id || `msg_${message.timestamp}_${message.role}`
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  // Debug: Log isEditing state changes
  React.useEffect(() => {
    console.log('[EDIT DEBUG] isEditing changed to:', isEditing)
  }, [isEditing])

  // Reset edit content when entering edit mode
  React.useEffect(() => {
    if (isEditing) {
      setEditContent(message.content)
    }
  }, [isEditing, message.content])

  const handleEdit = async (e?: React.MouseEvent) => {
    // Prevent any default behavior and stop propagation
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }

    console.log('[EDIT DEBUG] handleEdit called')
    console.log('[EDIT DEBUG] editContent:', editContent)
    console.log('[EDIT DEBUG] message.content:', message.content)
    console.log('[EDIT DEBUG] messageId:', messageId)
    console.log('[EDIT DEBUG] agentId:', agentId, 'threadId:', threadId)

    if (!editContent.trim()) {
      console.log('[EDIT DEBUG] Content is empty, aborting')
      setIsEditing(false)
      return
    }

    if (editContent.trim() === message.content.trim()) {
      console.log('[EDIT DEBUG] Content unchanged, aborting')
      setIsEditing(false)
      return
    }

    console.log('[EDIT DEBUG] Calling API with:', { messageId, newContent: editContent.trim(), regenerate: true })
    setIsLoading(true)
    try {
      const result = await api.editMessage(agentId, threadId, {
        message_id: messageId,
        new_content: editContent.trim(),
        regenerate: true
      })
      console.log('[EDIT DEBUG] Edit API response:', result)
      setIsEditing(false)
      onMessageUpdated()
    } catch (err: any) {
      console.error('[EDIT DEBUG] Edit API failed:', err)
      alert(`Error: ${err.message || 'Failed to edit message'}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleRegenerate = async () => {
    setIsLoading(true)
    try {
      await api.regenerateMessage(agentId, threadId, { message_id: messageId })
      onMessageUpdated()
    } catch (err: any) {
      console.error('Failed to regenerate message:', err)
      alert(`Error: ${err.message || 'Failed to regenerate message'}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm('Delete this message and all subsequent messages?')) return

    setIsLoading(true)
    try {
      await api.deleteMessage(agentId, threadId, {
        message_id: messageId,
        delete_subsequent: true
      })
      onMessageUpdated()
    } catch (err: any) {
      console.error('Failed to delete message:', err)
      alert(`Error: ${err.message || 'Failed to delete message'}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopy = async () => {
    try {
      await copyToClipboard(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err: any) {
      console.error('Failed to copy message:', err)
      alert(`Error: ${err.message || 'Failed to copy message'}`)
    }
  }

  const handleBookmark = async () => {
    setIsLoading(true)
    try {
      await api.bookmarkMessage(agentId, threadId, {
        message_id: messageId,
        bookmarked: !message.is_bookmarked
      })
      onMessageUpdated()
    } catch (err: any) {
      console.error('Failed to bookmark message:', err)
      alert(`Error: ${err.message || 'Failed to bookmark message'}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleBranch = async () => {
    if (!confirm('Create a new conversation branch from this point?')) return

    setIsLoading(true)
    try {
      const result = await api.branchConversation(agentId, threadId, {
        message_id: messageId,
        new_thread_title: `Branch from ${message.content.slice(0, 30)}...`
      })

      if (result.new_thread) {
        alert(`New thread created: ${result.new_thread.title}`)
      }
      onMessageUpdated()
    } catch (err: any) {
      console.error('Failed to branch conversation:', err)
      alert(`Error: ${err.message || 'Failed to branch conversation'}`)
    } finally {
      setIsLoading(false)
    }
  }

  if (isEditing) {
    return (
      <div className="mt-2 space-y-2">
        <textarea
          value={editContent}
          onChange={(e) => {
            console.log('[EDIT DEBUG] onChange fired, new value:', e.target.value)
            setEditContent(e.target.value)
          }}
          className="w-full px-3 py-2 bg-tsushin-surface/50 border border-tsushin-indigo/20 rounded-lg text-tsushin-text focus:outline-none focus:border-tsushin-indigo/40 resize-none"
          rows={3}
          disabled={isLoading}
          autoFocus
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            onMouseDown={() => console.log('[EDIT DEBUG] onMouseDown fired on Save button')}
            onClick={handleEdit}
            disabled={isLoading}
            className="px-3 py-1.5 text-sm rounded-md bg-tsushin-indigo/20 hover:bg-tsushin-indigo/30 text-tsushin-indigo transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Saving...' : 'Save & Regenerate'}
          </button>
          <button
            type="button"
            onClick={() => {
              console.log('[EDIT DEBUG] Cancel button clicked')
              setIsEditing(false)
            }}
            disabled={isLoading}
            className="px-3 py-1.5 text-sm rounded-md bg-tsushin-surface/50 hover:bg-tsushin-surface text-tsushin-slate transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className="group relative"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Action Buttons */}
      <div className={`absolute ${isUser ? 'right-0' : 'left-0'} -top-8 flex items-center gap-1 transition-opacity ${showActions ? 'opacity-100' : 'opacity-0'}`}>
        {/* Copy Button */}
        <button
          type="button"
          onClick={handleCopy}
          disabled={isLoading}
          className="p-1.5 rounded-md border border-tsushin-indigo/20 hover:bg-tsushin-surface text-tsushin-slate hover:text-tsushin-indigo transition-colors disabled:opacity-50"
          style={{ background: '#0D1117', opacity: 1 }}
          title="Copy message"
        >
          {copied ? (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          )}
        </button>

        {/* Edit Button (user messages only) */}
        {isUser && (
          <button
            type="button"
            onClick={() => {
              console.log('[EDIT DEBUG] Edit button clicked, setting isEditing to true')
              setIsEditing(true)
            }}
            disabled={isLoading}
            className="p-1.5 rounded-md backdrop-blur-sm border border-tsushin-indigo/20 hover:bg-tsushin-surface text-tsushin-slate hover:text-tsushin-indigo transition-colors disabled:opacity-50"
            style={{ backgroundColor: '#1C2128' }}
            title="Edit message"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
        )}

        {/* Regenerate Button (assistant messages only) */}
        {isAssistant && (
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={isLoading}
            className="p-1.5 rounded-md backdrop-blur-sm border border-tsushin-indigo/20 hover:bg-tsushin-surface text-tsushin-slate hover:text-tsushin-indigo transition-colors disabled:opacity-50"
            style={{ backgroundColor: '#1C2128' }}
            title="Regenerate response"
          >
            <svg className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        )}

        {/* Bookmark Button */}
        <button
          type="button"
          onClick={handleBookmark}
          disabled={isLoading}
          className={`p-1.5 rounded-md backdrop-blur-sm border border-tsushin-indigo/20 hover:bg-tsushin-surface transition-colors disabled:opacity-50 ${
            message.is_bookmarked
              ? 'text-yellow-400'
              : 'text-tsushin-slate hover:text-yellow-400'
          }`}
          style={{ backgroundColor: '#1C2128' }}
          title={message.is_bookmarked ? 'Remove bookmark' : 'Bookmark message'}
        >
          <svg className="w-3.5 h-3.5" fill={message.is_bookmarked ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
          </svg>
        </button>

        {/* Branch Button */}
        <button
          type="button"
          onClick={handleBranch}
          disabled={isLoading}
          className="p-1.5 rounded-md border border-tsushin-indigo/20 hover:bg-tsushin-surface text-tsushin-slate hover:text-tsushin-indigo transition-colors disabled:opacity-50"
          style={{ background: '#0D1117', opacity: 1 }}
          title="Create branch from here"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
          </svg>
        </button>

        {/* Delete Button */}
        <button
          type="button"
          onClick={handleDelete}
          disabled={isLoading}
          className="p-1.5 rounded-md backdrop-blur-sm border border-tsushin-indigo/20 hover:bg-red-500/20 text-tsushin-slate hover:text-red-400 transition-colors disabled:opacity-50"
          style={{ backgroundColor: '#1C2128' }}
          title="Delete message"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        </button>
      </div>

      {/* Edit Indicator */}
      {message.is_edited && (
        <div className="text-xs text-tsushin-slate/70 mt-1">
          (edited)
        </div>
      )}

      {/* Bookmark Indicator */}
      {message.is_bookmarked && !showActions && (
        <div className="absolute top-0 right-0 text-yellow-400">
          <svg className="w-3 h-3" fill="currentColor" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
          </svg>
        </div>
      )}
    </div>
  )
}
