'use client'

import { useEffect, useState } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import { api } from '@/lib/client'
import { LightningIcon, CheckCircleIcon, AlertTriangleIcon, SearchIcon } from '@/components/ui/icons'

/**
 * Step 5 — connection test + model discovery.
 *
 * For cloud providers we can use the unsaved variant of the test endpoint
 * so the user sees live feedback before committing. Model discovery populates
 * `available_models` which the Review step displays.
 */
export default function StepTestAndModels() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const { draft } = state
  const { vendor, hosting, modality } = draft

  const [testing, setTesting] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [modelInput, setModelInput] = useState('')
  const [predefined, setPredefined] = useState<string[]>([])

  // TTS providers don't expose `available_models` the same way LLMs do — they
  // ship a fixed voice/model catalog discoverable via /api/tts-providers/.
  // The TTS save path (StepProgress branch 1+2) doesn't read `available_models`
  // either, so this step has nothing meaningful to ask. Auto-complete and
  // hide the LLM-shaped UI when modality === 'tts'.
  const isTTS = modality === 'tts'
  const isImage = modality === 'image'

  // The backend `ProviderInstanceCreate` schema requires
  // `available_models.length >= 1` — POSTing with an empty list returns 400.
  // Previously this step always marked complete and the empty state copy
  // hinted "Auto-detect after saving", which is false: save fails without
  // models. Gate Next on having at least one model (entered manually,
  // added from suggestions, or populated via Auto-detect). TTS modality
  // bypasses this gate (see comment above).
  useEffect(() => {
    markStepComplete('testAndModels', isTTS || draft.available_models.length > 0)
  }, [markStepComplete, isTTS, draft.available_models.length])

  // Load curated model suggestions once. Image setup intentionally uses
  // provider-specific image-only buckets so image model IDs appear there
  // without polluting normal LLM model suggestions.
  useEffect(() => {
    const predefinedKey = isImage && vendor
      ? `${vendor}_image`
      : (vendor || '')
    api.getPredefinedModels()
      .then(m => setPredefined(m?.[predefinedKey] || []))
      .catch(() => {})
  }, [vendor, isImage])

  const runTest = async () => {
    if (!vendor) return
    setTesting(true)
    try {
      const body = {
        vendor,
        base_url: draft.base_url || undefined,
        api_key: vendor === 'vertex_ai'
          ? (draft.extra_config?.private_key || undefined)
          : (draft.api_key || undefined),
        model: isImage ? undefined : draft.available_models[0],
        extra_config: vendor === 'vertex_ai'
          ? {
              project_id: draft.extra_config?.project_id,
              region: draft.extra_config?.region,
              sa_email: draft.extra_config?.sa_email,
            }
          : undefined,
      }
      const result = await api.testProviderConnectionRaw(body)
      patchDraft({ test_result: result })
    } catch (err: unknown) {
      patchDraft({
        test_result: {
          success: false,
          message: err instanceof Error ? err.message : 'Test failed',
        },
      })
    } finally {
      setTesting(false)
    }
  }

  const runDiscover = async () => {
    if (!vendor || !draft.api_key) return
    setDiscovering(true)
    try {
      const models = await api.discoverModelsRaw(vendor, draft.api_key, draft.base_url || undefined)
      if (models.length > 0) {
        patchDraft({ available_models: models })
      }
    } finally {
      setDiscovering(false)
    }
  }

  const addModel = () => {
    const v = modelInput.trim()
    if (!v) return
    if (draft.available_models.includes(v)) return
    patchDraft({ available_models: [...draft.available_models, v] })
    setModelInput('')
  }

  const removeModel = (m: string) => {
    patchDraft({ available_models: draft.available_models.filter(x => x !== m) })
  }

  const canTest = hosting === 'cloud' && (
    vendor === 'vertex_ai'
      ? !!draft.extra_config?.private_key
      : !!draft.api_key
  )

  const canDiscover = !isImage && vendor && ['gemini', 'openai', 'groq', 'grok', 'deepseek', 'openrouter'].includes(vendor) && !!draft.api_key
  const imageModelExample = vendor === 'openai' ? 'gpt-image-2' : 'imagen-4.0-generate-001'

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">
          {isImage ? 'Test & choose image models' : 'Test & choose models'}
        </h3>
        <p className="text-xs text-tsushin-slate">
          {isImage
            ? 'Run a connection test and pick which image models this setup should expose.'
            : 'Optional but recommended — run a connection test and pick which models this instance will expose to your agents.'}
        </p>
      </div>

      {/* Test connection */}
      {hosting === 'cloud' && (
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={runTest}
            disabled={!canTest || testing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-tsushin-accent/30 text-tsushin-accent bg-tsushin-accent/5 hover:bg-tsushin-accent/10 transition-colors disabled:opacity-50"
          >
            <LightningIcon size={14} />
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
          {draft.test_result && (
            <span className={`text-xs flex items-center gap-1.5 ${draft.test_result.success ? 'text-tsushin-success' : 'text-tsushin-vermilion'}`}>
              {draft.test_result.success ? <CheckCircleIcon size={14} /> : <AlertTriangleIcon size={14} />}
              {draft.test_result.message}
              {draft.test_result.latency_ms !== undefined && draft.test_result.success && (
                <span className="text-tsushin-slate ml-1">({draft.test_result.latency_ms}ms)</span>
              )}
            </span>
          )}
        </div>
      )}

      {/* TTS modality: voices/models live in /api/tts-providers/{provider}/voices
          and /models — selected per-agent in the Audio Wizard, not at credential
          creation time. We surface a short hint instead of the LLM-shaped
          model picker. */}
      {isTTS && (
        <div className="rounded-lg border border-tsushin-border bg-tsushin-ink/40 p-3">
          <div className="text-sm text-white font-medium mb-1">Voices & TTS models</div>
          <div className="text-xs text-tsushin-slate">
            {vendor === 'gemini'
              ? 'Picked per-agent in the Audio Agents Wizard. Three preview models (Fast / Balanced / Quality) and 30 prebuilt voices are available — no setup required here.'
              : vendor === 'openai'
              ? '6 voices (alloy, nova, echo, fable, onyx, shimmer) — picked per-agent in the Audio Agents Wizard.'
              : 'Voices are picked per-agent in the Audio Agents Wizard.'}
          </div>
        </div>
      )}

      {/* Models (LLM/Image only) */}
      {!isTTS && (
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm font-medium text-tsushin-fog">Models</label>
          {canDiscover && (
            <button
              onClick={runDiscover}
              disabled={discovering}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md border border-tsushin-accent/30 text-tsushin-accent bg-tsushin-accent/5 hover:bg-tsushin-accent/10 transition-colors disabled:opacity-50"
            >
              <SearchIcon size={12} />
              {discovering ? 'Discovering...' : 'Auto-detect'}
            </button>
          )}
        </div>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={modelInput}
            onChange={e => setModelInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addModel() } }}
            list="wiz-models-suggestions"
            placeholder={predefined.length > 0
              ? (isImage ? 'Pick an image model suggestion or type a custom ID...' : 'Pick a suggestion or type a custom ID...')
              : (isImage ? `Image model name (e.g. ${imageModelExample})` : 'Model name (e.g. gpt-4o)')}
            className="flex-1 px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 text-sm"
          />
          <datalist id="wiz-models-suggestions">
            {predefined.map(m => <option key={m} value={m} />)}
          </datalist>
          <button
            onClick={addModel}
            disabled={!modelInput.trim()}
            className="px-3 py-2 text-sm font-medium rounded-lg border border-tsushin-border text-tsushin-fog hover:text-white hover:border-white/20 transition-colors disabled:opacity-30"
          >
            Add
          </button>
        </div>
        {draft.available_models.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {draft.available_models.map(m => (
              <span key={m} className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-tsushin-indigo/10 text-tsushin-indigo border border-tsushin-indigo/20 rounded-md text-xs font-mono">
                {m}
                <button onClick={() => removeModel(m)} className="text-tsushin-indigo/60 hover:text-tsushin-indigo transition-colors">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-[11px] text-tsushin-vermilion">
            At least one {isImage ? 'image model' : 'model'} is required before you can create the instance.
            {canDiscover ? ' Use Auto-detect above, or type a model name and click Add.' : ' Pick a suggestion or type a custom model ID, then click Add.'}
          </p>
        )}
      </div>
      )}

      {/* Default instance — only meaningful for paths that create a real
          instance row (ProviderInstance for LLM/Image, TTSInstance for Kokoro).
          Cloud TTS via api_keys (ElevenLabs / OpenAI / Gemini) has at most one
          api_key per service per tenant, so the concept of "default" doesn't
          apply — hide the toggle. */}
      {!(isTTS && (vendor === 'elevenlabs' || vendor === 'openai' || vendor === 'gemini')) && (
      <label className="flex items-center gap-3 cursor-pointer p-3 bg-tsushin-ink rounded-lg border border-tsushin-border">
        <input
          type="checkbox"
          checked={draft.is_default}
          onChange={e => patchDraft({ is_default: e.target.checked })}
          className="w-4 h-4 rounded accent-tsushin-indigo"
        />
        <div>
          <div className="text-sm font-medium text-white">Set as default for {vendor}</div>
          <div className="text-xs text-tsushin-slate">Agents that reference this vendor without a specific instance will use this one.</div>
        </div>
      </label>
      )}
    </div>
  )
}
