'use client'

/**
 * Knowledge Tab - Shows KB documents for the selected agent and project
 * Part of the playground inspector panel
 * Now supports both Agent KB and Project KB with separate sections
 */

import React, { useState, useEffect } from 'react'
import { api, AgentKnowledge, ProjectDocument, ProjectSession } from '@/lib/client'
import { parseUTCTimestamp } from '@/lib/dateUtils'
import {
  FileIcon,
  DocumentIcon,
  ChartBarIcon,
  TrendingUpIcon,
  FileTextIcon,
  FolderIcon,
  BookIcon,
  IconProps
} from '@/components/ui/icons'

interface KnowledgeTabProps {
  agentId: number | null
  projectSession?: ProjectSession | null
}

const DOC_TYPE_ICON_COMPONENTS: Record<string, React.FC<IconProps>> = {
  pdf: FileIcon,
  txt: DocumentIcon,
  csv: ChartBarIcon,
  json: FileTextIcon,
  xlsx: TrendingUpIcon,
  xls: TrendingUpIcon,
  docx: DocumentIcon,
  doc: DocumentIcon,
  md: DocumentIcon,
  markdown: DocumentIcon,
  rtf: FileTextIcon,
  default: FolderIcon
}

const DOC_TYPE_COLORS: Record<string, string> = {
  pdf: 'text-red-400',
  txt: 'text-blue-400',
  csv: 'text-green-400',
  json: 'text-purple-400',
  xlsx: 'text-emerald-400',
  xls: 'text-emerald-400',
  docx: 'text-cyan-400',
  doc: 'text-cyan-400',
  md: 'text-yellow-400',
  markdown: 'text-yellow-400',
  rtf: 'text-orange-400',
  default: 'text-white/60'
}

