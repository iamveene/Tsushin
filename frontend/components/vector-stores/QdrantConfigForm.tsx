'use client'

import { useState } from 'react'

interface QdrantConfigFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
  isEditing: boolean
}

export default function QdrantConfigForm({ config, onChange, isEditing }: QdrantConfigFormProps) {
  const [showKey, setShowKey] = useState(false)

  const update = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm text-gray-300 mb-1">Base URL <span className="text-red-400">*</span></label>
        <input
          type="text"
          value={config.base_url || ''}
          onChange={(e) => update('base_url', e.target.value)}
          placeholder="http://localhost:6333 or https://xxx.cloud.qdrant.io"
          className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm text-gray-300 mb-1">API Key</label>
        <div className="relative">
          <input
            type={showKey ? 'text' : 'password'}
            value={config.api_key || ''}
            onChange={(e) => update('api_key', e.target.value)}
            placeholder={isEditing ? '(unchanged)' : 'Optional for self-hosted instances'}
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
        <p className="text-xs text-gray-500 mt-1">Optional for self-hosted Qdrant, required for Qdrant Cloud</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Collection Name <span className="text-red-400">*</span></label>
          <input
            type="text"
            value={config.collection_name || ''}
            onChange={(e) => update('collection_name', e.target.value)}
            placeholder="tsushin"
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Embedding Dimensions</label>
          <input
            type="number"
            value={config.embedding_dims || 384}
            onChange={(e) => update('embedding_dims', parseInt(e.target.value) || 384)}
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm"
          />
        </div>
      </div>
    </div>
  )
}
