'use client'

/**
 * Phase 17: Memory Inspector Component
 * Phase 18: Add CRUD operations for facts
 * Item 37: Temporal decay freshness badges + archive decayed
 *
 * View and inspect agent memory layers in cockpit mode.
 * Features:
 * - Working memory view (recent messages)
 * - Semantic memory search
 * - Learned facts display with edit/delete/create
 * - Memory stats
 * - Freshness badges (fresh/fading/stale/archived) with decay factor
 * - Archive decayed facts button
 */

import React, { useState, useEffect } from 'react'
import {
  BrainIcon,
  AlertTriangleIcon,
  InboxIcon,
  SearchIcon,
  DocumentIcon
} from '@/components/ui/icons'
import { formatDateTime } from '@/lib/dateUtils'
import { authenticatedFetch, api } from '@/lib/client'

interface MemoryMessage {
  role: string
  content: string
  timestamp?: string
  metadata?: Record<string, any>
}

interface Fact {
  id?: number
  topic: string
  key: string
  value: string
  fact_type: 'user' | 'project'
  project_id?: number
  confidence?: number
  source?: string
  freshness?: 'fresh' | 'fading' | 'stale' | 'archived'
  decay_factor?: number
  last_accessed_at?: string
  effective_confidence?: number
}

interface MemoryData {
  working_memory: MemoryMessage[]
  semantic_results: any[]
  facts: Fact[]
  stats: {
    working_memory_count: number
    semantic_count: number
    facts_count: number
    sender_key?: string
    project_id?: number
  }
}

interface FreshnessDistribution {
  fresh: number
  fading: number
  stale: number
  archived: number
}

interface MemoryInspectorProps {
  agentId: number | null
  senderKey?: string
}

