'use client'

/**
 * Phase 14.1: Thread Header
 *
 * Displays current thread title with rename, export, and delete options.
 */

import React, { useState } from 'react'
import { api, PlaygroundThread } from '@/lib/client'

interface ThreadHeaderProps {
  thread: PlaygroundThread | null
  onThreadUpdated: () => void
  onThreadDeleted: () => void
  onThreadRenamed?: (threadId: number, newTitle: string) => void
  onOpenSearch?: () => void  // Phase 14.5
  onExtractKnowledge?: () => void  // Phase 14.6
  agentId?: number  // Phase 14.6: needed for extraction
}

export default function ThreadHeader({ thread, onThreadUpdated, onThreadDeleted, onThreadRenamed, onOpenSearch, onExtractKnowledge, agentId }: ThreadHeaderProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [menuPosition, setMenuPosition] = useState<{ x: number; y: number } | null>(null)
  const menuButtonRef = React.useRef<HTMLButtonElement>(null)

  if (!thread) {
    return (
      <div className="px-6 py-4 border-b border-tsushin-indigo/20 bg-tsushin-dark/40 backdrop-blur-sm">
        <h1 className="text-lg font-semibold text-tsushin-text">Select a conversation</h1>
      </div>
    )
  }

  const startEdit = () => {
    setEditTitle(thread.title || '')
    setIsEditing(true)
  }

  const cancelEdit = () => {
    setIsEditing(false)
    setEditTitle('')
  }

  const saveEdit = async () => {
    if (!editTitle.trim() || editTitle === thread.title) {
      cancelEdit()
      return
    }

    const trimmedTitle = editTitle.trim()
    setIsLoading(true)
    try {
      await api.updateThread(thread.id, { title: trimmedTitle })
      setIsEditing(false)
      setEditTitle('')
      // Use specific rename callback if available for instant UI update
      if (onThreadRenamed) {
        onThreadRenamed(thread.id, trimmedTitle)
      } else {
        onThreadUpdated()
      }
    } catch (err) {
      console.error('Failed to update thread:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleExport = async () => {
    try {
      const exportData = await api.exportThread(thread.id)
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `thread-${thread.id}-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setShowMenu(false)
    } catch (err) {
      console.error('Failed to export thread:', err)
    }
  }

  const handleArchive = async () => {
    try {
      await api.updateThread(thread.id, { is_archived: !thread.is_archived })
      setShowMenu(false)
      onThreadUpdated()
    } catch (err) {
      console.error('Failed to archive thread:', err)
    }
  }

  const handleDelete = async () => {
    if (!confirm('Delete this conversation? This action cannot be undone.')) {
      setShowMenu(false)
      return
    }

    try {
      await api.deleteThread(thread.id)
      setShowMenu(false)
      onThreadDeleted()
    } catch (err) {
      console.error('Failed to delete thread:', err)
    }
  }

  return (
    <>
      <style jsx>{`
        .thread-menu-container {
          background-color: #0D1117 !important;
        }
        .thread-menu-button {
          background-color: #0D1117 !important;
        }
      `}</style>
    <div className="px-6 py-4 border-b border-tsushin-indigo/20 bg-tsushin-dark/40 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-4">
        {isEditing ? (
          <div className="flex-1 flex items-center gap-2">
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveEdit()
                if (e.key === 'Escape') cancelEdit()
              }}
              className="flex-1 px-3 py-2 bg-tsushin-surface/50 border border-tsushin-indigo/20 rounded-lg text-tsushin-text focus:outline-none focus:border-tsushin-indigo/40"
              placeholder="Thread title"
              autoFocus
              disabled={isLoading}
            />
            <button
              onClick={saveEdit}
              disabled={isLoading}
              className="p-2 rounded-lg bg-tsushin-indigo/20 hover:bg-tsushin-indigo/30 text-tsushin-indigo transition-colors disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </button>
            <button
              onClick={cancelEdit}
              disabled={isLoading}
              className="p-2 rounded-lg bg-tsushin-surface/50 hover:bg-tsushin-surface text-tsushin-slate transition-colors disabled:opacity-50"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        ) : (
          <>
            <div className="flex-1 flex items-center gap-3">
              <h1 className="text-lg font-semibold text-tsushin-text truncate">
                {thread.title || 'New Conversation'}
              </h1>
              <button
                onClick={startEdit}
                className="p-1.5 rounded-lg opacity-60 hover:opacity-100 hover:bg-tsushin-surface/30 text-tsushin-slate transition-all"
                title="Rename thread"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              {/* Phase 14.5: Search Button */}
              {onOpenSearch && (
                <button
                  onClick={onOpenSearch}
                  className="p-1.5 rounded-lg opacity-60 hover:opacity-100 hover:bg-tsushin-surface/30 text-tsushin-slate transition-all"
                  title="Search conversations (⌘K)"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </button>
              )}
              {thread.is_archived && (
                <span className="px-2 py-1 text-xs rounded-md bg-tsushin-surface/50 text-tsushin-slate">
                  Archived
                </span>
              )}
            </div>

            <div className="relative">
              <button
                ref={menuButtonRef}
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  setMenuPosition({ x: rect.right - 192, y: rect.bottom + 8 })  // 192px = menu width, 8px = spacing
                  setShowMenu(!showMenu)
                }}
                className="p-2 rounded-lg bg-tsushin-surface/30 hover:bg-tsushin-surface/50 text-tsushin-slate transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                </svg>
              </button>

              {showMenu && menuPosition && (
                <>
                  <div
                    style={{
                      position: 'fixed',
                      inset: 0,
                      zIndex: 9998
                    }}
                    onClick={() => setShowMenu(false)}
                  />
                  <div
                    className="thread-menu-container"
                    style={{
                      position: 'fixed',
                      left: `${menuPosition.x}px`,
                      top: `${menuPosition.y}px`,
                      zIndex: 9999,
                      width: '12rem',
                      backgroundColor: '#0D1117',
                      border: '1px solid rgba(60, 90, 254, 0.2)',
                      borderRadius: '0.5rem',
                      boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
                      overflow: 'hidden'
                    }}
                  >
                    {/* Phase 14.6: Extract Knowledge */}
                    {onExtractKnowledge && (
                      <button
                        className="thread-menu-button"
                        onClick={() => {
                          setShowMenu(false)
                          onExtractKnowledge()
                        }}
                        style={{
                          width: '100%',
                          padding: '0.5rem 1rem',
                          fontSize: '0.875rem',
                          textAlign: 'left',
                          border: 'none',
                          backgroundColor: '#0D1117',
                          color: '#f4f4f5',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                          cursor: 'pointer'
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#161B22'}
                        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#0D1117'}
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                        Extract Knowledge
                      </button>
                    )}
                    <button
                      className="thread-menu-button"
                      onClick={() => {
                        setShowMenu(false)
                        startEdit()
                      }}
                      style={{
                        width: '100%',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        textAlign: 'left',
                        border: 'none',
                        backgroundColor: '#0D1117',
                        color: '#f4f4f5',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        cursor: 'pointer'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#161B22'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#0D1117'}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      Rename
                    </button>
                    <button
                      className="thread-menu-button"
                      onClick={handleExport}
                      style={{
                        width: '100%',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        textAlign: 'left',
                        border: 'none',
                        backgroundColor: '#0D1117',
                        color: '#f4f4f5',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        cursor: 'pointer'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#161B22'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#0D1117'}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      Export as JSON
                    </button>
                    <button
                      className="thread-menu-button"
                      onClick={handleArchive}
                      style={{
                        width: '100%',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        textAlign: 'left',
                        border: 'none',
                        backgroundColor: '#0D1117',
                        color: '#f4f4f5',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        cursor: 'pointer'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#161B22'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#0D1117'}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                      </svg>
                      {thread.is_archived ? 'Unarchive' : 'Archive'}
                    </button>
                    <button
                      className="thread-menu-button"
                      onClick={handleDelete}
                      style={{
                        width: '100%',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        textAlign: 'left',
                        border: 'none',
                        backgroundColor: '#0D1117',
                        color: '#f87171',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        cursor: 'pointer'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)'}
                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#0D1117'}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Delete Thread
                    </button>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
    </>
  )
}
