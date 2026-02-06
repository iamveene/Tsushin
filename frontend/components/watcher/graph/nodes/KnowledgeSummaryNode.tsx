'use client'

/**
 * KnowledgeSummaryNode - Summary node for agent knowledge base
 * Phase 6: Replaces individual KnowledgeNode with aggregated summary
 * Phase 8: Real-time activity glow
 */

import { memo, useState, useEffect, useRef } from 'react'
import { NodeProps, Handle, Position } from '@xyflow/react'
import { KnowledgeSummaryNodeData } from '../types'

// Format file size
function formatFileSize(bytes?: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function KnowledgeSummaryNode(props: NodeProps<KnowledgeSummaryNodeData>) {
  const { data, selected } = props
  const [showDetail, setShowDetail] = useState(false)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  // Phase 8: Real-time activity glow
  const isActive = data.isActive ?? false
  const isFading = data.isFading ?? false

  // Escape key to close modal
  useEffect(() => {
    if (!showDetail) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowDetail(false)
      }
    }

    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [showDetail])

  // Focus management - focus close button on open, restore focus on close
  useEffect(() => {
    if (showDetail) {
      previousFocusRef.current = document.activeElement as HTMLElement
      setTimeout(() => closeButtonRef.current?.focus(), 50)
    } else if (previousFocusRef.current) {
      previousFocusRef.current.focus()
      previousFocusRef.current = null
    }
  }, [showDetail])

  // Format document type breakdown
  const docTypeBreakdown = Object.entries(data.documentTypes)
    .map(([type, count]) => `${count} ${type.toUpperCase()}`)
    .join(', ')

  return (
    <>
      <div
        className={`
          relative px-3 py-2 rounded-lg border min-w-[160px]
          transition-all duration-200 cursor-pointer
          ${selected
            ? 'border-purple-500 bg-purple-500/10 shadow-lg shadow-purple-500/20'
            : 'border-tsushin-border bg-tsushin-surface hover:border-purple-500/50'
          }
          ${isActive && !isFading ? 'kb-node-active' : isFading ? 'kb-node-fading' : ''}
        `}
        onClick={() => setShowDetail(true)}
      >
        {/* Connection handle - target (connects from agent on the left in LR layout) */}
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-purple-500 !w-2 !h-2 !border-2 !border-tsushin-deep"
        />

        <div className="flex items-center gap-2">
          {/* Knowledge Base Icon */}
          <div className="flex-shrink-0 relative">
            <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
            </svg>
            {/* Status indicator */}
            <span
              className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ${
                data.allCompleted ? 'bg-green-500' : 'bg-yellow-500'
              }`}
              title={data.allCompleted ? 'All documents processed' : 'Processing...'}
            />
          </div>

          {/* KB Summary Info */}
          <div className="flex flex-col min-w-0">
            <div className="text-xs font-medium text-white">
              Knowledge Base
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-tsushin-slate">
              <span className="flex items-center gap-0.5">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                {data.totalDocuments}
              </span>
              <span className="text-tsushin-slate/50">•</span>
              <span>{data.totalChunks} chunks</span>
            </div>
          </div>
        </div>
      </div>

      {/* Detail Popup */}
      {showDetail && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50"
          onClick={() => setShowDetail(false)}
          role="presentation"
        >
          <div
            className="bg-tsushin-deep border border-tsushin-border rounded-xl p-4 shadow-2xl min-w-[320px] max-w-[400px] animate-fade-in"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="kb-modal-title"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                </svg>
                <h3 id="kb-modal-title" className="text-lg font-medium text-white">Knowledge Base</h3>
              </div>
              <button
                ref={closeButtonRef}
                onClick={() => setShowDetail(false)}
                className="p-1 hover:bg-tsushin-surface rounded transition-colors flex-shrink-0"
                aria-label="Close knowledge base details"
              >
                <svg className="w-5 h-5 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="bg-tsushin-surface rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-white">{data.totalDocuments}</div>
                <div className="text-xs text-tsushin-slate">Documents</div>
              </div>
              <div className="bg-tsushin-surface rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-white">{data.totalChunks}</div>
                <div className="text-xs text-tsushin-slate">Semantic Chunks</div>
              </div>
            </div>

            {/* Details */}
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Total Size:</span>
                <span className="text-white">{formatFileSize(data.totalSizeBytes)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-tsushin-slate">Status:</span>
                <span className={`font-medium ${data.allCompleted ? 'text-green-400' : 'text-yellow-400'}`}>
                  {data.allCompleted ? 'All Processed' : 'Processing...'}
                </span>
              </div>
              {docTypeBreakdown && (
                <div className="flex justify-between text-sm">
                  <span className="text-tsushin-slate">Types:</span>
                  <span className="text-white text-right">{docTypeBreakdown}</span>
                </div>
              )}
            </div>

            {/* Semantic Search Info */}
            <div className="mt-4 p-3 bg-purple-500/10 border border-purple-500/20 rounded-lg">
              <div className="flex items-center gap-2 text-purple-400 text-sm font-medium mb-1">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                </svg>
                Semantic Search Enabled
              </div>
              <p className="text-xs text-tsushin-slate">
                Documents are chunked and embedded for intelligent retrieval during conversations.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default memo(KnowledgeSummaryNode)
