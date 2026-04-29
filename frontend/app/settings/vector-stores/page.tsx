'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, VectorStoreInstance, VectorStoreEmbeddingTestResult } from '@/lib/client'

const VENDOR_LABELS: Record<string, string> = {
  mongodb: 'MongoDB',
  pinecone: 'Pinecone',
  qdrant: 'Qdrant',
}

const STATUS_COLORS: Record<string, string> = {
  healthy: 'bg-emerald-400',
  unknown: 'bg-gray-400',
  unavailable: 'bg-red-400',
  degraded: 'bg-yellow-400',
}

export default function VectorStoresSettingsPage() {
  const { isLoading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [instances, setInstances] = useState<VectorStoreInstance[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [savedId, setSavedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  // v0.7.x Wave 2-D — per-instance embedding probe. Keyed by instance.id so a
  // future iteration that lists multiple rows can render results inline.
  const [embeddingTesting, setEmbeddingTesting] = useState<number | null>(null)
  const [embeddingResults, setEmbeddingResults] = useState<Record<number, VectorStoreEmbeddingTestResult>>({})
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (authLoading) return
    loadData()
  }, [authLoading])

  const loadData = async () => {
    setLoading(true)
    try {
      const [instanceList, defaultData] = await Promise.all([
        api.getVectorStoreInstances(),
        api.getDefaultVectorStore(),
      ])
      setInstances(instanceList)
      setSelectedId(defaultData.default_vector_store_instance_id)
      setSavedId(defaultData.default_vector_store_instance_id)
    } catch (e: any) {
      setError(e.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await api.updateDefaultVectorStore(selectedId)
      setSavedId(selectedId)
      setSuccess('Default vector store updated successfully')
      setTimeout(() => setSuccess(''), 3000)
    } catch (e: any) {
      setError(e.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    if (!selectedId) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testVectorStoreConnection(selectedId)
      setTestResult(result)
    } catch (e: any) {
      setTestResult({ success: false, message: e.message || 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  const handleTestEmbedding = async (instanceId: number) => {
    setEmbeddingTesting(instanceId)
    setEmbeddingResults((prev) => {
      const next = { ...prev }
      delete next[instanceId]
      return next
    })
    try {
      const result = await api.testEmbedding(instanceId, 'OAuth token refresh failure')
      setEmbeddingResults((prev) => ({ ...prev, [instanceId]: result }))
    } catch (e: any) {
      setEmbeddingResults((prev) => ({
        ...prev,
        [instanceId]: {
          success: false,
          dims: 0,
          sample_norm: 0,
          latency_ms: 0,
          provider: '',
          model: '',
          error: e?.message || 'Embedding test failed',
        },
      }))
    } finally {
      setEmbeddingTesting(null)
    }
  }

  const selectedInstance = instances.find(i => i.id === selectedId)
  const hasChanges = selectedId !== savedId

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#07070d] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-teal-400" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#07070d] text-white p-6 max-w-4xl mx-auto">
      <Link href="/settings" className="text-sm text-gray-400 hover:text-teal-400 transition-colors">
        &larr; Back to Settings
      </Link>

      <div className="mt-6 mb-8">
        <h1 className="text-2xl font-bold text-white">Vector Store Configuration</h1>
        <p className="text-gray-400 mt-1">Select the default vector store for agent long-term memory</p>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">{success}</div>
      )}

      {/* Default Vector Store Selector */}
      <div className="bg-[#12121a] border border-white/5 rounded-xl p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-1">Default Vector Store</h2>
        <p className="text-sm text-gray-400 mb-4">
          All agents will use this vector store unless they have a per-agent override configured in Agent Builder.
        </p>

        <select
          value={selectedId ?? ''}
          onChange={(e) => {
            const val = e.target.value
            setSelectedId(val === '' ? null : parseInt(val))
            setTestResult(null)
          }}
          disabled={!canEdit}
          className="w-full px-3 py-2.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
        >
          <option value="">ChromaDB (built-in)</option>
          {instances.map(inst => (
            <option key={inst.id} value={inst.id}>
              {inst.instance_name} ({VENDOR_LABELS[inst.vendor] || inst.vendor})
              {inst.is_auto_provisioned ? ' - Provisioned' : ''}
            </option>
          ))}
        </select>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={!canEdit || !hasChanges || saving}
            className="px-4 py-2 rounded-lg bg-teal-500 text-white text-sm font-medium hover:bg-teal-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
          {selectedId && (
            <button
              onClick={handleTest}
              disabled={testing}
              className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-gray-300 text-sm hover:bg-white/10 disabled:opacity-40 transition-colors"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
          )}
        </div>

        {testResult && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${testResult.success ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400' : 'bg-red-500/10 border border-red-500/20 text-red-400'}`}>
            {testResult.message}
          </div>
        )}
      </div>

      {/* Selected Instance Info */}
      {selectedInstance && (
        <div className="bg-[#12121a] border border-white/5 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-3 mb-3">
            <div className={`w-2 h-2 rounded-full ${STATUS_COLORS[selectedInstance.health_status] || 'bg-gray-400'}`} />
            <span className="text-white font-medium">{selectedInstance.instance_name}</span>
            <span className="text-xs px-2 py-0.5 rounded bg-teal-500/20 text-teal-400">
              {VENDOR_LABELS[selectedInstance.vendor] || selectedInstance.vendor}
            </span>
            {selectedInstance.is_auto_provisioned && (
              <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-400">Provisioned</span>
            )}
          </div>
          <div className="space-y-1 text-sm text-gray-400">
            {selectedInstance.base_url && <p>Endpoint: <span className="text-gray-300">{selectedInstance.base_url}</span></p>}
            {selectedInstance.extra_config?.collection_name && (
              <p>Collection: <span className="text-gray-300">{selectedInstance.extra_config.collection_name}</span></p>
            )}
            {selectedInstance.container_port && (
              <p>Port: <span className="text-gray-300">{selectedInstance.container_port}</span></p>
            )}
            <p>Health: <span className={selectedInstance.health_status === 'healthy' ? 'text-emerald-400' : 'text-gray-300'}>
              {selectedInstance.health_status}
            </span></p>
            {/* v0.7.x Wave 2-D: surface the embedding provider/dims pair so
                operators can see what model the recap loop will use without
                cracking open extra_config raw JSON. */}
            <p>Embedding: <span className="text-gray-300">
              {selectedInstance.extra_config?.embedding_provider || '—'}
              {selectedInstance.extra_config?.embedding_dims
                ? ` · ${selectedInstance.extra_config.embedding_dims}d`
                : ''}
            </span></p>
          </div>

          {/* v0.7.x Wave 2-D: Test Embedding button — probes the configured
              embedding provider with a short test phrase and reports
              dims/provider/model/latency or surfaces an inline error. */}
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={() => handleTestEmbedding(selectedInstance.id)}
              disabled={embeddingTesting === selectedInstance.id}
              className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-300 text-xs hover:bg-white/10 disabled:opacity-40 transition-colors"
            >
              {embeddingTesting === selectedInstance.id ? 'Testing embedding…' : 'Test Embedding'}
            </button>
          </div>

          {embeddingResults[selectedInstance.id] && (
            <div
              className={`mt-3 p-3 rounded-lg text-xs ${
                embeddingResults[selectedInstance.id].success
                  ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-300'
                  : 'bg-red-500/10 border border-red-500/20 text-red-300'
              }`}
            >
              {embeddingResults[selectedInstance.id].success ? (
                <span>
                  success ✓ | dims={embeddingResults[selectedInstance.id].dims}
                  {' | '}
                  provider={embeddingResults[selectedInstance.id].provider}
                  {' | '}
                  model={embeddingResults[selectedInstance.id].model}
                  {' | '}
                  latency_ms={embeddingResults[selectedInstance.id].latency_ms}
                </span>
              ) : (
                <span>error ✗ | {embeddingResults[selectedInstance.id].error || 'unknown error'}</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Resolution Chain Info */}
      <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">How it works</h3>
        <div className="text-xs text-gray-500 space-y-1">
          <p>1. If an agent has a per-agent vector store override (Agent Builder), it uses that.</p>
          <p>2. Otherwise, it uses the tenant default selected above.</p>
          <p>3. If no default is set, ChromaDB (built-in) is used automatically.</p>
          <p className="mt-2 text-gray-400">Configure vector store connections in <Link href="/hub" className="text-teal-400 hover:underline">Hub &gt; Vector Stores</Link>.</p>
        </div>
      </div>
    </div>
  )
}
