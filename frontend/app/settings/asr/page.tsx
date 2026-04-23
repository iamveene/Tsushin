'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, ASRInstance } from '@/lib/client'

const MEM_LIMIT_OPTIONS = ['1g', '1.5g', '2g', '3g']

const HEALTH_COLORS: Record<string, string> = {
  healthy: 'bg-emerald-400',
  degraded: 'bg-amber-400',
  unavailable: 'bg-red-400',
  unknown: 'bg-gray-400',
}

const CONTAINER_LABELS: Record<string, string> = {
  none: 'Not provisioned',
  creating: 'Creating',
  provisioning: 'Provisioning',
  running: 'Running',
  stopped: 'Stopped',
  error: 'Error',
}

const DEFAULT_MODEL = 'Systran/faster-distil-whisper-small.en'

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function ASRSettingsPage() {
  const { loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [instances, setInstances] = useState<ASRInstance[]>([])
  const [selectedDefaultId, setSelectedDefaultId] = useState<number | null>(null)
  const [savedDefaultId, setSavedDefaultId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingDefault, setSavingDefault] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [creating, setCreating] = useState(false)
  const [actingId, setActingId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [form, setForm] = useState({
    instance_name: 'Local Whisper',
    description: '',
    default_model: DEFAULT_MODEL,
    mem_limit: '1.5g',
    auto_provision: true,
  })

  async function loadData({ silent = false }: { silent?: boolean } = {}) {
    if (!silent) setLoading(true)
    setError('')
    try {
      const [instanceList, defaultData] = await Promise.all([
        api.getASRInstances(),
        api.getDefaultASRInstance(),
      ])
      setInstances(instanceList)
      setSelectedDefaultId(defaultData.default_asr_instance_id)
      setSavedDefaultId(defaultData.default_asr_instance_id)
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to load ASR settings'))
    } finally {
      if (!silent) setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    if (authLoading) return
    const timer = window.setTimeout(() => {
      void loadData()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [authLoading])

  useEffect(() => {
    if (!instances.some(inst => inst.container_status === 'creating' || inst.container_status === 'provisioning')) {
      return
    }
    const timer = window.setInterval(() => {
      void loadData({ silent: true })
    }, 5000)
    return () => window.clearInterval(timer)
  }, [instances])

  const selectedDefaultInstance = useMemo(
    () => instances.find(inst => inst.id === selectedDefaultId) || null,
    [instances, selectedDefaultId],
  )

  const hasDefaultChanges = selectedDefaultId !== savedDefaultId

  const handleSaveDefault = async (nextDefaultId: number | null = selectedDefaultId) => {
    setSavingDefault(true)
    setError('')
    setSuccess('')
    try {
      await api.setDefaultASRInstance(nextDefaultId)
      setSelectedDefaultId(nextDefaultId)
      setSavedDefaultId(nextDefaultId)
      setSuccess(nextDefaultId ? 'Default ASR instance updated.' : 'Default ASR reset to OpenAI Whisper.')
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to save default ASR setting'))
    } finally {
      setSavingDefault(false)
    }
  }

  const handleCreate = async () => {
    if (!form.instance_name.trim()) {
      setError('Instance name is required.')
      return
    }
    setCreating(true)
    setError('')
    setSuccess('')
    try {
      const created = await api.createASRInstance({
        vendor: 'speaches',
        instance_name: form.instance_name.trim(),
        description: form.description.trim() || undefined,
        auto_provision: form.auto_provision,
        mem_limit: form.auto_provision ? form.mem_limit : undefined,
        default_model: form.default_model.trim() || DEFAULT_MODEL,
      })
      setSuccess(
        created.container_status === 'provisioning'
          ? `Created ${created.instance_name}. Provisioning has started.`
          : `Created ${created.instance_name}.`,
      )
      await loadData({ silent: true })
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to create ASR instance'))
    } finally {
      setCreating(false)
    }
  }

  const handleContainerAction = async (instanceId: number, action: 'start' | 'stop' | 'restart') => {
    setActingId(instanceId)
    setError('')
    setSuccess('')
    try {
      await api.asrContainerAction(instanceId, action)
      setSuccess(`Instance ${action} requested.`)
      await loadData({ silent: true })
    } catch (error: unknown) {
      setError(getErrorMessage(error, `Failed to ${action} instance`))
    } finally {
      setActingId(null)
    }
  }

  const handleDelete = async (instanceId: number, instanceName: string) => {
    const confirmed = window.confirm(`Delete ASR instance "${instanceName}"?`)
    if (!confirmed) return
    setActingId(instanceId)
    setError('')
    setSuccess('')
    try {
      await api.deleteASRInstance(instanceId)
      setSuccess(`Deleted ${instanceName}.`)
      await loadData({ silent: true })
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to delete ASR instance'))
    } finally {
      setActingId(null)
    }
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-[#07070d] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-teal-400" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#07070d] text-white p-6 max-w-5xl mx-auto">
      <Link href="/settings" className="text-sm text-gray-400 hover:text-teal-400 transition-colors">
        &larr; Back to Settings
      </Link>

      <div className="mt-6 mb-8">
        <h1 className="text-2xl font-bold text-white">ASR / Whisper Settings</h1>
        <p className="text-gray-400 mt-1">
          Choose how audio transcription resolves by default, and provision local Speaches/Whisper instances for this tenant.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300 text-sm">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm">{success}</div>
      )}

      <div className="bg-[#12121a] border border-white/5 rounded-xl p-6 mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold text-white mb-1">Default transcription path</h2>
            <p className="text-sm text-gray-400">
              Agents using the tenant default will follow this setting. Choosing no local instance keeps the existing OpenAI Whisper behavior.
            </p>
          </div>
          <button
            onClick={() => {
              setRefreshing(true)
              void loadData({ silent: true })
            }}
            className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300 hover:bg-white/10 transition-colors"
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <div className="mt-5 space-y-3">
          <label className="block text-sm font-medium text-gray-200">Tenant default ASR backend</label>
          <select
            value={selectedDefaultId ?? ''}
            onChange={(e) => setSelectedDefaultId(e.target.value ? Number(e.target.value) : null)}
            disabled={!canEdit}
            className="w-full px-3 py-2.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
          >
            <option value="">OpenAI Whisper (cloud default)</option>
            {instances.map(inst => (
              <option key={inst.id} value={inst.id}>
                {inst.instance_name} ({inst.vendor}){inst.container_status ? ` · ${CONTAINER_LABELS[inst.container_status] || inst.container_status}` : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => void handleSaveDefault()}
            disabled={!canEdit || !hasDefaultChanges || savingDefault}
            className="px-4 py-2 rounded-lg bg-teal-500 text-white text-sm font-medium hover:bg-teal-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {savingDefault ? 'Saving...' : 'Save default'}
          </button>
        </div>

        <div className="mt-5 p-4 rounded-lg bg-white/[0.02] border border-white/5 text-sm">
          {selectedDefaultInstance ? (
            <div className="space-y-1 text-gray-300">
              <div className="font-medium text-white">Using local ASR by default: {selectedDefaultInstance.instance_name}</div>
              <div>Model: <span className="font-mono text-xs">{selectedDefaultInstance.default_model || DEFAULT_MODEL}</span></div>
              {selectedDefaultInstance.base_url && (
                <div>Endpoint: <span className="text-gray-400">{selectedDefaultInstance.base_url}</span></div>
              )}
              <div>
                Container: <span className="text-gray-400">{CONTAINER_LABELS[selectedDefaultInstance.container_status || 'none'] || selectedDefaultInstance.container_status || 'none'}</span>
              </div>
            </div>
          ) : (
            <div className="space-y-1 text-gray-300">
              <div className="font-medium text-white">Using OpenAI Whisper by default</div>
              <div>Agent-level overrides can still pin a local ASR instance or continue using OpenAI explicitly.</div>
            </div>
          )}
        </div>
      </div>

      <div className="bg-[#12121a] border border-white/5 rounded-xl p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-1">Provision a local Speaches / Whisper instance</h2>
        <p className="text-sm text-gray-400 mb-5">
          This creates a tenant-scoped OpenAI-compatible transcription endpoint. Auto-provisioning will start a managed container on the reserved ASR port range.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-200 mb-1">Instance name</label>
            <input
              value={form.instance_name}
              onChange={(e) => setForm(prev => ({ ...prev, instance_name: e.target.value }))}
              disabled={!canEdit}
              className="w-full px-3 py-2.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              placeholder="Local Whisper"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-200 mb-1">Memory limit</label>
            <select
              value={form.mem_limit}
              onChange={(e) => setForm(prev => ({ ...prev, mem_limit: e.target.value }))}
              disabled={!canEdit || !form.auto_provision}
              className="w-full px-3 py-2.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
            >
              {MEM_LIMIT_OPTIONS.map(limit => (
                <option key={limit} value={limit}>{limit}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-200 mb-1">Default model</label>
            <input
              value={form.default_model}
              onChange={(e) => setForm(prev => ({ ...prev, default_model: e.target.value }))}
              disabled={!canEdit}
              className="w-full px-3 py-2.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm font-mono focus:border-teal-500/50 focus:outline-none"
              placeholder={DEFAULT_MODEL}
            />
            <p className="mt-1 text-xs text-gray-500">Use a Hugging Face-style model id supported by Speaches/faster-whisper.</p>
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-200 mb-1">Description (optional)</label>
            <input
              value={form.description}
              onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
              disabled={!canEdit}
              className="w-full px-3 py-2.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              placeholder="PT/EN local transcription node"
            />
          </div>
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={form.auto_provision}
            onChange={(e) => setForm(prev => ({ ...prev, auto_provision: e.target.checked }))}
            disabled={!canEdit}
          />
          Auto-provision the local container now
        </label>

        <div className="mt-5">
          <button
            onClick={handleCreate}
            disabled={!canEdit || creating}
            className="px-4 py-2 rounded-lg bg-teal-500 text-white text-sm font-medium hover:bg-teal-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {creating ? 'Creating...' : 'Create local ASR instance'}
          </button>
        </div>
      </div>

      <div className="bg-[#12121a] border border-white/5 rounded-xl p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-1">Existing local instances</h2>
        <p className="text-sm text-gray-400 mb-5">
          Create one instance per preferred language/model profile, then let agents use the tenant default or pin a specific instance.
        </p>

        {instances.length === 0 ? (
          <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5 text-sm text-gray-400">
            No local ASR instances yet. OpenAI Whisper remains the default until you provision one above.
          </div>
        ) : (
          <div className="space-y-4">
            {instances.map(inst => {
              const isDefault = savedDefaultId === inst.id
              const statusLabel = CONTAINER_LABELS[inst.container_status || 'none'] || inst.container_status || 'Unknown'
              return (
                <div key={inst.id} className="p-4 rounded-xl border border-white/8 bg-white/[0.02]">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-white font-medium">{inst.instance_name}</span>
                        {isDefault && (
                          <span className="px-2 py-0.5 rounded-full text-xs bg-teal-500/20 border border-teal-500/30 text-teal-300">Tenant default</span>
                        )}
                        <span className="px-2 py-0.5 rounded-full text-xs bg-white/5 border border-white/10 text-gray-300">{inst.vendor}</span>
                        {inst.is_auto_provisioned && (
                          <span className="px-2 py-0.5 rounded-full text-xs bg-sky-500/15 border border-sky-500/30 text-sky-200">Managed container</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-sm text-gray-400">
                        <span className={`w-2 h-2 rounded-full ${HEALTH_COLORS[inst.health_status] || 'bg-gray-400'}`} />
                        <span>{inst.health_status}</span>
                        <span>•</span>
                        <span>{statusLabel}</span>
                      </div>
                      <div className="text-xs text-gray-500 space-y-1">
                        <div>Model: <span className="font-mono">{inst.default_model || DEFAULT_MODEL}</span></div>
                        {inst.base_url && <div>Endpoint: <span className="text-gray-400">{inst.base_url}</span></div>}
                        {inst.container_port && <div>Port: <span className="text-gray-400">{inst.container_port}</span></div>}
                        {inst.health_status_reason && <div>Reason: <span className="text-gray-400">{inst.health_status_reason}</span></div>}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      {!isDefault && (
                        <button
                          onClick={() => {
                            void handleSaveDefault(inst.id)
                          }}
                          disabled={!canEdit || actingId === inst.id}
                          className="px-3 py-1.5 rounded-lg bg-teal-500 text-white text-xs font-medium hover:bg-teal-400 disabled:opacity-40 transition-colors"
                        >
                          Set default
                        </button>
                      )}
                      <button
                        onClick={() => void handleContainerAction(inst.id, 'start')}
                        disabled={!canEdit || actingId === inst.id}
                        className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-gray-300 hover:bg-white/10 disabled:opacity-40 transition-colors"
                      >
                        Start
                      </button>
                      <button
                        onClick={() => void handleContainerAction(inst.id, 'restart')}
                        disabled={!canEdit || actingId === inst.id}
                        className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-gray-300 hover:bg-white/10 disabled:opacity-40 transition-colors"
                      >
                        Restart
                      </button>
                      <button
                        onClick={() => void handleContainerAction(inst.id, 'stop')}
                        disabled={!canEdit || actingId === inst.id}
                        className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-gray-300 hover:bg-white/10 disabled:opacity-40 transition-colors"
                      >
                        Stop
                      </button>
                      <button
                        onClick={() => void handleDelete(inst.id, inst.instance_name)}
                        disabled={!canEdit || actingId === inst.id}
                        className="px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-300 hover:bg-red-500/20 disabled:opacity-40 transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="bg-white/[0.02] border border-white/5 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Resolution order</h3>
        <div className="text-xs text-gray-500 space-y-1">
          <p>1. An agent can explicitly use OpenAI, the tenant default, or a specific local ASR instance.</p>
          <p>2. When an agent uses the tenant default, the selector above is applied.</p>
          <p>3. If no tenant default instance is set, Tsushin falls back to OpenAI Whisper automatically.</p>
          <p className="mt-2 text-gray-400">Per-agent overrides are available in the Audio Agent wizard, the regular Agent Wizard, and Agent Skills.</p>
        </div>
      </div>
    </div>
  )
}
