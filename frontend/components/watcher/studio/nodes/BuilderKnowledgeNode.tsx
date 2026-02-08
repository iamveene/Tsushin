'use client'
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderKnowledgeData } from '../types'

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function BuilderKnowledgeNode({ data, selected }: NodeProps) {
  const d = data as BuilderKnowledgeData
  return (
    <div role="group" aria-label={`Knowledge: ${d.filename}`}
      className={`builder-node builder-node-knowledge px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-violet-400 shadow-glow-sm' : 'border-tsushin-border hover:border-violet-400/50'} bg-tsushin-surface`}>
      <Handle type="target" position={Position.Top} className="!bg-violet-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-violet-500/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium truncate max-w-[140px]">{d.filename}</p>
          <div className="flex items-center gap-2 text-2xs text-tsushin-muted">
            <span>{formatFileSize(d.fileSize)}</span>
            {d.chunkCount !== undefined && <span>{d.chunkCount} chunks</span>}
          </div>
          <span className={`text-2xs ${d.status === 'completed' ? 'text-green-400' : d.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}`}>{d.status}</span>
        </div>
      </div>
    </div>
  )
}
export default memo(BuilderKnowledgeNode)
