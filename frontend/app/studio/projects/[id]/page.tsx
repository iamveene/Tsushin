'use client'

/**
 * Studio Project Detail Page
 * Full project configuration with tabs for General, KB, Memory, Facts, Conversations, Access
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, Project, ProjectFact, ProjectSemanticMemoryEntry, ProjectDocument, PlaygroundAgentInfo } from '@/lib/client'
import {
  PROJECT_ICON_MAP,
  IconProps,
  SettingsIcon,
  BookOpenIcon,
  BrainIcon,
  LightbulbIcon,
  MessageIcon,
  LockIcon,
  DocumentIcon,
  UserIcon,
  BotIcon,
} from '@/components/ui/icons'

type Tab = 'general' | 'kb' | 'memory' | 'facts' | 'conversations' | 'access'

const PROJECT_COLORS = [
  { name: 'blue', bg: 'bg-blue-500', ring: 'ring-blue-500' },
  { name: 'teal', bg: 'bg-teal-500', ring: 'ring-teal-500' },
  { name: 'indigo', bg: 'bg-indigo-500', ring: 'ring-indigo-500' },
  { name: 'purple', bg: 'bg-purple-500', ring: 'ring-purple-500' },
  { name: 'pink', bg: 'bg-pink-500', ring: 'ring-pink-500' },
  { name: 'orange', bg: 'bg-orange-500', ring: 'ring-orange-500' },
  { name: 'green', bg: 'bg-green-500', ring: 'ring-green-500' },
]

const EMBEDDING_MODELS = [
  { value: 'all-MiniLM-L6-v2', label: 'MiniLM L6 v2 (Fast, Good)' },
  { value: 'all-mpnet-base-v2', label: 'MPNet Base v2 (Better Quality)' },
  { value: 'paraphrase-multilingual-MiniLM-L12-v2', label: 'Multilingual (PT/EN/ES)' },
]

const TABS: { id: Tab; label: string; Icon: React.FC<IconProps> }[] = [
  { id: 'general', label: 'General', Icon: SettingsIcon },
  { id: 'kb', label: 'Knowledge Base', Icon: BookOpenIcon },
  { id: 'memory', label: 'Memory', Icon: BrainIcon },
  { id: 'facts', label: 'Facts', Icon: LightbulbIcon },
  { id: 'conversations', label: 'Conversations', Icon: MessageIcon },
  { id: 'access', label: 'Access', Icon: LockIcon },
]

export default function StudioProjectDetailPage() {
  useRequireAuth()
  const params = useParams()
  const router = useRouter()
  const projectId = Number(params.id)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [activeTab, setActiveTab] = useState<Tab>('general')
  const [project, setProject] = useState<Project | null>(null)
  const [agents, setAgents] = useState<PlaygroundAgentInfo[]>([])
  const [documents, setDocuments] = useState<ProjectDocument[]>([])
  const [facts, setFacts] = useState<ProjectFact[]>([])
  const [memories, setMemories] = useState<ProjectSemanticMemoryEntry[]>([])
  const [projectAgents, setProjectAgents] = useState<number[]>([])

  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Form state for general settings
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    icon: 'folder',
    color: 'blue',
    agent_id: undefined as number | undefined,
    kb_chunk_size: 500,
    kb_chunk_overlap: 50,
    kb_embedding_model: 'all-MiniLM-L6-v2',
    enable_semantic_memory: true,
    semantic_memory_results: 10,
    semantic_similarity_threshold: 0.5,
    enable_factual_memory: true,
    factual_extraction_threshold: 5,
  })

  // New fact form
  const [newFact, setNewFact] = useState({ topic: '', key: '', value: '' })

  const loadProject = useCallback(async () => {
    try {
      const data = await api.getProject(projectId)
      setProject(data)
      setFormData({
        name: data.name,
        description: data.description || '',
        icon: data.icon,
        color: data.color,
        agent_id: data.agent_id || undefined,
        kb_chunk_size: data.kb_chunk_size || 500,
        kb_chunk_overlap: data.kb_chunk_overlap || 50,
        kb_embedding_model: data.kb_embedding_model || 'all-MiniLM-L6-v2',
        enable_semantic_memory: data.enable_semantic_memory ?? true,
        semantic_memory_results: data.semantic_memory_results || 10,
        semantic_similarity_threshold: data.semantic_similarity_threshold || 0.5,
        enable_factual_memory: data.enable_factual_memory ?? true,
        factual_extraction_threshold: data.factual_extraction_threshold || 5,
      })
      setProjectAgents(data.agent_ids || [])
    } catch (err: any) {
      setError(err.message || 'Failed to load project')
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  const loadAgents = useCallback(async () => {
    try {
      const data = await api.getPlaygroundAgents()
      setAgents(data)
    } catch (err) {
      console.error('Failed to load agents:', err)
    }
  }, [])

  const loadDocuments = useCallback(async () => {
    try {
      const data = await api.getProjectDocuments(projectId)
      setDocuments(data)
    } catch (err) {
      console.error('Failed to load documents:', err)
    }
  }, [projectId])

  const loadFacts = useCallback(async () => {
    try {
      const data = await api.getProjectFacts(projectId)
      setFacts(data)
    } catch (err) {
      console.error('Failed to load facts:', err)
    }
  }, [projectId])

  const loadMemories = useCallback(async () => {
    try {
      const data = await api.getProjectSemanticMemory(projectId)
      setMemories(data.memories || [])
    } catch (err) {
      console.error('Failed to load memories:', err)
    }
  }, [projectId])

  useEffect(() => {
    loadProject()
    loadAgents()
    loadDocuments()
    loadFacts()
    loadMemories()
  }, [loadProject, loadAgents, loadDocuments, loadFacts, loadMemories])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      loadProject()
      loadAgents()
      loadDocuments()
      loadFacts()
      loadMemories()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [loadProject, loadAgents, loadDocuments, loadFacts, loadMemories])

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    setSuccess(null)

    try {
      await api.updateProject(projectId, {
        name: formData.name,
        description: formData.description || undefined,
        icon: formData.icon,
        color: formData.color,
        agent_id: formData.agent_id,
        kb_chunk_size: formData.kb_chunk_size,
        kb_chunk_overlap: formData.kb_chunk_overlap,
        kb_embedding_model: formData.kb_embedding_model,
        enable_semantic_memory: formData.enable_semantic_memory,
        semantic_memory_results: formData.semantic_memory_results,
        semantic_similarity_threshold: formData.semantic_similarity_threshold,
        enable_factual_memory: formData.enable_factual_memory,
        factual_extraction_threshold: formData.factual_extraction_threshold,
        agent_ids: projectAgents,
      })
      setSuccess('Project saved successfully')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to save project')
    } finally {
      setIsSaving(false)
    }
  }

  const handleUploadDocument = async (files: FileList) => {
    for (const file of Array.from(files)) {
      try {
        await api.uploadProjectDocument(projectId, file, formData.kb_chunk_size, formData.kb_chunk_overlap)
        setSuccess(`Uploaded ${file.name}`)
      } catch (err: any) {
        setError(err.message || 'Failed to upload document')
      }
    }
    loadDocuments()
    loadProject()
  }

  const handleDeleteDocument = async (docId: number) => {
    if (!confirm('Delete this document and all its chunks?')) return
    try {
      await api.deleteProjectDocument(projectId, docId)
      loadDocuments()
      loadProject()
    } catch (err: any) {
      setError(err.message || 'Failed to delete document')
    }
  }

  const handleAddFact = async () => {
    if (!newFact.topic || !newFact.key || !newFact.value) return
    try {
      await api.addProjectFact(projectId, {
        topic: newFact.topic,
        key: newFact.key,
        value: newFact.value,
        source: 'manual',
      })
      setNewFact({ topic: '', key: '', value: '' })
      loadFacts()
      loadProject()
    } catch (err: any) {
      setError(err.message || 'Failed to add fact')
    }
  }

  const handleDeleteFact = async (factId: number) => {
    try {
      await api.deleteProjectFact(projectId, factId)
      loadFacts()
      loadProject()
    } catch (err: any) {
      setError(err.message || 'Failed to delete fact')
    }
  }

  const handleClearFacts = async () => {
    if (!confirm('Clear ALL facts? This cannot be undone.')) return
    try {
      await api.clearProjectFacts(projectId)
      loadFacts()
      loadProject()
    } catch (err: any) {
      setError(err.message || 'Failed to clear facts')
    }
  }

  const handleClearMemory = async (senderKey?: string) => {
    const msg = senderKey ? `Clear history for ${senderKey}?` : 'Clear ALL conversation history?'
    if (!confirm(msg)) return
    try {
      await api.clearProjectSemanticMemory(projectId, senderKey)
      loadMemories()
      loadProject()
    } catch (err: any) {
      setError(err.message || 'Failed to clear memory')
    }
  }

  const getColorClass = (color: string) => {
    return PROJECT_COLORS.find(c => c.name === color)?.bg || 'bg-blue-500'
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-tsushin-bg via-gray-900 to-gray-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-teal-500/30 border-t-teal-500 rounded-full animate-spin"></div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-tsushin-bg via-gray-900 to-gray-950 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-lg text-white mb-2">Project not found</h2>
          <Link href="/studio/projects" className="text-teal-400 hover:underline">
            Back to projects
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-tsushin-bg via-gray-900 to-gray-950">
      {/* Header */}
      <header className="sticky top-0 z-20 glass-card border-t-0 border-l-0 border-r-0 rounded-none">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/studio/projects" className="text-white/50 hover:text-white transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </Link>
              <div className={`w-10 h-10 rounded-xl ${getColorClass(formData.color)} flex items-center justify-center`}>
                {(() => { const iconEntry = PROJECT_ICON_MAP.find(i => i.label === formData.icon) || PROJECT_ICON_MAP[0]; return <iconEntry.Icon size={20} className="text-white" /> })()}
              </div>
              <div>
                <h1 className="text-lg font-semibold text-white">{formData.name || 'Untitled Project'}</h1>
                <p className="text-xs text-white/50">Project Configuration</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href={`/playground/projects/${projectId}`}
                className="px-4 py-2 text-sm text-white/70 hover:text-white hover:bg-white/10 rounded-lg transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Open in Playground
              </Link>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="btn-primary px-4 py-2 rounded-lg disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Alerts */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center justify-between">
            <span className="text-sm text-red-400">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400/80 hover:text-red-400">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-xl flex items-center justify-between">
            <span className="text-sm text-green-400">{success}</span>
            <button onClick={() => setSuccess(null)} className="text-green-400/80 hover:text-green-400">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex gap-6">
          {/* Tabs Sidebar */}
          <div className="w-48 flex-shrink-0">
            <nav className="space-y-1">
              {TABS.map((tab) => (
                  <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                    ${activeTab === tab.id
                      ? 'bg-teal-500/20 text-teal-400'
                      : 'text-white/60 hover:text-white hover:bg-white/5'}`}
                >
                  <tab.Icon size={16} />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Tab Content */}
          <div className="flex-1 glass-card rounded-2xl p-6">
            {/* General Tab */}
            {activeTab === 'general' && (
              <div className="space-y-6">
                <h2 className="text-lg font-semibold text-white">General Settings</h2>

                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Project Name</label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Default Agent</label>
                    <select
                      value={formData.agent_id || ''}
                      onChange={(e) => setFormData({ ...formData, agent_id: e.target.value ? Number(e.target.value) : undefined })}
                      className="input w-full"
                    >
                      <option value="">Use system default</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>{agent.name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-white/70 mb-1.5">Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="input w-full resize-none"
                    rows={3}
                  />
                </div>

                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Icon</label>
                    <div className="flex flex-wrap gap-1.5">
                      {PROJECT_ICON_MAP.map((entry) => (
                        <button
                          key={entry.label}
                          type="button"
                          onClick={() => setFormData({ ...formData, icon: entry.label })}
                          className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all ${
                            formData.icon === entry.label ? 'bg-teal-500/20 ring-2 ring-teal-500' : 'bg-white/5 hover:bg-white/10'
                          }`}
                        >
                          <entry.Icon size={18} className="text-white" />
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Color</label>
                    <div className="flex gap-2">
                      {PROJECT_COLORS.map((color) => (
                        <button
                          key={color.name}
                          type="button"
                          onClick={() => setFormData({ ...formData, color: color.name })}
                          className={`w-8 h-8 rounded-full ${color.bg} transition-all ${
                            formData.color === color.name ? 'ring-2 ring-offset-2 ring-offset-[#14141f] ring-white' : 'opacity-50 hover:opacity-100'
                          }`}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Knowledge Base Tab */}
            {activeTab === 'kb' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-white">Knowledge Base</h2>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.txt,.csv,.json,.xlsx,.docx,.md"
                    onChange={(e) => e.target.files && handleUploadDocument(e.target.files)}
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="btn-primary px-4 py-2 rounded-lg text-sm flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    Upload Document
                  </button>
                </div>

                {/* Embedding Settings */}
                <div className="p-4 bg-white/5 rounded-xl space-y-4">
                  <h3 className="text-sm font-medium text-white">Chunking Settings</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs text-white/50 mb-1">Embedding Model</label>
                      <select
                        value={formData.kb_embedding_model}
                        onChange={(e) => setFormData({ ...formData, kb_embedding_model: e.target.value })}
                        className="input w-full text-sm"
                      >
                        {EMBEDDING_MODELS.map((m) => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-white/50 mb-1">Chunk Size</label>
                      <input
                        type="number"
                        value={formData.kb_chunk_size}
                        onChange={(e) => setFormData({ ...formData, kb_chunk_size: Number(e.target.value) })}
                        className="input w-full text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-white/50 mb-1">Chunk Overlap</label>
                      <input
                        type="number"
                        value={formData.kb_chunk_overlap}
                        onChange={(e) => setFormData({ ...formData, kb_chunk_overlap: Number(e.target.value) })}
                        className="input w-full text-sm"
                      />
                    </div>
                  </div>
                </div>

                {/* Documents List */}
                <div>
                  <h3 className="text-sm font-medium text-white mb-3">Documents ({documents.length})</h3>
                  {documents.length === 0 ? (
                    <div className="text-center py-8 text-white/40 bg-white/5 rounded-xl">
                      No documents uploaded yet
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {documents.map((doc) => (
                        <div key={doc.id} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg group">
                          <DocumentIcon size={18} className="text-blue-400" />
                          <div className="flex-1">
                            <p className="text-sm text-white">{doc.name}</p>
                            <p className="text-xs text-white/40">{doc.num_chunks} chunks • {Math.round(doc.size_bytes / 1024)}KB • {doc.status}</p>
                          </div>
                          <button
                            onClick={() => handleDeleteDocument(doc.id)}
                            className="p-2 text-white/40 hover:text-red-400 hover:bg-red-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Memory Tab */}
            {activeTab === 'memory' && (
              <div className="space-y-6">
                <h2 className="text-lg font-semibold text-white">Memory Configuration</h2>

                {/* Semantic Memory */}
                <div className="p-4 bg-white/5 rounded-xl space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-medium text-white">Semantic Memory</h3>
                      <p className="text-xs text-white/50">Store conversation history with semantic search</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, enable_semantic_memory: !formData.enable_semantic_memory })}
                      className={`w-12 h-6 rounded-full transition-colors ${formData.enable_semantic_memory ? 'bg-teal-500' : 'bg-white/20'}`}
                    >
                      <div className={`w-5 h-5 rounded-full bg-white transition-transform ${formData.enable_semantic_memory ? 'translate-x-6' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                  {formData.enable_semantic_memory && (
                    <div className="grid grid-cols-2 gap-4 pt-2 border-t border-white/10">
                      <div>
                        <label className="block text-xs text-white/50 mb-1">Max Results</label>
                        <input
                          type="number"
                          value={formData.semantic_memory_results}
                          onChange={(e) => setFormData({ ...formData, semantic_memory_results: Number(e.target.value) })}
                          className="input w-full text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-white/50 mb-1">Similarity Threshold</label>
                        <input
                          type="number"
                          value={formData.semantic_similarity_threshold}
                          onChange={(e) => setFormData({ ...formData, semantic_similarity_threshold: Number(e.target.value) })}
                          className="input w-full text-sm"
                          step={0.1}
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Factual Memory */}
                <div className="p-4 bg-white/5 rounded-xl space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-medium text-white">Factual Memory</h3>
                      <p className="text-xs text-white/50">Extract and store facts from conversations</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, enable_factual_memory: !formData.enable_factual_memory })}
                      className={`w-12 h-6 rounded-full transition-colors ${formData.enable_factual_memory ? 'bg-purple-500' : 'bg-white/20'}`}
                    >
                      <div className={`w-5 h-5 rounded-full bg-white transition-transform ${formData.enable_factual_memory ? 'translate-x-6' : 'translate-x-0.5'}`} />
                    </button>
                  </div>
                  {formData.enable_factual_memory && (
                    <div className="pt-2 border-t border-white/10">
                      <label className="block text-xs text-white/50 mb-1">Extraction Threshold (messages)</label>
                      <input
                        type="number"
                        value={formData.factual_extraction_threshold}
                        onChange={(e) => setFormData({ ...formData, factual_extraction_threshold: Number(e.target.value) })}
                        className="input w-full text-sm"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Facts Tab */}
            {activeTab === 'facts' && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-white">Facts ({facts.length})</h2>
                  {facts.length > 0 && (
                    <button onClick={handleClearFacts} className="text-sm text-red-400 hover:text-red-300">
                      Clear All
                    </button>
                  )}
                </div>

                {/* Add Fact Form */}
                <div className="p-4 bg-white/5 rounded-xl space-y-3">
                  <h3 className="text-sm font-medium text-white">Add New Fact</h3>
                  <div className="grid grid-cols-3 gap-3">
                    <input
                      type="text"
                      placeholder="Topic"
                      value={newFact.topic}
                      onChange={(e) => setNewFact({ ...newFact, topic: e.target.value })}
                      className="input text-sm"
                    />
                    <input
                      type="text"
                      placeholder="Key"
                      value={newFact.key}
                      onChange={(e) => setNewFact({ ...newFact, key: e.target.value })}
                      className="input text-sm"
                    />
                    <input
                      type="text"
                      placeholder="Value"
                      value={newFact.value}
                      onChange={(e) => setNewFact({ ...newFact, value: e.target.value })}
                      className="input text-sm"
                    />
                  </div>
                  <button
                    onClick={handleAddFact}
                    disabled={!newFact.topic || !newFact.key || !newFact.value}
                    className="btn-primary px-4 py-2 rounded-lg text-sm disabled:opacity-50"
                  >
                    Add Fact
                  </button>
                </div>

                {/* Facts List */}
                {facts.length === 0 ? (
                  <div className="text-center py-8 text-white/40 bg-white/5 rounded-xl">
                    No facts yet
                  </div>
                ) : (
                  <div className="space-y-4">
                    {Object.entries(
                      facts.reduce((acc, f) => {
                        if (!acc[f.topic]) acc[f.topic] = []
                        acc[f.topic].push(f)
                        return acc
                      }, {} as Record<string, ProjectFact[]>)
                    ).map(([topic, topicFacts]) => (
                      <div key={topic}>
                        <h4 className="text-xs text-white/50 uppercase tracking-wider mb-2">{topic}</h4>
                        <div className="space-y-1">
                          {topicFacts.map((fact) => (
                            <div key={fact.id} className="flex items-center gap-3 p-2 bg-white/5 rounded-lg group">
                              <span className="text-white/50 text-sm font-mono">{fact.key}:</span>
                              <span className="flex-1 text-sm text-white">{fact.value}</span>
                              <span className="text-xs text-white/30">{fact.source}</span>
                              <button
                                onClick={() => handleDeleteFact(fact.id)}
                                className="p-1 text-white/40 hover:text-red-400 opacity-0 group-hover:opacity-100"
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
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-white">Conversation History ({memories.length})</h2>
                  {memories.length > 0 && (
                    <button onClick={() => handleClearMemory()} className="text-sm text-red-400 hover:text-red-300">
                      Clear All
                    </button>
                  )}
                </div>

                {memories.length === 0 ? (
                  <div className="text-center py-8 text-white/40 bg-white/5 rounded-xl">
                    No conversation history yet
                  </div>
                ) : (
                  <div className="space-y-4">
                    {Object.entries(
                      memories.reduce((acc, m) => {
                        if (!acc[m.sender_key]) acc[m.sender_key] = []
                        acc[m.sender_key].push(m)
                        return acc
                      }, {} as Record<string, ProjectSemanticMemoryEntry[]>)
                    ).map(([sender, senderMemories]) => (
                      <div key={sender} className="p-4 bg-white/5 rounded-xl">
                        <div className="flex items-center justify-between mb-3">
                          <h4 className="text-sm font-medium text-white inline-flex items-center gap-1"><UserIcon size={14} /> {sender} ({senderMemories.length} messages)</h4>
                          <button onClick={() => handleClearMemory(sender)} className="text-xs text-red-400 hover:text-red-300">
                            Clear User
                          </button>
                        </div>
                        <div className="space-y-2 max-h-40 overflow-y-auto">
                          {senderMemories.slice(0, 10).map((m, idx) => (
                            <div key={idx} className={`p-2 rounded-lg text-xs ${m.role === 'user' ? 'bg-blue-500/10 text-blue-100' : 'bg-white/5 text-white/70'}`}>
                              <span className="text-white/40 mr-2">{m.role}:</span>
                              {m.content.length > 150 ? `${m.content.substring(0, 150)}...` : m.content}
                            </div>
                          ))}
                          {senderMemories.length > 10 && (
                            <p className="text-xs text-white/40 text-center">+{senderMemories.length - 10} more</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Access Tab */}
            {activeTab === 'access' && (
              <div className="space-y-6">
                <h2 className="text-lg font-semibold text-white">Agent Access</h2>
                <p className="text-sm text-white/50">Select which agents can interact with this project.</p>

                <div className="space-y-2">
                  {agents.map((agent) => (
                    <label key={agent.id} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg cursor-pointer hover:bg-white/10 transition-colors">
                      <input
                        type="checkbox"
                        checked={projectAgents.includes(agent.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setProjectAgents([...projectAgents, agent.id])
                          } else {
                            setProjectAgents(projectAgents.filter(id => id !== agent.id))
                          }
                        }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-teal-500 focus:ring-teal-500"
                      />
                      <BotIcon size={18} className="text-teal-400" />
                      <div>
                        <p className="text-sm text-white">{agent.name}</p>
                        <p className="text-xs text-white/40">{agent.is_active ? 'Active' : 'Inactive'}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
