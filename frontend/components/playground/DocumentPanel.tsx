'use client'

import React, { useState, useCallback, useRef } from 'react'
import { api, PlaygroundDocument } from '@/lib/client'
import {
  FileIcon,
  DocumentIcon,
  ChartBarIcon,
  TrendingUpIcon,
  FileTextIcon,
  FolderIcon,
  IconProps
} from '@/components/ui/icons'

interface DocumentPanelProps {
  agentId: number
  documents: PlaygroundDocument[]
  onDocumentsChange: () => void
  isOpen: boolean
  onClose: () => void
}

export default function DocumentPanel({
  agentId,
  documents,
  onDocumentsChange,
  isOpen,
  onClose
}: DocumentPanelProps) {
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const SUPPORTED_TYPES = [
    '.pdf', '.txt', '.csv', '.json', '.xlsx', '.xls',
    '.docx', '.doc', '.md', '.markdown', '.rtf'
  ]

  const handleFileUpload = useCallback(async (files: FileList | File[]) => {
    setError(null)
    setIsUploading(true)

    const fileArray = Array.from(files)

    for (const file of fileArray) {
      try {
        setUploadProgress(`Uploading ${file.name}...`)
        const result = await api.uploadPlaygroundDocument(agentId, file)

        if (result.status === 'error') {
          setError(result.error || 'Upload failed')
        }
      } catch (err: any) {
        setError(err.message || 'Upload failed')
      }
    }

    setIsUploading(false)
    setUploadProgress(null)
    onDocumentsChange()
  }, [agentId, onDocumentsChange])

  const handleDelete = useCallback(async (docId: number) => {
    try {
      await api.deletePlaygroundDocument(docId)
      onDocumentsChange()
    } catch (err: any) {
      setError(err.message || 'Failed to delete document')
    }
  }, [onDocumentsChange])

  const handleClearAll = useCallback(async () => {
    if (!confirm('Are you sure you want to delete all documents?')) return

    try {
      await api.clearPlaygroundDocuments(agentId)
      onDocumentsChange()
    } catch (err: any) {
      setError(err.message || 'Failed to clear documents')
    }
  }, [agentId, onDocumentsChange])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFileUpload(files)
    }
  }, [handleFileUpload])

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const DOC_TYPE_ICON_COMPONENTS: Record<string, React.FC<IconProps>> = {
    pdf: FileIcon,
    txt: DocumentIcon,
    csv: ChartBarIcon,
    json: DocumentIcon,
    xlsx: TrendingUpIcon,
    docx: DocumentIcon,
    md: DocumentIcon,
    rtf: FileTextIcon,
    default: FolderIcon,
  }

  const getDocTypeIcon = (type: string) => {
    const IconComponent = DOC_TYPE_ICON_COMPONENTS[type] || DOC_TYPE_ICON_COMPONENTS.default
    return <IconComponent size={18} className="text-[var(--pg-text-secondary)]" />
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-400'
      case 'processing': return 'text-yellow-400'
      case 'failed': return 'text-red-400'
      default: return 'text-gray-400'
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="glass-card w-full max-w-lg max-h-[80vh] overflow-hidden rounded-2xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-tsushin-border">
          <h2 className="text-lg font-semibold text-tsushin-pearl flex items-center gap-2">
            <svg className="w-5 h-5 text-tsushin-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Knowledge Base
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-tsushin-slate hover:text-tsushin-pearl hover:bg-tsushin-surface rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Upload Area */}
        <div
          className={`p-4 border-b border-tsushin-border ${isDragging ? 'bg-tsushin-teal/10' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className={`
            border-2 border-dashed rounded-xl p-6 text-center transition-colors
            ${isDragging
              ? 'border-tsushin-teal bg-tsushin-teal/5'
              : 'border-tsushin-border hover:border-tsushin-slate'
            }
          `}>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={SUPPORTED_TYPES.join(',')}
              onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
              className="hidden"
            />

            {isUploading ? (
              <div className="flex flex-col items-center gap-2">
                <div className="w-8 h-8 border-2 border-tsushin-teal/30 border-t-tsushin-teal rounded-full animate-spin"></div>
                <p className="text-sm text-tsushin-slate">{uploadProgress}</p>
              </div>
            ) : (
              <>
                <svg className="w-10 h-10 mx-auto text-tsushin-slate mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-sm text-tsushin-slate mb-2">
                  Drag & drop files here, or{' '}
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="text-tsushin-teal hover:underline"
                  >
                    browse
                  </button>
                </p>
                <p className="text-xs text-tsushin-muted">
                  PDF, TXT, CSV, JSON, XLSX, DOCX, MD, RTF (max 10MB)
                </p>
              </>
            )}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="px-4 py-2 bg-tsushin-vermilion/10 border-b border-tsushin-vermilion/20">
            <p className="text-sm text-tsushin-vermilion">{error}</p>
          </div>
        )}

        {/* Documents List */}
        <div className="flex-1 overflow-y-auto max-h-[300px] p-4">
          {documents.length === 0 ? (
            <p className="text-center text-tsushin-muted py-8">
              No documents uploaded yet.
              <br />
              <span className="text-xs">
                Upload documents to chat with your agent about them.
              </span>
            </p>
          ) : (
            <div className="space-y-2">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center gap-3 p-3 bg-tsushin-surface/50 rounded-lg hover:bg-tsushin-surface transition-colors"
                >
                  <span className="flex items-center justify-center w-5 h-5">{getDocTypeIcon(doc.type)}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-tsushin-pearl truncate">
                      {doc.name}
                    </p>
                    <p className="text-xs text-tsushin-muted flex items-center gap-2">
                      <span>{formatFileSize(doc.size_bytes)}</span>
                      <span>•</span>
                      <span>{doc.num_chunks} chunks</span>
                      <span>•</span>
                      <span className={getStatusColor(doc.status)}>{doc.status}</span>
                    </p>
                    {doc.error && (
                      <p className="text-xs text-tsushin-vermilion mt-1">{doc.error}</p>
                    )}
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="p-1.5 text-tsushin-slate hover:text-tsushin-vermilion hover:bg-tsushin-vermilion/10 rounded transition-colors"
                    title="Delete document"
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

        {/* Footer */}
        {documents.length > 0 && (
          <div className="p-4 border-t border-tsushin-border flex justify-between items-center">
            <p className="text-xs text-tsushin-muted">
              {documents.length} document{documents.length !== 1 ? 's' : ''}
            </p>
            <button
              onClick={handleClearAll}
              className="text-xs text-tsushin-vermilion hover:text-tsushin-vermilion/80 transition-colors"
            >
              Clear all
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
