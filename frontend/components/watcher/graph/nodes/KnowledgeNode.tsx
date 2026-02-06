'use client'

/**
 * KnowledgeNode - Compact child node for displaying knowledge base documents in the graph
 * Phase 5: Expandable Agent Features
 */

import { memo, useState } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { KnowledgeNodeData, KnowledgeStatus } from '../types'

// Document type icon mapping
const docTypeIcons: Record<string, JSX.Element> = {
  pdf: (
    <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
  txt: (
    <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
  docx: (
    <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
  csv: (
    <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0112 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M13.125 12h7.5c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 14.625v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 14.625c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m0 1.5v-1.5m0 0c0-.621.504-1.125 1.125-1.125m-1.125 1.125c0 .621.504 1.125 1.125 1.125m0 0h7.5" />
    </svg>
  ),
  json: (
    <svg className="w-4 h-4 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
    </svg>
  ),
  default: (
    <svg className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  ),
}

// Status configuration
const statusConfig: Record<KnowledgeStatus, { color: string; bgColor: string; label: string }> = {
  completed: { color: 'text-green-400', bgColor: 'bg-green-500', label: 'Ready' },
  processing: { color: 'text-yellow-400', bgColor: 'bg-yellow-500', label: 'Processing' },
  pending: { color: 'text-blue-400', bgColor: 'bg-blue-500', label: 'Pending' },
  failed: { color: 'text-red-400', bgColor: 'bg-red-500', label: 'Failed' },
}

// Format file size
function formatFileSize(bytes?: number): string {
  if (!bytes) return 'Unknown'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Format date
function formatDate(dateStr?: string): string {
  if (!dateStr) return 'Unknown'
  return new Date(dateStr).toLocaleDateString()
}

function KnowledgeNode(props: NodeProps<KnowledgeNodeData>) {
  const { data, selected } = props
  const [showDetail, setShowDetail] = useState(false)

  const docIcon = docTypeIcons[data.documentType.toLowerCase()] || docTypeIcons.default
  const status = statusConfig[data.status] || statusConfig.pending

  return (
    <>
      <div
        className={`
          relative px-3 py-2 rounded-lg border min-w-[140px]
          transition-all duration-200 cursor-pointer
          ${selected
            ? 'border-purple-500 bg-purple-500/10 shadow-lg shadow-purple-500/20'
            : 'border-tsushin-border bg-tsushin-surface hover:border-purple-500/50'
          }
        `}
        onClick={() => setShowDetail(true)}
      >
        {/* Connection handle - target only (connects from agent) */}
        <Handle
          type="target"
          position={Position.Top}
          className="!bg-purple-500 !w-2 !h-2 !border-2 !border-tsushin-deep"
        />

        <div className="flex items-center gap-2">
          {/* Document Icon */}
          <div className="flex-shrink-0 relative">
            {docIcon}
            {/* Status indicator */}
            <span
              className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ${status.bgColor}`}
              title={status.label}
            />
          </div>

          {/* Document Info */}
          <div className="flex flex-col min-w-0">
            <div className="text-xs font-medium text-white truncate max-w-[100px]">
              {data.documentName}
            </div>
            <div className="flex items-center gap-1 text-[10px] text-tsushin-slate">
              <span>{data.chunkCount} chunks</span>
            </div>
          </div>
        </div>
      </div>

      {/* Detail Popup */}
      {showDetail && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50"
          onClick={() => setShowDetail(false)}
        >
          <div
            className="bg-tsushin-deep border border-tsushin-border rounded-xl p-4 shadow-2xl min-w-[300px] max-w-[400px] animate-fade-in"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                {docIcon}
                <h3 className="text-lg font-medium text-white truncate max-w-[280px]">{data.documentName}</h3>
              </div>
              <button
                onClick={() => setShowDetail(false)}
                className="p-1 hover:bg-tsushin-surface rounded transition-colors flex-shrink-0"
              >
                <svg className="w-5 h-5 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Content */}
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Type:</span>
                <span className="text-white uppercase">{data.documentType}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Status:</span>
                <span className={`font-medium ${status.color}`}>{status.label}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Chunks:</span>
                <span className="text-white">{data.chunkCount}</span>
              </div>
              {data.fileSizeBytes && (
                <div className="flex justify-between text-sm">
                  <span className="text-tsushin-slate">Size:</span>
                  <span className="text-white">{formatFileSize(data.fileSizeBytes)}</span>
                </div>
              )}
              {data.uploadDate && (
                <div className="flex justify-between text-sm">
                  <span className="text-tsushin-slate">Uploaded:</span>
                  <span className="text-white">{formatDate(data.uploadDate)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default memo(KnowledgeNode)
