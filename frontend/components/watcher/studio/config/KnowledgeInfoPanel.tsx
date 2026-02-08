'use client'

import type { BuilderKnowledgeData } from '../types'

interface KnowledgeInfoPanelProps {
  data: BuilderKnowledgeData
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const statusStyles: Record<string, string> = {
  processed: 'bg-green-500/20 text-green-300',
  processing: 'bg-blue-500/20 text-blue-300',
  error: 'bg-red-500/20 text-red-300',
  pending: 'bg-yellow-500/20 text-yellow-300',
}

export default function KnowledgeInfoPanel({ data }: KnowledgeInfoPanelProps) {
  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Filename</label>
        <p className="text-sm text-white break-all">{data.filename}</p>
      </div>

      <div className="config-field">
        <label>Content Type</label>
        <p className="text-sm text-tsushin-slate">{data.contentType}</p>
      </div>

      <div className="config-field">
        <label>File Size</label>
        <p className="text-sm text-tsushin-slate">{formatFileSize(data.fileSize)}</p>
      </div>

      {data.chunkCount !== undefined && (
        <div className="config-field">
          <label>Chunks</label>
          <p className="text-sm text-tsushin-slate">{data.chunkCount} chunks</p>
        </div>
      )}

      <div className="config-field">
        <label>Status</label>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusStyles[data.status] || statusStyles.pending}`}>
          {data.status}
        </span>
      </div>
    </div>
  )
}
