'use client'

/**
 * Phase 14.1: Thread List Sidebar
 *
 * Displays all conversation threads with search, filter, and management options.
 */

import React, { useState, useEffect } from 'react'
import { api, PlaygroundThread } from '@/lib/client'
import { formatRelative } from '@/lib/dateUtils'

interface ThreadListSidebarProps {
  agentId: number | null
  activeThreadId: number | null
  onThreadSelect: (threadId: number) => void
  onNewThread: () => void
  onThreadDeleted: () => void
  onThreadRenamed?: (threadId: number, newTitle: string) => void
}

export default function ThreadListSidebar({
  agentId,
  activeThreadId,
  onThreadSelect,
  onNewThread,
  onThreadDeleted,
  onThreadRenamed
}: ThreadListSidebarProps) {
  const [threads, setThreads] = useState<PlaygroundThread[]>([])
  const [filteredThreads, setFilteredThreads] = useState<PlaygroundThread[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [contextMenu, setContextMenu] = useState<{ threadId: number; x: number; y: number } | null>(null)
  const [renamingThreadId, setRenamingThreadId] = useState<number | null>(null)
  const [renameTitle, setRenameTitle] = useState('')

  useEffect(() => {
    if (agentId) {
      loadThreads()
    }
  }, [agentId, showArchived])

  useEffect(() => {
    // Filter threads based on search query
    if (searchQuery.trim() === '') {
      setFilteredThreads(threads)
    } else {
      const query = searchQuery.toLowerCase()
      setFilteredThreads(threads.filter(t =>
        t.title?.toLowerCase().includes(query) ||
        t.last_message_preview?.toLowerCase().includes(query)
      ))
    }
  }, [searchQuery, threads])

  const loadThreads = async () => {
    if (!agentId) return

    setIsLoading(true)
    try {
      const result = await api.listThreads(agentId, showArchived)
      setThreads(result.threads)
    } catch (err) {
      console.error('Failed to load threads:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleArchiveThread = async (threadId: number, currentArchived: boolean) => {
    try {
      await api.updateThread(threadId, { is_archived: !currentArchived })
      await loadThreads()
    } catch (err) {
      console.error('Failed to archive thread:', err)
    }
  }

  const handleDeleteThread = async (threadId: number) => {
    if (!confirm('Delete this conversation? This action cannot be undone.')) return

    try {
      await api.deleteThread(threadId)
      await loadThreads()
      if (threadId === activeThreadId) {
        onThreadDeleted()
      }
    } catch (err) {
      console.error('Failed to delete thread:', err)
    }
  }

  const handleExportThread = async (threadId: number) => {
    try {
      const exportData = await api.exportThread(threadId)
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `thread-${threadId}-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to export thread:', err)
    }
  }

  const handleStartRename = (threadId: number) => {
    const thread = threads.find(t => t.id === threadId)
    if (thread) {
      setRenamingThreadId(threadId)
      setRenameTitle(thread.title || '')
      setContextMenu(null)
    }
  }

  const handleCancelRename = () => {
    setRenamingThreadId(null)
    setRenameTitle('')
  }

  const handleSaveRename = async () => {
    if (!renamingThreadId || !renameTitle.trim()) {
      handleCancelRename()
      return
    }

    const trimmedTitle = renameTitle.trim()
    try {
      await api.updateThread(renamingThreadId, { title: trimmedTitle })
      await loadThreads()
      // Notify parent of rename so activeThread can be updated
      if (onThreadRenamed) {
        onThreadRenamed(renamingThreadId, trimmedTitle)
      }
      handleCancelRename()
    } catch (err) {
      console.error('Failed to rename thread:', err)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return ''
    return formatRelative(dateStr)
  }

  return (
    <div className="flex flex-col h-full bg-tsushin-dark/40 backdrop-blur-sm border-r border-tsushin-indigo/20">
      {/* Header */}
      <div className="p-4 border-b border-tsushin-indigo/20">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-tsushin-text uppercase tracking-wide">Conversations</h2>
          <button
            onClick={onNewThread}
            className="p-2 rounded-lg bg-tsushin-indigo/20 hover:bg-tsushin-indigo/30 text-tsushin-indigo transition-colors"
            title="New conversation"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-tsushin-slate w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-tsushin-surface/50 border border-tsushin-indigo/20 rounded-lg text-sm text-tsushin-text placeholder-tsushin-slate focus:outline-none focus:border-tsushin-indigo/40"
          />
        </div>

        {/* Archive toggle */}
        <button
          onClick={() => setShowArchived(!showArchived)}
          className={`mt-2 flex items-center gap-2 text-xs px-3 py-1.5 rounded-md transition-colors ${
            showArchived
              ? 'bg-tsushin-indigo/20 text-tsushin-indigo'
              : 'text-tsushin-slate hover:bg-tsushin-surface/50'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
          </svg>
          {showArchived ? 'Hide' : 'Show'} Archived
        </button>
      </div>

      {/* Thread List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-center text-tsushin-slate text-sm">Loading...</div>
        ) : filteredThreads.length === 0 ? (
          <div className="p-4 text-center text-tsushin-slate text-sm">
            {searchQuery ? 'No matching conversations' : 'No conversations yet'}
          </div>
        ) : (
          filteredThreads.map(thread => (
            <div
              key={thread.id}
              className={`relative group border-b border-tsushin-indigo/10 hover:bg-tsushin-surface/30 transition-colors cursor-pointer ${
                thread.id === activeThreadId ? 'bg-tsushin-indigo/10' : ''
              }`}
              onClick={() => onThreadSelect(thread.id)}
            >
              <div className="p-4">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <svg className="w-3.5 h-3.5 text-tsushin-indigo flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    <h3 className="text-sm font-medium text-tsushin-text truncate">
                      {thread.title || 'New Conversation'}
                    </h3>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setContextMenu({ threadId: thread.id, x: e.clientX, y: e.clientY })
                    }}
                    className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-tsushin-surface/50 transition-opacity"
                  >
                    <svg className="w-3.5 h-3.5 text-tsushin-slate" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                    </svg>
                  </button>
                </div>

                {thread.folder && (
                  <div className="flex items-center gap-1 text-xs text-tsushin-slate mb-1">
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                    <span>{thread.folder}</span>
                  </div>
                )}

                {thread.last_message_preview && (
                  <p className="text-xs text-tsushin-slate line-clamp-2 mb-2">
                    {thread.last_message_preview}
                  </p>
                )}

                <div className="flex items-center justify-between text-xs text-tsushin-slate/70">
                  <span>{thread.message_count} messages</span>
                  <span>{formatDate(thread.updated_at)}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setContextMenu(null)}
          />
          <div
            className="fixed z-50 border border-tsushin-indigo/20 rounded-lg shadow-xl overflow-hidden"
            style={{
              left: contextMenu.x,
              top: contextMenu.y,
              background: '#0D1117',
              opacity: 1
            }}
          >
            <button
              onClick={() => {
                handleStartRename(contextMenu.threadId)
              }}
              className="w-full px-4 py-2 text-sm text-left hover:bg-tsushin-surface/30 flex items-center gap-2"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Rename
            </button>
            <button
              onClick={() => {
                handleExportThread(contextMenu.threadId)
                setContextMenu(null)
              }}
              className="w-full px-4 py-2 text-sm text-left hover:bg-tsushin-surface/30 flex items-center gap-2"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export as JSON
            </button>
            <button
              onClick={() => {
                const thread = threads.find(t => t.id === contextMenu.threadId)
                if (thread) {
                  handleArchiveThread(contextMenu.threadId, thread.is_archived)
                }
                setContextMenu(null)
              }}
              className="w-full px-4 py-2 text-sm text-left hover:bg-tsushin-surface/30 flex items-center gap-2"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              {threads.find(t => t.id === contextMenu.threadId)?.is_archived ? 'Unarchive' : 'Archive'}
            </button>
            <button
              onClick={() => {
                handleDeleteThread(contextMenu.threadId)
                setContextMenu(null)
              }}
              className="w-full px-4 py-2 text-sm text-left hover:bg-red-500/10 text-red-400 flex items-center gap-2"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete
            </button>
          </div>
        </>
      )}

      {/* Rename Modal */}
      {renamingThreadId && (
        <>
          <div
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
            onClick={handleCancelRename}
          />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="bg-tsushin-dark border border-tsushin-indigo/20 rounded-lg p-6 max-w-md w-full shadow-xl">
              <h3 className="text-lg font-semibold text-tsushin-text mb-4">Rename Conversation</h3>
              <input
                type="text"
                value={renameTitle}
                onChange={(e) => setRenameTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSaveRename()
                  } else if (e.key === 'Escape') {
                    handleCancelRename()
                  }
                }}
                className="w-full px-3 py-2 bg-tsushin-surface border border-tsushin-indigo/20 rounded-lg text-tsushin-text placeholder-tsushin-slate focus:outline-none focus:border-tsushin-indigo/50 mb-4"
                placeholder="Enter conversation title"
                autoFocus
                maxLength={200}
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={handleCancelRename}
                  className="px-4 py-2 text-sm text-tsushin-slate hover:text-tsushin-text hover:bg-tsushin-surface/50 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveRename}
                  className="px-4 py-2 text-sm bg-tsushin-indigo hover:bg-tsushin-indigo/80 text-white rounded-lg transition-colors"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
