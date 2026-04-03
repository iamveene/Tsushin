'use client'

import { useState } from 'react'

interface PineconeConfigFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
  isEditing: boolean
}

export default function PineconeConfigForm({ config, onChange, isEditing }: PineconeConfigFormProps) {
  const [showKey, setShowKey] = useState(false)

  const update = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm text-gray-300 mb-1">API Key <span className="text-red-400">*</span></label>
        <div className="relative">
          <input
            type={showKey ? 'text' : 'password'}
            value={config.api_key || ''}
            onChange={(e) => update('api_key', e.target.value)}
            placeholder={isEditing ? '(unchanged)' : 'pcsk_...'}
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm pr-16"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-300"
          >
            {showKey ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1">Environment / Host <span className="text-red-400">*</span></label>
        <input
          type="text"
          value={config.environment || ''}
          onChange={(e) => update('environment', e.target.value)}
          placeholder="us-east-1-aws or https://xxx.svc.pinecone.io"
          className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Index Name <span className="text-red-400">*</span></label>
          <input
            type="text"
            value={config.index_name || ''}
            onChange={(e) => update('index_name', e.target.value)}
            placeholder="tsushin"
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Namespace</label>
          <input
            type="text"
            value={config.namespace || ''}
            onChange={(e) => update('namespace', e.target.value)}
            placeholder="default (optional)"
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1">Embedding Dimensions</label>
        <input
          type="number"
          value={config.embedding_dims || 384}
          onChange={(e) => update('embedding_dims', parseInt(e.target.value) || 384)}
          className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm"
        />
        <p className="text-xs text-gray-500 mt-1">Must match your embedding model (384 for all-MiniLM-L6-v2)</p>
      </div>
    </div>
  )
}