export default function KnowledgeTab({ agentId, projectSession }: KnowledgeTabProps) {
  // Agent KB state
  const [documents, setDocuments] = useState<AgentKnowledge[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<AgentKnowledge | null>(null)
  const [chunks, setChunks] = useState<any[]>([])
  const [loadingChunks, setLoadingChunks] = useState(false)
  const [uploading, setUploading] = useState(false)

  // Project KB state
  const [projectDocuments, setProjectDocuments] = useState<ProjectDocument[]>([])
  const [projectLoading, setProjectLoading] = useState(false)
  const [projectUploading, setProjectUploading] = useState(false)
  const [selectedProjectDoc, setSelectedProjectDoc] = useState<ProjectDocument | null>(null)

  // UI state
  const [agentSectionCollapsed, setAgentSectionCollapsed] = useState(false)
  const [projectSectionCollapsed, setProjectSectionCollapsed] = useState(false)

  useEffect(() => {
    if (agentId) {
      loadDocuments()
    } else {
      setDocuments([])
    }
  }, [agentId])

  // Auto-reload project documents when project session changes
  useEffect(() => {
    if (projectSession?.is_in_project && projectSession?.project_id) {
      loadProjectDocuments()
    } else {
      // Clear project documents when exiting project
      setProjectDocuments([])
    }
  }, [projectSession?.project_id, projectSession?.is_in_project])

  const loadDocuments = async () => {
    if (!agentId) return
    setLoading(true)
    setError(null)

    try {
      const result = await api.getAgentKnowledge(agentId)
      setDocuments(result || [])
    } catch (err: any) {
      console.error('Failed to load KB documents:', err)
      setError(err.message || 'Failed to load documents')
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    const file = files[0]

    // Validate file type
    const validTypes = [
      'text/plain',
      'text/csv',
      'application/json',
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]

    const fileName = file.name.toLowerCase()
    const validExtensions = ['.txt', '.csv', '.json', '.pdf', '.docx']
    const hasValidExtension = validExtensions.some(ext => fileName.endsWith(ext))

    if (!validTypes.includes(file.type) && !hasValidExtension) {
      alert('Invalid file type. Please upload TXT, CSV, JSON, PDF, or DOCX files.')
      return
    }

    // Validate file size (10 MB max)
    if (file.size > 10 * 1024 * 1024) {
      alert('File too large. Maximum size is 10 MB.')
      return
    }

    setUploading(true)
    try {
      if (!agentId) return
      await api.uploadKnowledgeDocument(agentId, file)
      alert('Document uploaded successfully! Processing will begin shortly.')
      loadDocuments()
    } catch (err: any) {
      console.error('Failed to upload document:', err)
      alert('Failed to upload document: ' + (err.message || 'Unknown error'))
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (docId: number) => {
    if (!confirm('Delete this document?')) return

    try {
      if (!agentId) return
      await api.deleteKnowledgeDocument(agentId, docId)
      loadDocuments()
    } catch (err: any) {
      console.error('Failed to delete document:', err)
      setError(err.message || 'Failed to delete document')
    }
  }

  // Project KB Functions
  const loadProjectDocuments = async () => {
    if (!projectSession?.project_id) return
    setProjectLoading(true)

    try {
      const result = await api.getProjectDocuments(projectSession.project_id)
      setProjectDocuments(result || [])
    } catch (err: any) {
      console.error('Failed to load project KB documents:', err)
      setError(err.message || 'Failed to load project documents')
    } finally {
      setProjectLoading(false)
    }
  }

  const handleProjectUpload = async (files: FileList | null) => {
    if (!files || files.length === 0 || !projectSession?.project_id) return

    const file = files[0]

    // Validate file type
    const validTypes = [
      'text/plain',
      'text/csv',
      'application/json',
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ]

    const fileName = file.name.toLowerCase()
    const validExtensions = ['.txt', '.csv', '.json', '.pdf', '.docx']
    const hasValidExtension = validExtensions.some(ext => fileName.endsWith(ext))

    if (!validTypes.includes(file.type) && !hasValidExtension) {
      alert('Invalid file type. Please upload TXT, CSV, JSON, PDF, or DOCX files.')
      return
    }

    // Validate file size (10 MB max)
    if (file.size > 10 * 1024 * 1024) {
      alert('File too large. Maximum size is 10 MB.')
      return
    }

    setProjectUploading(true)
    try {
      await api.uploadProjectDocument(projectSession.project_id, file)
      alert('Document uploaded successfully to project KB!')
      loadProjectDocuments()
    } catch (err: any) {
      console.error('Failed to upload project document:', err)
      alert('Failed to upload document: ' + (err.message || 'Unknown error'))
    } finally {
      setProjectUploading(false)
    }
  }

  const handleProjectDelete = async (docId: number) => {
    if (!confirm('Delete this project document?')) return

    try {
      if (!projectSession?.project_id) return
      await api.deleteProjectDocument(projectSession.project_id, docId)
      loadProjectDocuments()
    } catch (err: any) {
      console.error('Failed to delete project document:', err)
      setError(err.message || 'Failed to delete project document')
    }
  }

  const getDocIcon = (type: string) => {
    const cleanType = type.toLowerCase().replace('.', '')
    const IconComponent = DOC_TYPE_ICON_COMPONENTS[cleanType] || DOC_TYPE_ICON_COMPONENTS.default
    return <IconComponent size={16} />
  }

  const getDocColor = (type: string) => {
    const cleanType = type.toLowerCase().replace('.', '')
    return DOC_TYPE_COLORS[cleanType] || DOC_TYPE_COLORS.default
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-400'
      case 'processing': return 'text-yellow-400'
      case 'failed': return 'text-red-400'
      default: return 'text-white/40'
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A'
    return parseUTCTimestamp(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  if (!agentId) {
    return (
      <div className="h-full flex items-center justify-center text-white/40 text-xs">
        Select an agent to view KB
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-3 text-xs text-red-400">
        {error}
      </div>
    )
  }

  // Calculate stats
  const agentTotalSize = documents.reduce((sum, doc) => sum + doc.file_size_bytes, 0)
  const agentTotalChunks = documents.reduce((sum, doc) => sum + doc.num_chunks, 0)
  const agentCompletedDocs = documents.filter(d => d.status === 'completed').length

  const projectTotalSize = projectDocuments.reduce((sum, doc) => sum + doc.size_bytes, 0)
  const projectTotalChunks = projectDocuments.reduce((sum, doc) => sum + doc.num_chunks, 0)
  const projectCompletedDocs = projectDocuments.filter(d => d.status === 'completed').length

  const handleView = async (doc: AgentKnowledge) => {
    setSelectedDoc(doc)
    setLoadingChunks(true)
    try {
      if (!agentId) return
      const docChunks = await api.getKnowledgeChunks(agentId, doc.id)
      setChunks(docChunks || [])
    } catch (err: any) {
      console.error('Failed to load chunks:', err)
      setError(err.message || 'Failed to load document chunks')
      setChunks([])
    } finally {
      setLoadingChunks(false)
    }
  }

  const handleProjectView = async (doc: ProjectDocument) => {
    setSelectedDoc(doc)
    setLoadingChunks(true)
    try {
      if (!projectSession?.project_id) return
      const docChunks = await api.getProjectKnowledgeChunks(projectSession.project_id, doc.id)
      setChunks(docChunks || [])
    } catch (err: any) {
      console.error('Failed to load project chunks:', err)
      setError(err.message || 'Failed to load document chunks')
      setChunks([])
    } finally {
      setLoadingChunks(false)
    }
  }

  // Render a document list item (reusable for both agent and project docs)
  const renderDocumentItem = (doc: AgentKnowledge | ProjectDocument, isProject: boolean) => {
    const docName = 'document_name' in doc ? doc.document_name : doc.name
    const docType = 'document_type' in doc ? doc.document_type : doc.type
    const fileSize = 'file_size_bytes' in doc ? doc.file_size_bytes : doc.size_bytes
    const uploadDate = 'upload_date' in doc ? doc.upload_date : doc.upload_date
    const errorMessage = 'error_message' in doc ? doc.error_message : doc.error

    return (
      <div
        key={doc.id}
        className="group p-2 rounded bg-white/[0.02] hover:bg-white/[0.04] border border-white/[0.06] hover:border-white/[0.1] transition-all"
      >
        <div className="flex items-start gap-2">
          <div className={`text-base ${getDocColor(docType)}`}>
            {getDocIcon(docType)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-white/90 truncate mb-1">
              {docName}
            </div>
            <div className="flex items-center gap-2 text-[10px] text-white/40">
              <span>{formatFileSize(fileSize)}</span>
              <span>•</span>
              <span>{doc.num_chunks} chunks</span>
              <span>•</span>
              <span className={getStatusColor(doc.status)}>{doc.status}</span>
            </div>
            {uploadDate && (
              <div className="text-[9px] text-white/30 mt-1">
                {formatDate(uploadDate)}
              </div>
            )}
            {errorMessage && (
              <div className="text-[10px] text-red-400 mt-1">
                {errorMessage}
              </div>
            )}
          </div>
          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {doc.status === 'completed' && (
              <button
                onClick={() => isProject ? handleProjectView(doc as ProjectDocument) : handleView(doc as AgentKnowledge)}
                className="p-1 hover:bg-blue-500/10 rounded text-white/40 hover:text-blue-400"
                title="View document"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </button>
            )}
            <button
              onClick={() => isProject ? handleProjectDelete(doc.id) : handleDelete(doc.id)}
              className="p-1 hover:bg-red-500/10 rounded text-white/40 hover:text-red-400"
              title="Delete document"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Agent KB Section */}
      <div className="border-b border-white/[0.06]">
        {/* Agent KB Header */}
        <button
          onClick={() => setAgentSectionCollapsed(!agentSectionCollapsed)}
          className="w-full px-3 py-2 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-2">
            <svg
              className={`w-3 h-3 text-white/40 transition-transform ${agentSectionCollapsed ? '' : 'rotate-90'}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="text-xs font-semibold text-white/80">Agent Knowledge Base</span>
          </div>
          <span className="text-[10px] text-white/40">{agentCompletedDocs} docs</span>
        </button>

        {!agentSectionCollapsed && (
          <>
            {/* Agent Stats */}
            {documents.length > 0 && (
              <div className="px-3 py-2 border-t border-white/[0.06]">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-xs font-semibold text-[var(--pg-accent)]">{agentCompletedDocs}</div>
                    <div className="text-[9px] text-white/40 uppercase tracking-wider">Docs</div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[var(--pg-accent)]">{agentTotalChunks}</div>
                    <div className="text-[9px] text-white/40 uppercase tracking-wider">Chunks</div>
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-[var(--pg-accent)]">{formatFileSize(agentTotalSize)}</div>
                    <div className="text-[9px] text-white/40 uppercase tracking-wider">Size</div>
                  </div>
                </div>
              </div>
            )}

            {/* Agent Upload Section */}
            <div className="px-3 py-2 border-t border-white/[0.06]">
              <input
                type="file"
                id="agent-kb-file-upload"
                className="hidden"
                accept=".pdf,.txt,.csv,.json,.docx"
                onChange={(e) => handleUpload(e.target.files)}
                disabled={uploading}
              />
              <label
                htmlFor="agent-kb-file-upload"
                className={`flex items-center justify-center gap-2 px-3 py-2 rounded text-xs font-medium transition-all cursor-pointer ${
                  uploading
                    ? 'bg-white/5 text-white/40 cursor-not-allowed'
                    : 'bg-[var(--pg-accent)]/20 text-[var(--pg-accent)] hover:bg-[var(--pg-accent)]/30'
                }`}
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                {uploading ? 'Uploading...' : 'Upload to Agent'}
              </label>
              <div className="text-[9px] text-white/30 mt-1 text-center">
                TXT, CSV, JSON, PDF, DOCX • Max 10 MB
              </div>
            </div>

            {/* Agent Documents List */}
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <div className="w-5 h-5 border-2 border-white/20 border-t-[var(--pg-accent)] rounded-full animate-spin"></div>
              </div>
            ) : documents.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center p-4">
                <div className="text-white/30 mb-2"><BookIcon size={32} /></div>
                <div className="text-xs text-white/40 mb-1">No agent KB documents</div>
                <div className="text-[10px] text-white/30">Upload documents to chat with them</div>
              </div>
            ) : (
              <div className="p-2 space-y-1 max-h-[300px] overflow-y-auto">
                {documents.map((doc) => renderDocumentItem(doc, false))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Project KB Section - Only visible when in project */}
      {projectSession?.is_in_project && (
        <div className="border-b border-white/[0.06]">
          {/* Project KB Header */}
          <button
            onClick={() => setProjectSectionCollapsed(!projectSectionCollapsed)}
            className="w-full px-3 py-2 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
          >
            <div className="flex items-center gap-2">
              <svg
                className={`w-3 h-3 text-white/40 transition-transform ${projectSectionCollapsed ? '' : 'rotate-90'}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className="text-xs font-semibold text-white/80">Project Knowledge Base</span>
              <span className="text-[10px] text-blue-400">({projectSession.project_name})</span>
            </div>
            <span className="text-[10px] text-white/40">{projectCompletedDocs} docs</span>
          </button>

          {!projectSectionCollapsed && (
            <>
              {/* Project Stats */}
              {projectDocuments.length > 0 && (
                <div className="px-3 py-2 border-t border-white/[0.06]">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div>
                      <div className="text-xs font-semibold text-blue-400">{projectCompletedDocs}</div>
                      <div className="text-[9px] text-white/40 uppercase tracking-wider">Docs</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-blue-400">{projectTotalChunks}</div>
                      <div className="text-[9px] text-white/40 uppercase tracking-wider">Chunks</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-blue-400">{formatFileSize(projectTotalSize)}</div>
                      <div className="text-[9px] text-white/40 uppercase tracking-wider">Size</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Project Upload Section */}
              <div className="px-3 py-2 border-t border-white/[0.06]">
                <input
                  type="file"
                  id="project-kb-file-upload"
                  className="hidden"
                  accept=".pdf,.txt,.csv,.json,.docx"
                  onChange={(e) => handleProjectUpload(e.target.files)}
                  disabled={projectUploading}
                />
                <label
                  htmlFor="project-kb-file-upload"
                  className={`flex items-center justify-center gap-2 px-3 py-2 rounded text-xs font-medium transition-all cursor-pointer ${
                    projectUploading
                      ? 'bg-white/5 text-white/40 cursor-not-allowed'
                      : 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30'
                  }`}
                >
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  {projectUploading ? 'Uploading...' : 'Upload to Project'}
                </label>
                <div className="text-[9px] text-white/30 mt-1 text-center">
                  TXT, CSV, JSON, PDF, DOCX • Max 10 MB
                </div>
              </div>

              {/* Project Documents List */}
              {projectLoading ? (
                <div className="flex items-center justify-center py-4">
                  <div className="w-5 h-5 border-2 border-white/20 border-t-blue-400 rounded-full animate-spin"></div>
                </div>
              ) : projectDocuments.length === 0 ? (
                <div className="flex flex-col items-center justify-center text-center p-4">
                  <div className="text-white/30 mb-2"><FolderIcon size={32} /></div>
                  <div className="text-xs text-white/40 mb-1">No project KB documents</div>
                  <div className="text-[10px] text-white/30">Upload documents for this project</div>
                </div>
              ) : (
                <div className="p-2 space-y-1 max-h-[300px] overflow-y-auto">
                  {projectDocuments.map((doc) => renderDocumentItem(doc, true))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Document View Modal */}
      {selectedDoc && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-white/10 shadow-2xl">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-white/10 flex justify-between items-start">
              <div>
                <h3 className="text-lg font-semibold text-white">{selectedDoc.document_name}</h3>
                <p className="text-sm text-white/50 mt-1">
                  {formatFileSize(selectedDoc.file_size_bytes)} • {selectedDoc.num_chunks} chunks
                </p>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="text-white/40 hover:text-white transition-colors p-2 hover:bg-white/5 rounded"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Content */}
            <div className="overflow-y-auto p-6 space-y-4 flex-1">
              {loadingChunks ? (
                <div className="flex items-center justify-center py-12">
                  <div className="w-6 h-6 border-2 border-white/20 border-t-[var(--pg-accent)] rounded-full animate-spin"></div>
                </div>
              ) : chunks.length === 0 ? (
                <p className="text-center text-white/40 py-12">No chunks found</p>
              ) : (
                chunks.map((chunk, i) => (
                  <div key={i} className="border border-white/10 rounded-lg p-4 bg-white/[0.02]">
                    <div className="text-xs text-white/40 mb-2 flex items-center gap-2">
                      <span className="font-medium">Chunk {chunk.chunk_index + 1}</span>
                      <span>•</span>
                      <span>{chunk.char_count} chars</span>
                      {chunk.metadata_json?.page && (
                        <>
                          <span>•</span>
                          <span>Page {chunk.metadata_json.page}</span>
                        </>
                      )}
                    </div>
                    <p className="text-sm text-white/80 whitespace-pre-wrap leading-relaxed">{chunk.content}</p>
                  </div>
                ))
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-white/10">
              <button
                onClick={() => setSelectedDoc(null)}
                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
