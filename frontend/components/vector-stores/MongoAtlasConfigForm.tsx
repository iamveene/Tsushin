'use client'

import { useState } from 'react'

interface MongoAtlasConfigFormProps {
  config: Record<string, any>
  onChange: (config: Record<string, any>) => void
  isEditing: boolean
}

export default function MongoAtlasConfigForm({ config, onChange, isEditing }: MongoAtlasConfigFormProps) {
  const [showKey, setShowKey] = useState(false)

  const update = (key: string, value: any) => {
    onChange({ ...config, [key]: value })
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm text-gray-300 mb-1">Cluster URI <span className="text-red-400">*</span></label>
        <input
          type="text"
          value={config.cluster_uri || ''}
          onChange={(e) => update('cluster_uri', e.target.value)}
          placeholder="mongodb+srv://user:pass@cluster.mongodb.net"
          className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
        />
        <p className="text-xs text-gray-500 mt-1">MongoDB connection string (credentials can be embedded in URI)</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Database Name <span className="text-red-400">*</span></label>
          <input
            type="text"
            value={config.database_name || ''}
            onChange={(e) => update('database_name', e.target.value)}
            placeholder="tsushin"
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-300 mb-1">Collection Name <span className="text-red-400">*</span></label>
          <input
            type="text"
            value={config.collection_name || ''}
            onChange={(e) => update('collection_name', e.target.value)}
            placeholder="vectors"
            className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] placeholder:text-gray-600 text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm text-gray-300 mb-1">Vector Index Name <span className="text-red-400">*</span></label>
          <input
            type="text"
            value={config.index_name || ''}
            onChange={(e) => update('index_name', e.target.value)}
            placeholder="vector_index"
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

      <div>
        <label className="block text-sm text-gray-300 mb-1">API Key (optional)</label>
        <div className="relative">
          <input
            type={showKey ? 'text' : 'password'}
            value={config.api_key || ''}
            onChange={(e) => update('api_key', e.target.value)}
            placeholder={isEditing ? '(unchanged)' : 'For Atlas Data API authentication'}
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

      <div className="flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-white/[0.02]">
        <button
          type="button"
          onClick={() => update('use_native_search', config.use_native_search === false)}
          className={`relative w-10 h-5 rounded-full transition-colors ${
            config.use_native_search === false ? 'bg-amber-500/80' : 'bg-white/10'
          }`}
        >
          <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
            config.use_native_search === false ? 'translate-x-5' : ''
          }`} />
        </button>
        <div>
          <span className="text-sm text-gray-300">Local Mode</span>
          <p className="text-xs text-gray-500">
            {config.use_native_search === false
              ? 'Using local cosine similarity (self-hosted MongoDB, no Atlas required)'
              : 'Using Atlas Vector Search ($vectorSearch aggregation)'}
          </p>
        </div>
      </div>
    </div>
  )
}
