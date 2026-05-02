'use client'

/**
 * ProviderInstancePicker — single source of truth UI for "which LLM is this
 * agent / playground call going to use?".
 *
 * v0.7.0: consolidates the previously divergent provider-selection logic from
 *  - components/AgentConfigurationManager.tsx (Studio agent edit modal)
 *  - components/agent-wizard/steps/StepBasics.tsx (agent creation wizard)
 *  - components/playground/ConfigPanel.tsx (playground per-thread overrides)
 *
 * Backed by GET /api/llm-providers/catalog so vendors and instances stay in
 * lockstep across all surfaces. Supports inline creation of a new instance
 * via the existing ProviderInstanceModal so the user never has to bounce
 * over to Hub to wire up Ollama/OpenAI/etc. before finishing their agent.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  api,
  LlmCatalogVendor,
  LlmCatalogInstance,
  ProviderInstance,
} from '@/lib/client'
import ProviderInstanceModal from '@/components/providers/ProviderInstanceModal'

export interface ProviderPickerValue {
  vendor: string
  instance_id: number | null
  model_name: string
}

interface Props {
  value: ProviderPickerValue
  onChange: (next: ProviderPickerValue) => void
  /** Compact = single row of selects; default = stacked with labels. */
  layout?: 'default' | 'compact'
  /** Disable inline create CTA (e.g. read-only contexts). */
  allowCreate?: boolean
  /** Force-refetch the catalog. Bumping this number triggers a reload. */
  refreshKey?: number
  /** Notify parent after a new instance is created via inline-create. */
  onInstanceCreated?: (instance: ProviderInstance) => void
  /** Optional className for the outer wrapper. */
  className?: string
}

const FALLBACK_DEFAULT_MODELS: Record<string, string[]> = {
  // Used only when the catalog has zero instances for a vendor — we still
  // want the user to pick a model so the create flow can validate it later.
  ollama: ['llama3.2:3b', 'gemma4:latest', 'phi4:latest'],
  openai: ['gpt-4.1-mini', 'gpt-4.1', 'o4-mini'],
  anthropic: ['claude-sonnet-4.6', 'claude-opus-4.7'],
  gemini: ['gemini-2.5-flash', 'gemini-2.5-pro'],
}

