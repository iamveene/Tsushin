'use client'

import { useEffect, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { VectorStoreInstance } from '@/lib/client'
import { isMemoryValid } from '@/lib/agent-wizard/reducer'

export default function StepMemory() {
  const { state, patchMemory, markStepComplete } = useAgentWizard()
  const [stores, setStores] = useState<VectorStoreInstance[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    api.getVectorStoreInstances().then(s => { setStores(s); setLoaded(true) }).catch(() => setLoaded(true))
  }, [])

  useEffect(() => {
    markStepComplete('memory', isMemoryValid(state.draft.memory))
  }, [state.draft.memory, markStepComplete])

  const mem = state.draft.memory

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Memory and knowledge</h3>
        <p className="text-sm text-gray-300">How should the agent remember conversations and access knowledge?</p>
      </div>

      <div className="space-y-2">
        {([
          { id: 'builtin', title: 'Built-in memory', desc: 'Lightweight ring buffer of recent turns. Fastest to set up.' },
          { id: 'semantic', title: 'Built-in + semantic', desc: 'Adds semantic search over learned facts (ChromaDB). Recommended for most agents.' },
          { id: 'vector', title: 'External vector store', desc: 'Use an external vector store (Pinecone, Qdrant, MongoDB) as the primary knowledge layer.' },
        ] as const).map(opt => {
          const selected = mem.mode === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => patchMemory({ mode: opt.id, enable_semantic_search: opt.id !== 'builtin' })}
              className={`w-full text-left p-3 rounded-xl border transition-colors ${
                selected ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="text-white font-medium text-sm">{opt.title}</div>
              <div className="text-xs text-gray-400 mt-0.5">{opt.desc}</div>
            </button>
          )
        })}
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">Remember last N turns: <span className="text-teal-400 font-mono">{mem.memory_size}</span></label>
        <input
          type="range"
          min={1}
          max={50}
          step={1}
          value={mem.memory_size}
          onChange={e => patchMemory({ memory_size: parseInt(e.target.value, 10) })}
          className="w-full accent-teal-500"
        />
      </div>

      {mem.mode === 'vector' && (
        <div className="space-y-2 pt-2 border-t border-white/5">
          <label className="block text-xs text-gray-400">Vector store *</label>
          {!loaded ? (
            <div className="text-xs text-gray-500">Loading stores…</div>
          ) : stores.length === 0 ? (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm text-amber-200">
              You don't have any vector stores yet. Create one at <a href="/hub?tab=vector-stores" className="underline">Hub → Vector Stores</a>, then return here.
            </div>
          ) : (
            <select
              value={mem.vector_store_instance_id ?? ''}
              onChange={e => patchMemory({ vector_store_instance_id: e.target.value ? Number(e.target.value) : null })}
              className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
            >
              <option value="">Select a store</option>
              {stores.map(s => <option key={s.id} value={s.id}>{s.instance_name} ({s.vendor})</option>)}
            </select>
          )}
        </div>
      )}
    </div>
  )
}