const FRESHNESS_COLORS: Record<string, { dot: string; text: string; bg: string }> = {
  fresh: { dot: 'bg-emerald-500', text: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  fading: { dot: 'bg-amber-500', text: 'text-amber-400', bg: 'bg-amber-500/10' },
  stale: { dot: 'bg-orange-500', text: 'text-orange-400', bg: 'bg-orange-500/10' },
  archived: { dot: 'bg-gray-500', text: 'text-gray-400', bg: 'bg-gray-500/10' },
}

export default function MemoryInspector({ agentId, senderKey }: MemoryInspectorProps) {
  const [memoryData, setMemoryData] = useState<MemoryData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeLayer, setActiveLayer] = useState<'working' | 'semantic' | 'facts'>('working')
  const [searchQuery, setSearchQuery] = useState('')

  // Freshness distribution from memory stats
  const [freshnessDistribution, setFreshnessDistribution] = useState<FreshnessDistribution | null>(null)
  const [decayEnabled, setDecayEnabled] = useState(false)

  // Archive state
  const [archiving, setArchiving] = useState(false)
  const [archivePreview, setArchivePreview] = useState<{ count: number; facts: any[] } | null>(null)

  // Editing state
  const [editingFactId, setEditingFactId] = useState<number | null>(null)
  const [editingTopic, setEditingTopic] = useState('')
  const [editingKey, setEditingKey] = useState('')
  const [editingValue, setEditingValue] = useState('')

  // Creating state
  const [isCreating, setIsCreating] = useState(false)
  const [newTopic, setNewTopic] = useState('')
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  useEffect(() => {
    // BUG-PLAYGROUND-003 FIX: Clear previous data immediately when dependencies change
    // This prevents showing stale data from a different thread during transitions
    setMemoryData(null)
    setError(null)
    setFreshnessDistribution(null)
    setDecayEnabled(false)
    setArchivePreview(null)

    if (agentId && senderKey) {
      loadMemory()
      loadMemoryStats()
    }
  }, [agentId, senderKey])

  const loadMemory = async () => {
    // BUG-PLAYGROUND-003 FIX: Guard against undefined senderKey
    // If senderKey is undefined, the backend uses fallback logic that returns
    // data from ANY matching sender_key, causing cross-thread data display
    if (!agentId || senderKey === undefined) return
    setLoading(true)
    setError(null)

    try {
      const url = new URL(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/playground/memory/${agentId}`)
      if (senderKey) {
        url.searchParams.set('sender_key', senderKey)
      }

      const response = await authenticatedFetch(url.toString())

      if (response.ok) {
        const data = await response.json()
        setMemoryData(data)
      } else {
        setError('Failed to load memory')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load memory')
    } finally {
      setLoading(false)
    }
  }

  const loadMemoryStats = async () => {
    if (!agentId) return
    try {
      const stats = await api.getAgentMemoryStats(agentId)
      if (stats.decay_config) {
        setDecayEnabled(stats.decay_config.enabled)
      }
      if (stats.freshness_distribution) {
        setFreshnessDistribution(stats.freshness_distribution)
      }
    } catch {
      // Stats are supplementary, don't block on failure
    }
  }

  const handleArchiveDecayed = async () => {
    if (!agentId) return

    if (!archivePreview) {
      // First click: dry run
      setArchiving(true)
      try {
        const result = await api.archiveDecayedFacts(agentId, true)
        if (result.archived_count === 0) {
          alert('No decayed facts to archive.')
          setArchiving(false)
          return
        }
        setArchivePreview({ count: result.archived_count, facts: result.archived_facts || [] })
      } catch (err: any) {
        alert(`Failed to preview archive: ${err.message}`)
      } finally {
        setArchiving(false)
      }
    } else {
      // Execute archive (user already confirmed via preview panel buttons)
      setArchiving(true)
      try {
        await api.archiveDecayedFacts(agentId, false)
        setArchivePreview(null)
        await loadMemory()
        await loadMemoryStats()
      } catch (err: any) {
        alert(`Failed to archive: ${err.message}`)
      } finally {
        setArchiving(false)
      }
    }
  }

  const handleDeleteFact = async (fact: Fact) => {
    if (!agentId) return

    if (!confirm(`Are you sure you want to delete this fact?\n\n${fact.key}: ${fact.value}`)) {
      return
    }

    try {
      let url: string

      if (fact.fact_type === 'project' && fact.project_id) {
        url = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/projects/${fact.project_id}/memory/facts/${fact.id}`
      } else {
        url = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/agents/${agentId}/knowledge/${fact.id}`
      }

      const response = await authenticatedFetch(url, {
        method: 'DELETE'
      })

      if (response.ok) {
        await loadMemory()
      } else {
        alert('Failed to delete fact')
      }
    } catch (err: any) {
      alert(`Error deleting fact: ${err.message}`)
    }
  }

  const handleStartEdit = (fact: Fact) => {
    setEditingFactId(fact.id || null)
    // Remove [Project] prefix if it exists
    setEditingTopic(fact.topic.replace(/^\[Project\]\s*/, ''))
    setEditingKey(fact.key)
    setEditingValue(fact.value)
  }

  const handleCancelEdit = () => {
    setEditingFactId(null)
    setEditingTopic('')
    setEditingKey('')
    setEditingValue('')
  }

  const handleSaveEdit = async (fact: Fact) => {
    if (!agentId || !editingValue.trim()) return

    try {
      let url: string
      let body: any

      if (fact.fact_type === 'project' && fact.project_id) {
        url = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/projects/${fact.project_id}/memory/facts`
        body = {
          topic: editingTopic,
          key: editingKey,
          value: editingValue,
          sender_key: senderKey || null,
          confidence: fact.confidence || 1.0,
          source: 'manual'
        }
      } else {
        // Use the resolved sender_key from backend stats to match the key used when loading facts
        const resolvedUserId = memoryData?.stats.sender_key || senderKey || 'playground'
        url = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/agents/${agentId}/knowledge`
        body = {
          user_id: resolvedUserId,
          topic: editingTopic,
          key: editingKey,
          value: editingValue,
          confidence: fact.confidence || 1.0
        }
      }

      const response = await authenticatedFetch(url, {
        method: 'POST',
        body: JSON.stringify(body)
      })

      if (response.ok) {
        handleCancelEdit()
        await loadMemory()
      } else {
        alert('Failed to update fact')
      }
    } catch (err: any) {
      alert(`Error updating fact: ${err.message}`)
    }
  }

  const handleStartCreate = () => {
    setIsCreating(true)
    setNewTopic('')
    setNewKey('')
    setNewValue('')
  }

  const handleCancelCreate = () => {
    setIsCreating(false)
    setNewTopic('')
    setNewKey('')
    setNewValue('')
  }

  const handleCreateFact = async () => {
    if (!agentId || !newTopic.trim() || !newKey.trim() || !newValue.trim()) {
      alert('Please fill in all fields')
      return
    }

    try {
      let url: string
      let body: any

      // Check if we're in a project context
      const projectId = memoryData?.stats.project_id

      if (projectId) {
        // Create project fact
        url = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/projects/${projectId}/memory/facts`
        body = {
          topic: newTopic,
          key: newKey,
          value: newValue,
          sender_key: senderKey || null,
          confidence: 1.0,
          source: 'manual'
        }
      } else {
        // Create user fact
        // Use the resolved sender_key from backend stats to match the key used when loading facts
        const resolvedUserId = memoryData?.stats.sender_key || senderKey || 'playground'
        url = `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/agents/${agentId}/knowledge`
        body = {
          user_id: resolvedUserId,
          topic: newTopic,
          key: newKey,
          value: newValue,
          confidence: 1.0
        }
      }

      const response = await authenticatedFetch(url, {
        method: 'POST',
        body: JSON.stringify(body)
      })

      if (response.ok) {
        handleCancelCreate()
        await loadMemory()
      } else {
        const errorData = await response.json().catch(() => ({}))
        alert(`Failed to create fact: ${errorData.detail || 'Unknown error'}`)
      }
    } catch (err: any) {
      alert(`Error creating fact: ${err.message}`)
    }
  }

  const formatTimestamp = (ts?: string) => {
    if (!ts) return ''
    try {
      return formatDateTime(ts)
    } catch {
      return ts
    }
  }

  const filteredWorkingMemory = memoryData?.working_memory.filter(m =>
    searchQuery ? m.content.toLowerCase().includes(searchQuery.toLowerCase()) : true
  ) || []

  const filteredFacts = memoryData?.facts.filter(f =>
    searchQuery
      ? f.key.toLowerCase().includes(searchQuery.toLowerCase()) ||
        f.value.toLowerCase().includes(searchQuery.toLowerCase()) ||
        f.topic.toLowerCase().includes(searchQuery.toLowerCase())
      : true
  ) || []

  // Check if any fact has freshness data
  const hasFreshnessData = filteredFacts.some(f => f.freshness)

  return (
    <div className="h-full flex flex-col bg-tsushin-deep">
      {/* Header with Stats */}
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-white/70"><BrainIcon size={18} /></span>
            <h3 className="text-sm font-semibold text-white">Memory Inspector</h3>
          </div>
          <button
            onClick={loadMemory}
            disabled={loading}
            className="p-1.5 rounded-lg text-white/40 hover:text-white hover:bg-white/[0.04] transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        {/* Stats Row */}
        {memoryData && (
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-white/40">Working:</span>
              <span className="text-teal-400 font-medium">{memoryData.stats.working_memory_count}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-white/40">Semantic:</span>
              <span className="text-purple-400 font-medium">{memoryData.stats.semantic_count}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-white/40">Facts:</span>
              <span className="text-amber-400 font-medium">{memoryData.stats.facts_count}</span>
            </div>
          </div>
        )}
      </div>

      {/* Layer Tabs */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-white/[0.06]">
        <button
          onClick={() => setActiveLayer('working')}
          className={`
            px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
            ${activeLayer === 'working'
              ? 'bg-teal-500/20 text-teal-400'
              : 'text-white/50 hover:text-white/70 hover:bg-white/[0.04]'
            }
          `}
        >
          Working Memory
        </button>
        <button
          onClick={() => setActiveLayer('semantic')}
          className={`
            px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
            ${activeLayer === 'semantic'
              ? 'bg-purple-500/20 text-purple-400'
              : 'text-white/50 hover:text-white/70 hover:bg-white/[0.04]'
            }
          `}
        >
          Semantic
        </button>
        <button
          onClick={() => setActiveLayer('facts')}
          className={`
            px-3 py-1.5 rounded-lg text-xs font-medium transition-colors
            ${activeLayer === 'facts'
              ? 'bg-amber-500/20 text-amber-400'
              : 'text-white/50 hover:text-white/70 hover:bg-white/[0.04]'
            }
          `}
        >
          Facts
        </button>
      </div>

      {/* Search */}
      <div className="px-4 py-2 border-b border-white/[0.06]">
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search memory..."
            className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-white placeholder:text-white/30 outline-none focus:border-teal-500/50"
          />
          <svg className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-6 h-6 border-2 border-white/20 border-t-teal-500 rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <span className="text-red-400 mb-2"><AlertTriangleIcon size={48} /></span>
            <p className="text-sm text-red-400">{error}</p>
            <button
              onClick={loadMemory}
              className="mt-3 text-xs text-teal-400 hover:text-teal-300"
            >
              Try again
            </button>
          </div>
        ) : !memoryData ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <span className="text-white/30 mb-2"><InboxIcon size={48} /></span>
            <p className="text-sm text-white/40">No memory data</p>
          </div>
        ) : (
          <>
            {/* Working Memory Layer */}
            {activeLayer === 'working' && (
              <div className="space-y-2">
                {filteredWorkingMemory.length === 0 ? (
                  <p className="text-xs text-white/40 text-center py-4">No messages in working memory</p>
                ) : (
                  filteredWorkingMemory.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`
                        p-3 rounded-lg border text-xs
                        ${msg.role === 'user'
                          ? 'bg-teal-500/5 border-teal-500/20'
                          : 'bg-white/[0.02] border-white/[0.06]'
                        }
                      `}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className={`font-medium ${msg.role === 'user' ? 'text-teal-400' : 'text-white/70'}`}>
                          {msg.role === 'user' ? 'User' : 'Assistant'}
                        </span>
                        <span className="text-white/30">{formatTimestamp(msg.timestamp)}</span>
                      </div>
                      <p className="text-white/80 whitespace-pre-wrap break-words line-clamp-4">{msg.content}</p>
                      {msg.metadata && Object.keys(msg.metadata).length > 0 && (
                        <div className="mt-2 pt-2 border-t border-white/[0.06]">
                          <span className="text-white/40">Metadata: </span>
                          <span className="text-white/60 font-mono break-all whitespace-pre-wrap">{JSON.stringify(msg.metadata)}</span>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Semantic Memory Layer */}
            {activeLayer === 'semantic' && (
              <div className="space-y-2">
                {memoryData.semantic_results.length === 0 ? (
                  <div className="text-center py-8">
                    <span className="block mb-2 text-white/30"><SearchIcon size={48} className="mx-auto" /></span>
                    <p className="text-xs text-white/40">Semantic search results will appear here</p>
                    <p className="text-xs text-white/30 mt-1">Enter a search query above</p>
                  </div>
                ) : (
                  memoryData.semantic_results.map((result, idx) => (
                    <div key={idx} className="p-3 rounded-lg bg-purple-500/5 border border-purple-500/20 text-xs">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-purple-400 font-medium">Match #{idx + 1}</span>
                        <span className="text-white/40">Score: {(result.similarity * 100).toFixed(1)}%</span>
                      </div>
                      <p className="text-white/80 whitespace-pre-wrap">{result.content}</p>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Facts Layer */}
            {activeLayer === 'facts' && (
              <div className="space-y-2">
                {/* Freshness Distribution Summary */}
                {decayEnabled && freshnessDistribution && (
                  <div className="flex items-center gap-3 p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.06] text-xs mb-3">
                    <span className="text-white/40 mr-1">Freshness:</span>
                    {(['fresh', 'fading', 'stale', 'archived'] as const).map(label => {
                      const count = freshnessDistribution[label]
                      const colors = FRESHNESS_COLORS[label]
                      return (
                        <div key={label} className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
                          <span className={colors.text}>{count}</span>
                          <span className="text-white/30">{label}</span>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Archive Decayed Button */}
                {decayEnabled && (
                  <div className="mb-2">
                    {archivePreview ? (
                      <div className="p-2.5 rounded-lg bg-orange-500/10 border border-orange-500/30 text-xs">
                        <p className="text-orange-400 mb-2">
                          {archivePreview.count} fact(s) will be permanently archived.
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleArchiveDecayed}
                            disabled={archiving}
                            className="flex-1 px-3 py-1.5 bg-orange-500/20 text-orange-400 rounded hover:bg-orange-500/30 transition-colors text-xs font-medium disabled:opacity-50"
                          >
                            {archiving ? 'Archiving...' : 'Confirm Archive'}
                          </button>
                          <button
                            onClick={() => setArchivePreview(null)}
                            className="flex-1 px-3 py-1.5 bg-white/[0.04] text-white/60 rounded hover:bg-white/[0.08] transition-colors text-xs"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={handleArchiveDecayed}
                        disabled={archiving}
                        className="w-full p-2 rounded-lg border border-dashed border-orange-500/30 text-orange-400/70 hover:text-orange-400 hover:border-orange-500/50 transition-colors text-xs flex items-center justify-center gap-2 disabled:opacity-50"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                        </svg>
                        {archiving ? 'Checking...' : 'Archive Decayed Facts'}
                      </button>
                    )}
                  </div>
                )}

                {/* Create Fact Button */}
                {!isCreating && (
                  <button
                    onClick={handleStartCreate}
                    className="w-full p-2 rounded-lg border border-dashed border-amber-500/30 text-amber-400/70 hover:text-amber-400 hover:border-amber-500/50 transition-colors text-xs flex items-center justify-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Create New Fact
                  </button>
                )}

                {/* Create Form */}
                {isCreating && (
                  <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 space-y-2">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-amber-400">New Fact</span>
                    </div>
                    <input
                      type="text"
                      value={newTopic}
                      onChange={e => setNewTopic(e.target.value)}
                      placeholder="Topic (e.g., preferences, personal_info)"
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-xs text-white placeholder:text-white/30 outline-none focus:border-amber-500/50"
                    />
                    <input
                      type="text"
                      value={newKey}
                      onChange={e => setNewKey(e.target.value)}
                      placeholder="Key (e.g., favorite_color)"
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-xs text-white placeholder:text-white/30 outline-none focus:border-amber-500/50"
                    />
                    <input
                      type="text"
                      value={newValue}
                      onChange={e => setNewValue(e.target.value)}
                      placeholder="Value (e.g., blue)"
                      className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-xs text-white placeholder:text-white/30 outline-none focus:border-amber-500/50"
                    />
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={handleCreateFact}
                        className="flex-1 px-3 py-1.5 bg-amber-500/20 text-amber-400 rounded hover:bg-amber-500/30 transition-colors text-xs font-medium"
                      >
                        Save
                      </button>
                      <button
                        onClick={handleCancelCreate}
                        className="flex-1 px-3 py-1.5 bg-white/[0.04] text-white/60 rounded hover:bg-white/[0.08] transition-colors text-xs"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Facts List */}
                {filteredFacts.length === 0 && !isCreating ? (
                  <div className="text-center py-8">
                    <span className="block mb-2 text-white/30"><DocumentIcon size={48} className="mx-auto" /></span>
                    <p className="text-xs text-white/40">No learned facts yet</p>
                    <p className="text-xs text-white/30 mt-1">Facts are extracted from conversations</p>
                  </div>
                ) : (
                  filteredFacts.map((fact) => {
                    const isEditing = editingFactId === fact.id
                    const freshness = fact.freshness
                    const freshnessColors = freshness ? FRESHNESS_COLORS[freshness] : null

                    return (
                      <div
                        key={fact.id || `${fact.topic}-${fact.key}`}
                        className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/20 text-xs group"
                      >
                        {isEditing ? (
                          // Edit Mode
                          <div className="space-y-2">
                            <input
                              type="text"
                              value={editingTopic}
                              onChange={e => setEditingTopic(e.target.value)}
                              className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-xs text-white outline-none focus:border-amber-500/50"
                              placeholder="Topic"
                            />
                            <input
                              type="text"
                              value={editingKey}
                              onChange={e => setEditingKey(e.target.value)}
                              className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-xs text-white outline-none focus:border-amber-500/50"
                              placeholder="Key"
                            />
                            <input
                              type="text"
                              value={editingValue}
                              onChange={e => setEditingValue(e.target.value)}
                              className="w-full bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-xs text-white outline-none focus:border-amber-500/50"
                              placeholder="Value"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleSaveEdit(fact)}
                                className="flex-1 px-3 py-1.5 bg-amber-500/20 text-amber-400 rounded hover:bg-amber-500/30 transition-colors text-xs font-medium flex items-center justify-center gap-1"
                              >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                                Save
                              </button>
                              <button
                                onClick={handleCancelEdit}
                                className="flex-1 px-3 py-1.5 bg-white/[0.04] text-white/60 rounded hover:bg-white/[0.08] transition-colors text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          // View Mode
                          <>
                            <div className="flex items-center justify-between mb-1.5">
                              <div className="flex items-center gap-2">
                                <span className="text-amber-400/60 text-[10px] uppercase tracking-wider">{fact.topic}</span>
                                {freshnessColors && (
                                  <div className="flex items-center gap-1">
                                    <span className={`w-1.5 h-1.5 rounded-full ${freshnessColors.dot}`} />
                                    <span className={`text-[10px] ${freshnessColors.text}`}>
                                      {fact.decay_factor !== undefined ? `${Math.round(fact.decay_factor * 100)}%` : freshness}
                                    </span>
                                  </div>
                                )}
                              </div>
                              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                  onClick={() => handleStartEdit(fact)}
                                  className="p-1 text-white/40 hover:text-amber-400 transition-colors"
                                  title="Edit"
                                >
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                  </svg>
                                </button>
                                <button
                                  onClick={() => handleDeleteFact(fact)}
                                  className="p-1 text-white/40 hover:text-red-400 transition-colors"
                                  title="Delete"
                                >
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                  </svg>
                                </button>
                              </div>
                            </div>
                            <div className="flex items-start gap-2">
                              <span className="text-white/60 font-medium">{fact.key}:</span>
                              <span className="text-white/90 flex-1">{fact.value}</span>
                            </div>
                          </>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer - BUG-PLAYGROUND-003 FIX: Enhanced to show thread context clearly */}
      <div className="px-4 py-2 border-t border-white/[0.06] text-xs text-white/30">
        {memoryData?.stats.sender_key ? (
          <>
            Thread: <span className="font-mono text-teal-400/60">{memoryData.stats.sender_key}</span>
            {memoryData.stats.project_id && (
              <span className="ml-3">Project: <span className="font-mono">{memoryData.stats.project_id}</span></span>
            )}
          </>
        ) : (
          <span className="text-white/20 italic">Select a thread to view memory</span>
        )}
      </div>
    </div>
  )
}