export default function ProviderInstancePicker({
  value,
  onChange,
  layout = 'default',
  allowCreate = true,
  refreshKey = 0,
  onInstanceCreated,
  className,
}: Props) {
  const [catalog, setCatalog] = useState<LlmCatalogVendor[]>([])
  const [loading, setLoading] = useState(true)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createDefaultVendor, setCreateDefaultVendor] = useState<string | undefined>(undefined)

  // Load + refresh catalog
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .getLlmProvidersCatalog()
      .then((data) => {
        if (!cancelled) setCatalog(data)
      })
      .catch(() => {
        if (!cancelled) setCatalog([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  const currentVendor: LlmCatalogVendor | undefined = useMemo(
    () => catalog.find((v) => v.vendor === value.vendor),
    [catalog, value.vendor],
  )
  const currentInstance: LlmCatalogInstance | undefined = useMemo(
    () => currentVendor?.instances.find((i) => i.id === value.instance_id),
    [currentVendor, value.instance_id],
  )

  // Effective model list: instance.available_models OR vendor fallback
  const modelOptions: string[] = useMemo(() => {
    if (currentInstance && currentInstance.available_models.length > 0) {
      return currentInstance.available_models
    }
    return FALLBACK_DEFAULT_MODELS[value.vendor] || []
  }, [currentInstance, value.vendor])

  // Whenever vendor changes, snap to that vendor's default-or-first instance
  // and the first model of that instance.
  const handleVendorChange = (vendor: string) => {
    const v = catalog.find((c) => c.vendor === vendor)
    if (!v) {
      onChange({ vendor, instance_id: null, model_name: value.model_name })
      return
    }
    const def = v.instances.find((i) => i.is_default) || v.instances[0]
    if (def) {
      const firstModel = def.available_models[0] || FALLBACK_DEFAULT_MODELS[vendor]?.[0] || ''
      onChange({ vendor, instance_id: def.id, model_name: firstModel })
    } else {
      // Vendor has no active instances — leave instance_id null. The UI
      // will surface the inline-create CTA below.
      const fallbackModel = FALLBACK_DEFAULT_MODELS[vendor]?.[0] || ''
      onChange({ vendor, instance_id: null, model_name: fallbackModel })
    }
  }

  const handleInstanceChange = (raw: string) => {
    const id = raw ? parseInt(raw, 10) : null
    if (id === null) {
      onChange({ ...value, instance_id: null })
      return
    }
    const inst = currentVendor?.instances.find((i) => i.id === id)
    if (inst) {
      const firstModel =
        inst.available_models[0] ||
        FALLBACK_DEFAULT_MODELS[value.vendor]?.[0] ||
        value.model_name
      onChange({ ...value, instance_id: id, model_name: firstModel })
    } else {
      onChange({ ...value, instance_id: id })
    }
  }

  const handleModelChange = (model: string) => {
    onChange({ ...value, model_name: model })
  }

  const openCreateModal = () => {
    setCreateDefaultVendor(value.vendor || undefined)
    setCreateModalOpen(true)
  }

  // After a successful create in ProviderInstanceModal, refetch the catalog
  // and auto-select the newly created instance for this picker.
  const handleCreated = async () => {
    setCreateModalOpen(false)
    // Refetch catalog
    let fresh: LlmCatalogVendor[] = []
    try {
      fresh = await api.getLlmProvidersCatalog()
      setCatalog(fresh)
    } catch {
      /* swallow — UI already shows previous state */
    }
    // Find the new instance: most-recent-id for our vendor
    const v = fresh.find((c) => c.vendor === value.vendor)
    const ids = (v?.instances || []).map((i) => i.id)
    const newest = ids.length ? Math.max(...ids) : null
    if (newest && v) {
      const inst = v.instances.find((i) => i.id === newest)
      if (inst) {
        const firstModel =
          inst.available_models[0] ||
          FALLBACK_DEFAULT_MODELS[value.vendor]?.[0] ||
          value.model_name
        onChange({ vendor: value.vendor, instance_id: inst.id, model_name: firstModel })
        if (onInstanceCreated) {
          // Best-effort: convert catalog instance back to ProviderInstance shape
          // so the parent doesn't need a second fetch. Missing fields are
          // populated as the parent expects them via the catalog refetch.
          onInstanceCreated({
            id: inst.id,
            tenant_id: '',
            vendor: value.vendor,
            instance_name: inst.instance_name,
            base_url: inst.base_url,
            api_key_configured: false,
            api_key_preview: '',
            extra_config: null,
            available_models: inst.available_models,
            is_default: inst.is_default,
            is_active: true,
            health_status: inst.health_status,
            health_status_reason: inst.health_status_reason,
            last_health_check: null,
          })
        }
      }
    }
  }

  // Render
  const wrapperClass = className || (layout === 'compact' ? 'flex flex-wrap gap-2' : 'space-y-3')

  return (
    <div className={wrapperClass}>
      {loading && (
        <div className="text-xs text-tsushin-slate">Loading providers…</div>
      )}

      {!loading && (
        <>
          {/* Vendor select */}
          <div className={layout === 'compact' ? 'flex-1 min-w-[160px]' : ''}>
            {layout !== 'compact' && (
              <label className="block text-xs text-tsushin-slate mb-1">Provider</label>
            )}
            <select
              value={value.vendor || ''}
              onChange={(e) => handleVendorChange(e.target.value)}
              className="w-full px-3 py-2 bg-tsushin-surface border border-tsushin-border rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-teal-500/40"
              data-testid="provider-vendor-select"
            >
              <option value="">Select provider…</option>
              {catalog.map((v) => (
                <option key={v.vendor} value={v.vendor}>
                  {v.display_name}
                  {v.instances.length > 0 ? ` (${v.instances.length})` : ' (no instances)'}
                </option>
              ))}
            </select>
          </div>

          {/* Instance select / inline-create CTA */}
          {value.vendor && (
            <div className={layout === 'compact' ? 'flex-1 min-w-[180px]' : ''}>
              {layout !== 'compact' && (
                <label className="block text-xs text-tsushin-slate mb-1">Instance</label>
              )}
              {currentVendor && currentVendor.instances.length > 0 ? (
                <div className="flex gap-2">
                  <select
                    value={value.instance_id ?? ''}
                    onChange={(e) => handleInstanceChange(e.target.value)}
                    className="flex-1 px-3 py-2 bg-tsushin-surface border border-tsushin-border rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-teal-500/40"
                    data-testid="provider-instance-select"
                  >
                    {currentVendor.instances.map((inst) => (
                      <option
                        key={inst.id}
                        value={inst.id}
                        title={inst.health_status_reason || undefined}
                      >
                        {inst.instance_name}
                        {inst.is_default ? ' (default)' : ''}
                        {inst.health_status && inst.health_status !== 'healthy'
                          ? ` [${inst.health_status}]`
                          : ''}
                      </option>
                    ))}
                  </select>
                  {allowCreate && (
                    <button
                      type="button"
                      onClick={openCreateModal}
                      className="shrink-0 px-3 py-2 text-xs bg-teal-500/20 text-teal-400 hover:bg-teal-500/30 rounded-md border border-teal-500/40 focus:outline-none focus:ring-2 focus:ring-teal-500/40"
                      title={`Create another ${currentVendor.display_name} instance`}
                      data-testid="provider-instance-add"
                    >
                      + New
                    </button>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="px-3 py-2 rounded-md bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200">
                    No active instance for{' '}
                    <strong>{currentVendor?.display_name || value.vendor}</strong>.
                    {allowCreate && ' Create one below.'}
                  </div>
                  {allowCreate && (
                    <button
                      type="button"
                      onClick={openCreateModal}
                      className="w-full px-3 py-2 text-sm bg-teal-500/20 text-teal-300 hover:bg-teal-500/30 rounded-md border border-teal-500/40 focus:outline-none focus:ring-2 focus:ring-teal-500/40"
                      data-testid="provider-instance-create"
                    >
                      + Create {currentVendor?.display_name || value.vendor} instance
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Model select */}
          {value.vendor && (
            <div className={layout === 'compact' ? 'flex-1 min-w-[160px]' : ''}>
              {layout !== 'compact' && (
                <label className="block text-xs text-tsushin-slate mb-1">Model</label>
              )}
              {modelOptions.length > 0 ? (
                <select
                  value={value.model_name || ''}
                  onChange={(e) => handleModelChange(e.target.value)}
                  className="w-full px-3 py-2 bg-tsushin-surface border border-tsushin-border rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-teal-500/40"
                  data-testid="provider-model-select"
                >
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={value.model_name || ''}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder="Enter model name"
                  className="w-full px-3 py-2 bg-tsushin-surface border border-tsushin-border rounded-md text-sm text-white focus:outline-none focus:ring-2 focus:ring-teal-500/40"
                  data-testid="provider-model-input"
                />
              )}
            </div>
          )}
        </>
      )}

      {createModalOpen && (
        <ProviderInstanceModal
          isOpen={createModalOpen}
          onClose={() => setCreateModalOpen(false)}
          onSave={handleCreated}
          defaultVendor={createDefaultVendor}
        />
      )}
    </div>
  )
}
