'use client'

import { memo, useCallback } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderKnowledgeData } from '../types'

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const typeIcons: Record<string, string> = {
  pdf: 'text-red-400',
  txt: 'text-gray-400',
  csv: 'text-green-400',
  json: 'text-yellow-400',
  md: 'text-blue-400',
}

function BuilderKnowledgeNode({ data, selected }: NodeProps) {
  const d = data as BuilderKnowledgeData

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    d.onToggleExpand?.(d.docId)
  }, [d.onToggleExpand, d.docId])

  const typeColor = typeIcons[d.contentType?.toLowerCase()] || 'text-violet-400'

  return (
    <div role="group" aria-label={`Knowledge: ${d.filename}`}
      className={`builder-node builder-node-knowledge px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-violet-400 shadow-glow-sm' : 'border-tsushin-border hover:border-violet-400/50'} bg-tsushin-surface`}>
      <Handle type="target" position={Position.Top} className="!bg-violet-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-violet-500/20 flex items-center justify-center flex-shrink-0">
          <svg className={`w-4 h-4 ${typeColor}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-white text-sm font-medium truncate max-w-[140px]">{d.filename}</p>
          <div className="flex items-center gap-2 text-2xs text-tsushin-muted">
            <span>{formatFileSize(d.fileSize)}</span>
            {d.chunkCount !== undefined && <span>{d.chunkCount} chunks</span>}
          </div>
          <span className={`text-2xs ${d.status === 'completed' ? 'text-green-400' : d.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}`}>{d.status}</span>
        </div>
        {d.onToggleExpand && (
          <button onClick={handleToggle} className="flex-shrink-0 p-1 rounded hover:bg-violet-500/20 transition-colors" title={d.isExpanded ? 'Collapse details' : 'Expand details'}>
            <svg className={`w-3.5 h-3.5 text-violet-400 transition-transform ${d.isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        )}
      </div>
      {d.isExpanded && (
        <div className="mt-2 pt-2 border-t border-tsushin-border/50 space-y-1.5 text-2xs">
          <div className="flex justify-between">
            <span className="text-tsushin-muted">Type</span>
            <span className="text-white font-medium uppercase">{d.contentType}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-tsushin-muted">Size</span>
            <span className="text-white">{formatFileSize(d.fileSize)}</span>
          </div>
          {d.chunkCount !== undefined && (
            <div className="flex justify-between">
              <span className="text-tsushin-muted">Chunks</span>
              <span className="text-white">{d.chunkCount}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-tsushin-muted">Status</span>
            <span className={`font-medium ${d.status === 'completed' ? 'text-green-400' : d.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}`}>
              {d.status === 'completed' ? 'Processed' : d.status === 'processing' ? 'Processing...' : d.status === 'failed' ? 'Failed' : 'Pending'}
            </span>
          </div>
          {d.uploadDate && (
            <div className="flex justify-between">
              <span className="text-tsushin-muted">Uploaded</span>
              <span className="text-white">{new Date(d.uploadDate).toLocaleDateString()}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
export default memo(BuilderKnowledgeNode)
