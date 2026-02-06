'use client'

/**
 * Studio Projects Page
 * Full project management with configuration, KB settings, and memory management.
 */

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, Project, PlaygroundAgentInfo } from '@/lib/client'
import {
  IconProps,
  FolderIcon,
  FolderOpenIcon,
  ChartBarIcon,
  TrendingUpIcon,
  DocumentIcon,
  MicroscopeIcon,
  ScaleIcon,
  BriefcaseIcon,
  TargetIcon,
  RocketIcon,
  LightbulbIcon,
  SearchIcon,
  FileIcon,
  BrainIcon,
  MessageIcon,
} from '@/components/ui/icons'

const PROJECT_COLORS = [
  { name: 'blue', bg: 'bg-blue-500', ring: 'ring-blue-500' },
  { name: 'teal', bg: 'bg-teal-500', ring: 'ring-teal-500' },
  { name: 'indigo', bg: 'bg-indigo-500', ring: 'ring-indigo-500' },
  { name: 'purple', bg: 'bg-purple-500', ring: 'ring-purple-500' },
  { name: 'pink', bg: 'bg-pink-500', ring: 'ring-pink-500' },
  { name: 'orange', bg: 'bg-orange-500', ring: 'ring-orange-500' },
  { name: 'green', bg: 'bg-green-500', ring: 'ring-green-500' },
]

// Project icons as React components
const PROJECT_ICON_COMPONENTS: Array<{ Icon: React.FC<IconProps>; id: string }> = [
  { Icon: FolderIcon, id: 'folder' },
  { Icon: FolderOpenIcon, id: 'folder-open' },
  { Icon: ChartBarIcon, id: 'chart' },
  { Icon: TrendingUpIcon, id: 'trending' },
  { Icon: DocumentIcon, id: 'document' },
  { Icon: MicroscopeIcon, id: 'research' },
  { Icon: ScaleIcon, id: 'legal' },
  { Icon: BriefcaseIcon, id: 'business' },
  { Icon: TargetIcon, id: 'target' },
  { Icon: RocketIcon, id: 'rocket' },
  { Icon: LightbulbIcon, id: 'idea' },
  { Icon: SearchIcon, id: 'search' },
]

// Helper to get icon component by id
const getProjectIconById = (iconId: string): React.FC<IconProps> => {
  const found = PROJECT_ICON_COMPONENTS.find(item => item.id === iconId)
  return found?.Icon || FolderIcon
}

const EMBEDDING_MODELS = [
  // Local/Open Source Models
  { value: 'all-MiniLM-L6-v2', label: 'MiniLM L6 v2 (Fast, Local)' },
  { value: 'all-mpnet-base-v2', label: 'MPNet Base v2 (Better Quality, Local)' },
  { value: 'paraphrase-multilingual-MiniLM-L12-v2', label: 'Multilingual MiniLM (PT/EN/ES, Local)' },
  // OpenAI Models
  { value: 'text-embedding-3-small', label: 'OpenAI text-embedding-3-small (Fast, API)' },
  { value: 'text-embedding-3-large', label: 'OpenAI text-embedding-3-large (Best, API)' },
  { value: 'text-embedding-ada-002', label: 'OpenAI Ada 002 (Legacy, API)' },
  // Google Gemini Models
  { value: 'text-embedding-004', label: 'Gemini text-embedding-004 (Latest, API)' },
  { value: 'embedding-001', label: 'Gemini embedding-001 (Stable, API)' },
]

