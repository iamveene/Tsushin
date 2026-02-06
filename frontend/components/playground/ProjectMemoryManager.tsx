'use client'

/**
 * Phase 16: Project Memory Manager Component
 *
 * Tabbed interface for managing project memory:
 * - Knowledge Base: Document management
 * - Facts: Add/edit/delete learned facts
 * - Conversations: View and manage conversation history
 */

import React, { useState, useEffect, useCallback } from 'react'
import { api, ProjectFact, ProjectSemanticMemoryEntry, ProjectMemoryStats, PlaygroundDocument } from '@/lib/client'
import {
  BookIcon,
  BrainIcon,
  MessageIcon,
  UserIcon,
  FileIcon
} from '@/components/ui/icons'

interface ProjectMemoryManagerProps {
  projectId: number
  projectName: string
  isOpen: boolean
  onClose: () => void
}

type Tab = 'kb' | 'facts' | 'conversations'

export default function ProjectMemoryManager({
  projectId,
  projectName,
  isOpen,
  onClose
}: ProjectMemoryManagerProps) {
  const [activeTab, setActiveTab] = useState<Tab>('kb')
  const [stats, setStats] = useState<ProjectMemoryStats | null>(null)
  const [facts, setFacts] = useState<ProjectFact[]>([])
  const [memories, setMemories] = useState<ProjectSemanticMemoryEntry[]>([])
  const [documents, setDocuments] = useState<PlaygroundDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // New fact form state
  const [newFactTopic, setNewFactTopic] = useState('')
  const [newFactKey, setNewFactKey] = useState('')
  const [newFactValue, setNewFactValue] = useState('')

  // Load data when opened
  useEffect(() => {
    if (isOpen && projectId) {
      loadStats()
      loadFacts()
      loadMemories()
      loadDocuments()
    }
  }, [isOpen, projectId])

  const loadStats = async () => {
    try {
      const data = await api.getProjectMemoryStats(projectId)
      setStats(data)
    } catch (err) {
      console.error('Failed to load stats:', err)
    }
  }

  const loadFacts = async () => {
    try {
      const data = await api.getProjectFacts(projectId)
      setFacts(data)
    } catch (err) {
      console.error('Failed to load facts:', err)
    }
  }

  const loadMemories = async () => {
    try {
      const data = await api.getProjectSemanticMemory(projectId)
      setMemories(data.memories)
    } catch (err) {
      console.error('Failed to load memories:', err)
    }
  }

  const loadDocuments = async () => {
    try {
      const data = await api.getProjectDocuments(projectId)
      setDocuments(data)
    } catch (err) {
      console.error('Failed to load documents:', err)
    }
  }

  const handleAddFact = async () => {
    if (!newFactTopic || !newFactKey || !newFactValue) return

    setLoading(true)
    try {
      await api.addProjectFact(projectId, {
        topic: newFactTopic,
        key: newFactKey,
        value: newFactValue,
        source: 'manual'
      })
      setNewFactTopic('')
      setNewFactKey('')
      setNewFactValue('')
      await loadFacts()
      await loadStats()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteFact = async (factId: number) => {
    if (!confirm('Are you sure you want to delete this fact?')) return

    try {
      await api.deleteProjectFact(projectId, factId)
      await loadFacts()
      await loadStats()
    } catch (err: any) {
      setError(err.message)
    }
  }

  const handleClearFacts = async () => {
    if (!confirm('Are you sure you want to clear ALL facts? This cannot be undone.')) return

    setLoading(true)
    try {
      await api.clearProjectFacts(projectId)
      await loadFacts()
      await loadStats()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleClearMemory = async (senderKey?: string) => {
    const msg = senderKey
      ? `Clear conversation history for user ${senderKey}?`
      : 'Clear ALL conversation history? This cannot be undone.'
    if (!confirm(msg)) return

    setLoading(true)
    try {
      await api.clearProjectSemanticMemory(projectId, senderKey)
      await loadMemories()
      await loadStats()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl max-h-[80vh] bg-[#14141f] border border-white/10 rounded-2xl overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div>
            <h2 className="text-lg font-semibold text-white">Project Memory</h2>
            <p className="text-sm text-white/50">{projectName}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Stats Bar */}
        {stats && (
          <div className="flex items-center gap-6 px-6 py-3 bg-white/5 border-b border-white/10 text-sm">
            <span className="text-white/50 flex items-center gap-1.5"><BookIcon size={14} /> {stats.kb_document_count} docs</span>
            <span className="text-white/50 flex items-center gap-1.5"><BrainIcon size={14} /> {stats.fact_count} facts</span>
            <span className="text-white/50 flex items-center gap-1.5"><MessageIcon size={14} /> {stats.semantic_memory_count} memories</span>
            <span className="text-white/50 flex items-center gap-1.5"><UserIcon size={14} /> {stats.unique_users} users</span>
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-white/10">
          {[
            { id: 'kb', label: 'Knowledge Base', icon: <BookIcon size={14} />, count: stats?.kb_document_count },
            { id: 'facts', label: 'Facts', icon: <BrainIcon size={14} />, count: stats?.fact_count },
            { id: 'conversations', label: 'Conversations', icon: <MessageIcon size={14} />, count: stats?.semantic_memory_count },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as Tab)}
              className={`
                flex-1 px-4 py-3 text-sm font-medium transition-colors
                ${activeTab === tab.id
                  ? 'text-teal-400 border-b-2 border-teal-400 bg-white/5'
                  : 'text-white/60 hover:text-white hover:bg-white/5'}
              `}
            >
              <span className="flex items-center gap-1.5">{tab.icon} {tab.label}</span>
              {tab.count !== undefined && (
                <span className="ml-2 text-xs bg-white/10 px-1.5 py-0.5 rounded">{tab.count}</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="p-6 overflow-y-auto" style={{ maxHeight: 'calc(80vh - 200px)' }}>
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
              <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
            </div>
          )}

          {/* Knowledge Base Tab */}
          {activeTab === 'kb' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white font-medium">Documents</h3>
                <span className="text-sm text-white/50">
                  Manage documents in Studio → Projects
                </span>
              </div>
              {documents.length === 0 ? (
                <div className="text-center py-8 text-white/40">
                  No documents uploaded yet
                </div>
              ) : (
                <div className="space-y-2">
                  {documents.map(doc => (
                    <div
                      key={doc.id}
                      className="flex items-center gap-3 p-3 bg-white/5 rounded-lg"
                    >
                      <span className="flex items-center justify-center w-5 h-5"><FileIcon size={18} /></span>
                      <div className="flex-1">
                        <p className="text-white text-sm">{doc.name}</p>
                        <p className="text-white/40 text-xs">{doc.num_chunks} chunks • {Math.round(doc.size_bytes / 1024)}KB</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Facts Tab */}
          {activeTab === 'facts' && (
            <div>
              {/* Add Fact Form */}
              <div className="mb-6 p-4 bg-white/5 rounded-xl">
                <h4 className="text-white text-sm font-medium mb-3">Add New Fact</h4>
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <input
                    type="text"
                    placeholder="Topic (e.g., company_info)"
                    value={newFactTopic}
                    onChange={e => setNewFactTopic(e.target.value)}
                    className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder:text-white/30 outline-none focus:border-teal-500/50"
                  />
                  <input
                    type="text"
                    placeholder="Key (e.g., name)"
                    value={newFactKey}
                    onChange={e => setNewFactKey(e.target.value)}
                    className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder:text-white/30 outline-none focus:border-teal-500/50"
                  />
                  <input
                    type="text"
                    placeholder="Value"
                    value={newFactValue}
                    onChange={e => setNewFactValue(e.target.value)}
                    className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm placeholder:text-white/30 outline-none focus:border-teal-500/50"
                  />
                </div>
                <button
                  onClick={handleAddFact}
                  disabled={loading || !newFactTopic || !newFactKey || !newFactValue}
                  className="px-4 py-2 bg-teal-500 text-white text-sm font-medium rounded-lg hover:bg-teal-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Add Fact
                </button>
              </div>

              {/* Facts List */}
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-white text-sm font-medium">Learned Facts ({facts.length})</h4>
                {facts.length > 0 && (
                  <button
                    onClick={handleClearFacts}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Clear All
                  </button>
                )}
              </div>
              {facts.length === 0 ? (
                <div className="text-center py-8 text-white/40">
                  No facts yet. Add some above or let the AI learn from conversations.
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Group by topic */}
                  {Object.entries(
                    facts.reduce((acc, fact) => {
                      if (!acc[fact.topic]) acc[fact.topic] = []
                      acc[fact.topic].push(fact)
                      return acc
                    }, {} as Record<string, ProjectFact[]>)
                  ).map(([topic, topicFacts]) => (
                    <div key={topic} className="mb-4">
                      <h5 className="text-xs text-white/50 uppercase tracking-wider mb-2">{topic}</h5>
                      <div className="space-y-1">
                        {topicFacts.map(fact => (
                          <div
                            key={fact.id}
                            className="flex items-center gap-3 p-2 bg-white/5 rounded-lg group"
                          >
                            <span className="text-white/50 text-sm font-mono">{fact.key}:</span>
                            <span className="flex-1 text-white text-sm">{fact.value}</span>
                            <span className="text-xs text-white/30">{fact.source}</span>
                            <button
                              onClick={() => handleDeleteFact(fact.id)}
                              className="opacity-0 group-hover:opacity-100 p-1 text-red-400 hover:text-red-300 transition-opacity"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Conversations Tab */}
          {activeTab === 'conversations' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-white text-sm font-medium">Conversation History ({memories.length})</h4>
                {memories.length > 0 && (
                  <button
                    onClick={() => handleClearMemory()}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Clear All
                  </button>
                )}
              </div>

              {memories.length === 0 ? (
                <div className="text-center py-8 text-white/40">
                  No conversation history yet
                </div>
              ) : (
                <div>
                  {/* Group by sender */}
                  {Object.entries(
                    memories.reduce((acc, mem) => {
                      if (!acc[mem.sender_key]) acc[mem.sender_key] = []
                      acc[mem.sender_key].push(mem)
                      return acc
                    }, {} as Record<string, ProjectSemanticMemoryEntry[]>)
                  ).map(([sender, senderMemories]) => (
                    <div key={sender} className="mb-6">
                      <div className="flex items-center justify-between mb-2">
                        <h5 className="text-xs text-white/50 uppercase tracking-wider">
                          <span className="inline-flex items-center gap-1"><UserIcon size={14} /> {sender} ({senderMemories.length} messages)</span>
                        </h5>
                        <button
                          onClick={() => handleClearMemory(sender)}
                          className="text-xs text-red-400 hover:text-red-300"
                        >
                          Clear User
                        </button>
                      </div>
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {senderMemories.slice(0, 20).map((mem, idx) => (
                          <div
                            key={idx}
                            className={`p-2 rounded-lg text-sm ${
                              mem.role === 'user' ? 'bg-blue-500/10 text-blue-100' : 'bg-white/5 text-white/80'
                            }`}
                          >
                            <span className="text-xs text-white/40 mr-2">{mem.role}:</span>
                            {mem.content.length > 200 ? `${mem.content.substring(0, 200)}...` : mem.content}
                          </div>
                        ))}
                        {senderMemories.length > 20 && (
                          <p className="text-xs text-white/40 text-center py-2">
                            +{senderMemories.length - 20} more messages
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