export default function StudioProjectsPage() {
  useRequireAuth()
  const router = useRouter()
  const pathname = usePathname()

  const [projects, setProjects] = useState<Project[]>([])
  const [agents, setAgents] = useState<PlaygroundAgentInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [isCreating, setIsCreating] = useState(false)

  // New project form state
  const [newProject, setNewProject] = useState({
    name: '',
    description: '',
    icon: 'folder',
    color: 'blue',
    agent_id: undefined as number | undefined,
    // KB Configuration
    kb_chunk_size: 500,
    kb_chunk_overlap: 50,
    kb_embedding_model: 'all-MiniLM-L6-v2',
    // Memory Configuration
    enable_semantic_memory: true,
    semantic_memory_results: 10,
    semantic_similarity_threshold: 0.5,
    enable_factual_memory: true,
    factual_extraction_threshold: 5,
  })

  const loadProjects = useCallback(async () => {
    try {
      const data = await api.getProjects()
      setProjects(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load projects')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const loadAgents = useCallback(async () => {
    try {
      const data = await api.getPlaygroundAgents()
      setAgents(data)
    } catch (err) {
      console.error('Failed to load agents:', err)
    }
  }, [])

  useEffect(() => {
    loadProjects()
    loadAgents()
  }, [loadProjects, loadAgents])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      loadProjects()
      loadAgents()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [loadProjects, loadAgents])

  const handleCreateProject = async () => {
    if (!newProject.name.trim()) {
      setError('Project name is required')
      return
    }

    setIsCreating(true)
    setError(null)

    try {
      const project = await api.createProject({
        name: newProject.name,
        description: newProject.description || undefined,
        icon: newProject.icon,
        color: newProject.color,
        agent_id: newProject.agent_id,
        kb_chunk_size: newProject.kb_chunk_size,
        kb_chunk_overlap: newProject.kb_chunk_overlap,
        kb_embedding_model: newProject.kb_embedding_model,
        enable_semantic_memory: newProject.enable_semantic_memory,
        semantic_memory_results: newProject.semantic_memory_results,
        semantic_similarity_threshold: newProject.semantic_similarity_threshold,
        enable_factual_memory: newProject.enable_factual_memory,
        factual_extraction_threshold: newProject.factual_extraction_threshold,
      })

      setShowCreateModal(false)
      resetForm()
      router.push(`/agents/projects/${project.id}`)
    } catch (err: any) {
      setError(err.message || 'Failed to create project')
    } finally {
      setIsCreating(false)
    }
  }

  const resetForm = () => {
    setNewProject({
      name: '',
      description: '',
      icon: 'folder',
      color: 'blue',
      agent_id: undefined,
      kb_chunk_size: 500,
      kb_chunk_overlap: 50,
      kb_embedding_model: 'all-MiniLM-L6-v2',
      enable_semantic_memory: true,
      semantic_memory_results: 10,
      semantic_similarity_threshold: 0.5,
      enable_factual_memory: true,
      factual_extraction_threshold: 5,
    })
  }

  const handleDeleteProject = async (projectId: number, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()

    if (!confirm('Are you sure you want to delete this project? This will delete all documents, conversations, and memory. This action cannot be undone.')) {
      return
    }

    try {
      await api.deleteProject(projectId)
      loadProjects()
    } catch (err: any) {
      setError(err.message || 'Failed to delete project')
    }
  }

  const getColorClass = (color: string) => {
    return PROJECT_COLORS.find(c => c.name === color)?.bg || 'bg-blue-500'
  }

  return (
    <div className="min-h-screen animate-fade-in">
      {/* Header */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-display font-bold text-white mb-2">Projects</h1>
            <p className="text-tsushin-slate">Configure project workspaces, knowledge bases, and memory</p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Project
          </button>
        </div>
      </div>

      {/* Sub Navigation */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="border-b border-tsushin-border/50">
            <nav className="flex">
              <Link
                href="/agents"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">
                  Agents
                </span>
                {pathname === '/agents' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/contacts"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents/contacts'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">
                  Contacts
                </span>
                {pathname === '/agents/contacts' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/personas"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname === '/agents/personas'
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">
                  Personas
                </span>
                {pathname === '/agents/personas' && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
              <Link
                href="/agents/projects"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname?.startsWith('/agents/projects')
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">
                  Projects
                </span>
                {pathname?.startsWith('/agents/projects') && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                )}
              </Link>
            </nav>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3">
            <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="text-sm text-red-400">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-red-400/80 hover:text-red-400">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Loading */}
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 border-2 border-teal-500/30 border-t-teal-500 rounded-full animate-spin"></div>
          </div>
        ) : projects.length === 0 ? (
          /* Empty State */
          <div className="glass-card rounded-xl p-16 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-tsushin-surface flex items-center justify-center">
              <FolderOpenIcon size={32} className="text-teal-400" />
            </div>
            <h3 className="text-lg font-medium text-tsushin-pearl mb-2">No projects yet</h3>
            <p className="text-sm text-tsushin-slate mb-6 max-w-md mx-auto">
              Create your first project to organize documents, configure knowledge bases, and manage memory systems.
            </p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="btn-primary px-6 py-2.5 rounded-lg inline-flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create Project
            </button>
          </div>
        ) : (
          /* Projects Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects.map((project) => (
              <Link
                key={project.id}
                href={`/agents/projects/${project.id}`}
                className="glass-card p-6 rounded-xl hover:border-white/20 transition-all group"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className={`w-12 h-12 rounded-xl ${getColorClass(project.color)} flex items-center justify-center`}>
                    {(() => {
                      const ProjectIcon = getProjectIconById(project.icon)
                      return <ProjectIcon size={24} className="text-white" />
                    })()}
                  </div>
                  <button
                    onClick={(e) => handleDeleteProject(project.id, e)}
                    className="p-2 text-tsushin-slate hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
                <h3 className="font-semibold text-tsushin-pearl mb-1">{project.name}</h3>
                {project.description && (
                  <p className="text-sm text-tsushin-slate mb-4 line-clamp-2">{project.description}</p>
                )}

                {/* Stats */}
                <div className="flex flex-wrap gap-3 text-xs text-tsushin-muted">
                  <span className="flex items-center gap-1">
                    <FileIcon size={12} />
                    {project.document_count || 0} docs
                  </span>
                  <span className="flex items-center gap-1">
                    <BrainIcon size={12} />
                    {project.fact_count || 0} facts
                  </span>
                  <span className="flex items-center gap-1">
                    <MessageIcon size={12} />
                    {project.conversation_count || 0} convos
                  </span>
                </div>

                {/* Memory Config Badges */}
                <div className="mt-3 pt-3 border-t border-white/5 flex flex-wrap gap-1.5">
                  {project.enable_semantic_memory && (
                    <span className="text-2xs px-2 py-0.5 bg-teal-500/20 text-teal-400 rounded-full">Semantic</span>
                  )}
                  {project.enable_factual_memory && (
                    <span className="text-2xs px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded-full">Factual</span>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm overflow-y-auto py-8">
          <div className="glass-card w-full max-w-2xl rounded-2xl shadow-2xl my-auto mx-4">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-lg font-semibold text-white">Create Project</h2>
              <button
                onClick={() => { setShowCreateModal(false); resetForm() }}
                className="p-2 text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 max-h-[70vh] overflow-y-auto space-y-6">
              {/* Basic Info Section */}
              <div>
                <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                  <span className="w-6 h-6 rounded bg-teal-500/20 flex items-center justify-center text-xs">1</span>
                  Basic Information
                </h3>
                <div className="space-y-4">
                  {/* Name */}
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Project Name *</label>
                    <input
                      type="text"
                      value={newProject.name}
                      onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                      className="input w-full"
                      placeholder="ACME Research"
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Description</label>
                    <textarea
                      value={newProject.description}
                      onChange={(e) => setNewProject({ ...newProject, description: e.target.value })}
                      className="input w-full resize-none"
                      rows={2}
                      placeholder="What is this project about?"
                    />
                  </div>

                  {/* Icon & Color */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm text-white/70 mb-1.5">Icon</label>
                      <div className="flex flex-wrap gap-1.5">
                        {PROJECT_ICON_COMPONENTS.map(({ Icon, id }) => (
                          <button
                            key={id}
                            type="button"
                            onClick={() => setNewProject({ ...newProject, icon: id })}
                            className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all ${
                              newProject.icon === id
                                ? 'bg-teal-500/20 ring-2 ring-teal-500'
                                : 'bg-white/5 hover:bg-white/10'
                            }`}
                          >
                            <Icon size={18} className="text-white" />
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
                            onClick={() => setNewProject({ ...newProject, color: color.name })}
                            className={`w-8 h-8 rounded-full ${color.bg} transition-all ${
                              newProject.color === color.name
                                ? 'ring-2 ring-offset-2 ring-offset-[#14141f] ring-white'
                                : 'opacity-50 hover:opacity-100'
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Agent */}
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Default Agent</label>
                    <select
                      value={newProject.agent_id || ''}
                      onChange={(e) => setNewProject({ ...newProject, agent_id: e.target.value ? Number(e.target.value) : undefined })}
                      className="input w-full"
                    >
                      <option value="">Use system default</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>{agent.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Knowledge Base Section */}
              <div>
                <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                  <span className="w-6 h-6 rounded bg-purple-500/20 flex items-center justify-center text-xs">2</span>
                  Knowledge Base Configuration
                </h3>
                <div className="space-y-4 p-4 bg-white/5 rounded-xl">
                  <div>
                    <label className="block text-sm text-white/70 mb-1.5">Embedding Model</label>
                    <select
                      value={newProject.kb_embedding_model}
                      onChange={(e) => setNewProject({ ...newProject, kb_embedding_model: e.target.value })}
                      className="input w-full"
                    >
                      {EMBEDDING_MODELS.map((model) => (
                        <option key={model.value} value={model.value}>{model.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm text-white/70 mb-1.5">Chunk Size (chars)</label>
                      <input
                        type="number"
                        value={newProject.kb_chunk_size}
                        onChange={(e) => setNewProject({ ...newProject, kb_chunk_size: Number(e.target.value) })}
                        className="input w-full"
                        min={100}
                        max={2000}
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-white/70 mb-1.5">Chunk Overlap</label>
                      <input
                        type="number"
                        value={newProject.kb_chunk_overlap}
                        onChange={(e) => setNewProject({ ...newProject, kb_chunk_overlap: Number(e.target.value) })}
                        className="input w-full"
                        min={0}
                        max={500}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Memory Configuration Section */}
              <div>
                <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                  <span className="w-6 h-6 rounded bg-orange-500/20 flex items-center justify-center text-xs">3</span>
                  Memory Configuration
                </h3>
                <div className="space-y-4 p-4 bg-white/5 rounded-xl">
                  {/* Semantic Memory */}
                  <div className="flex items-start justify-between">
                    <div>
                      <label className="text-sm text-white font-medium">Semantic Memory</label>
                      <p className="text-xs text-white/50">Store conversation history with semantic search</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setNewProject({ ...newProject, enable_semantic_memory: !newProject.enable_semantic_memory })}
                      className={`w-12 h-6 rounded-full transition-colors ${newProject.enable_semantic_memory ? 'bg-teal-500' : 'bg-white/20'}`}
                    >
                      <div className={`w-5 h-5 rounded-full bg-white transition-transform ${newProject.enable_semantic_memory ? 'translate-x-6' : 'translate-x-0.5'}`} />
                    </button>
                  </div>

                  {newProject.enable_semantic_memory && (
                    <div className="grid grid-cols-2 gap-4 pl-4 border-l-2 border-teal-500/30">
                      <div>
                        <label className="block text-xs text-white/50 mb-1">Max Results</label>
                        <input
                          type="number"
                          value={newProject.semantic_memory_results}
                          onChange={(e) => setNewProject({ ...newProject, semantic_memory_results: Number(e.target.value) })}
                          className="input w-full text-sm"
                          min={1}
                          max={50}
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-white/50 mb-1">Similarity Threshold</label>
                        <input
                          type="number"
                          value={newProject.semantic_similarity_threshold}
                          onChange={(e) => setNewProject({ ...newProject, semantic_similarity_threshold: Number(e.target.value) })}
                          className="input w-full text-sm"
                          min={0}
                          max={1}
                          step={0.1}
                        />
                      </div>
                    </div>
                  )}

                  {/* Factual Memory */}
                  <div className="flex items-start justify-between">
                    <div>
                      <label className="text-sm text-white font-medium">Factual Memory</label>
                      <p className="text-xs text-white/50">Extract and store facts from conversations</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setNewProject({ ...newProject, enable_factual_memory: !newProject.enable_factual_memory })}
                      className={`w-12 h-6 rounded-full transition-colors ${newProject.enable_factual_memory ? 'bg-purple-500' : 'bg-white/20'}`}
                    >
                      <div className={`w-5 h-5 rounded-full bg-white transition-transform ${newProject.enable_factual_memory ? 'translate-x-6' : 'translate-x-0.5'}`} />
                    </button>
                  </div>

                  {newProject.enable_factual_memory && (
                    <div className="pl-4 border-l-2 border-purple-500/30">
                      <label className="block text-xs text-white/50 mb-1">Extraction Threshold (messages)</label>
                      <input
                        type="number"
                        value={newProject.factual_extraction_threshold}
                        onChange={(e) => setNewProject({ ...newProject, factual_extraction_threshold: Number(e.target.value) })}
                        className="input w-full text-sm"
                        min={1}
                        max={50}
                      />
                      <p className="text-xs text-white/40 mt-1">Extract facts after this many messages</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="p-4 border-t border-white/10 flex justify-end gap-3">
              <button
                onClick={() => { setShowCreateModal(false); resetForm() }}
                className="px-4 py-2 text-sm text-white/70 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateProject}
                disabled={isCreating || !newProject.name.trim()}
                className="px-4 py-2 text-sm btn-primary rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isCreating ? 'Creating...' : 'Create Project'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
