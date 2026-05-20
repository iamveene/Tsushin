'use client'

import { useEffect, useRef } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import { api, authenticatedFetch } from '@/lib/client'
import type { ProviderInstanceCreate, TTSInstanceCreate, ASRInstanceCreate } from '@/lib/client'
import { CheckCircleIcon, AlertTriangleIcon } from '@/components/ui/icons'

/**
 * Step 7 — terminal progress step. Fires the actual create call when entered.
 *
 * For cloud LLMs/Image: POST /api/provider-instances
 * For Ollama (local): POST /api/provider-instances with vendor=ollama, then
 *   provision container + optional model pulls.
 * For Kokoro (local TTS): POST /api/tts-instances (the TTS route auto-provisions
 *   the container when auto_provision=true).
 * For OpenAI/Gemini (cloud TTS): POST /api/provider-instances — same path as LLM
 *   cloud, since the same vendor key powers both. The resolver picks the default
 *   instance per vendor.
 * For ElevenLabs (cloud TTS): POST /api/tts-instances with encrypted hosted
 *   provider credentials.
 *
 * Failures surface a Retry → back to Review. The `fireComplete` callback hands
 * control back to the Hub so it can refetch the instance list.
 */
export default function StepProgress() {
  const { state, setProgress, fireComplete, patchDraft, goToStep, markStepComplete } = useProviderWizard()
  const { draft } = state
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async () => {
    setProgress({ status: 'running', message: 'Creating instance...', failedStep: null })

    try {
      let createdInstanceId: number | null = null

      // Branch 1: TTS Kokoro (self-hosted) — /api/tts-instances
      // NOTE: default_voice/default_language/default_speed/default_format
      // are schema-supported on TTSInstanceCreate. The guided wizard doesn't
      // yet collect them (advanced KokoroSetupWizard does), so we forward the
      // same sane defaults here so the created instance has a usable voice
      // out of the box instead of nulls. Without this, picking Kokoro via
      // the guided path silently produced a TTS instance with no voice
      // config — same class of bug as BUG-582 (wizard value never reaches
      // the server), just in the opposite direction.
      if (draft.modality === 'tts' && draft.vendor === 'kokoro') {
        const body: TTSInstanceCreate = {
          vendor: 'kokoro',
          instance_name: draft.instance_name,
          is_default: draft.is_default,
          auto_provision: true,
          mem_limit: draft.mem_limit || '1.5g',
          default_voice: 'pf_dora',
          default_language: 'pt',
          default_speed: 1.0,
          default_format: 'opus',
        }
        const result = await api.createTTSInstance(body)
        createdInstanceId = result.id
        setProgress({ message: 'TTS container provisioning...' })
      }
      // Branch 2a: TTS cloud OpenAI / Gemini — create a real ProviderInstance.
      // Previously this branch wrote to the retired legacy api_key table,
      // which (a) silently overwrote any existing tenant-wide LLM key for the
      // same vendor, (b) discarded the wizard's `instance_name`, and (c) became
      // invisible after the Hub moved to ProviderInstances. Now both LLM and
      // OpenAI/Gemini TTS flows use the same ProviderInstance backbone, and
      // the instance_name round-trips to the DB for cleanup/audit.
      else if (
        draft.modality === 'tts' &&
        (draft.vendor === 'openai' || draft.vendor === 'gemini')
      ) {
        // POST /api/provider-instances enforces a non-empty `available_models`
        // list (the LLM-cloud branch fills it from a discovery call). For TTS,
        // voice selection happens per-agent in the Audio Agents Wizard, not on
        // the ProviderInstance row — so we seed a vendor-appropriate default
        // TTS model list here purely to satisfy the API contract. Edit/Refresh
        // on the instance card can update these later if new TTS models ship.
        const ttsModels =
          draft.vendor === 'openai'
            ? ['tts-1', 'tts-1-hd']
            : ['gemini-2.5-flash-preview-tts']
        const body: ProviderInstanceCreate = {
          vendor: draft.vendor,
          instance_name: draft.instance_name,
          api_key: draft.api_key || undefined,
          available_models: ttsModels,
          is_default: draft.is_default,
        }
        const result = await api.createProviderInstance(body)
        createdInstanceId = result.id
      }
      // Branch 2b: TTS cloud ElevenLabs — first-class hosted TTSInstance.
      else if (draft.modality === 'tts' && draft.vendor === 'elevenlabs') {
        if (!draft.api_key) {
          throw new Error('ElevenLabs API key is required.')
        }
        const body: TTSInstanceCreate = {
          vendor: 'elevenlabs',
          instance_name: draft.instance_name || 'ElevenLabs',
          api_key: draft.api_key,
          is_default: draft.is_default,
          auto_provision: false,
        }
        const result = await api.createTTSInstance(body)
        createdInstanceId = result.id
      }
      // Branch 3a: ASR cloud — no separate provider row required. The OpenAI
      // Whisper API call path reuses the OpenAI key already saved on the
      // tenant under the LLM > OpenAI provider; we don't create an ASR
      // instance for the cloud case (audio_transcript skill falls through
      // to OpenAI when no local instance is selected).
      else if (draft.modality === 'asr' && draft.hosting === 'cloud') {
        setProgress({ message: 'OpenAI Whisper API uses your OpenAI Provider Instance — nothing to provision.' })
        // Nothing to create; mark as done immediately.
      }
      // Branch 3b: ASR local (speaches / openai_whisper) — /api/asr-instances
      else if (draft.modality === 'asr' && draft.hosting === 'local') {
        const vendorOk = draft.vendor === 'speaches' || draft.vendor === 'openai_whisper'
        if (!vendorOk) {
          throw new Error('Pick an ASR engine first.')
        }
        const defaultModel =
          draft.vendor === 'openai_whisper'
            ? 'base'
            : 'Systran/faster-distil-whisper-small.en'
        const body: ASRInstanceCreate = {
          vendor: draft.vendor || 'openai_whisper',
          instance_name: draft.instance_name,
          auto_provision: draft.auto_provision !== false,
          mem_limit: draft.mem_limit || (draft.vendor === 'openai_whisper' ? '3g' : '4g'),
          default_model: defaultModel,
        }
        setProgress({ message: 'Creating ASR instance and starting container...' })
        const result = await api.createASRInstance(body)
        createdInstanceId = result.id
        // Notify any open agent-config panels so their instance pickers
        // refresh without the user having to close/reopen the modal.
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('tsushin:asr-instance-changed', {
            detail: { id: createdInstanceId, action: 'created' },
          }))
        }
      }
      // Branch 4: LLM/Image cloud or Ollama local — /api/provider-instances
      else {
        const body: ProviderInstanceCreate = {
          vendor: draft.vendor || '',
          instance_name: draft.instance_name,
          base_url: draft.base_url || undefined,
          api_key: draft.api_key || undefined,
          available_models: draft.available_models,
          is_default: draft.is_default,
        }
        if (draft.vendor === 'vertex_ai') {
          body.extra_config = {
            project_id: draft.extra_config?.project_id || '',
            region: draft.extra_config?.region || '',
            sa_email: draft.extra_config?.sa_email || '',
            private_key: draft.extra_config?.private_key || '',
          }
          // Vertex stores the private key on the typed ProviderInstance payload.
          body.api_key = undefined
        }
        const result = await api.createProviderInstance(body)
        createdInstanceId = result.id

        // Ollama post-create: provision the container if requested, then pull models.
        if (draft.vendor === 'ollama' && draft.hosting === 'local' && createdInstanceId) {
          setProgress({ message: 'Provisioning Ollama container...' })
          try {
            // Best-effort provision request — the exact endpoint varies by
            // backend version. If it fails, the user can still provision from
            // the Hub → AI Providers panel after the instance is created.
            await authenticatedFetch(`/api/settings/ollama/provision`, {
              method: 'POST',
              body: JSON.stringify({
                instance_id: createdInstanceId,
                mem_limit: draft.mem_limit || '4g',
                gpu_enabled: !!draft.gpu_enabled,
              }),
            })
          } catch {
            // Non-fatal — the user can still hit Provision from the Hub panel.
          }

          if ((draft.pull_models || []).length > 0) {
            setProgress({ message: `Pulling ${draft.pull_models!.length} model(s)...` })
            for (const m of draft.pull_models || []) {
              try { await api.pullOllamaModel(createdInstanceId, m) } catch { /* surface via panel */ }
            }
          }
        }
      }

      patchDraft({ created_instance_id: createdInstanceId })
      // Mark progress complete so SET_STEP to the post-create `assignAgents`
      // step passes canAccessStep (which requires every prior step in the
      // flow to be complete). Without this the "Link to agents →" button
      // from the Done footer would be a no-op.
      markStepComplete('progress', true)
      setProgress({ status: 'done', message: 'All set — your provider is ready.' })
      fireComplete(createdInstanceId)
    } catch (err: any) {
      setProgress({
        status: 'error',
        message: err?.message || 'Failed to create provider instance.',
        failedStep: 'review',
      })
    }
  }

  const { progressStatus, progressMessage } = state

  return (
    <div className="space-y-4 py-4">
      <div className="flex flex-col items-center justify-center text-center">
        {progressStatus === 'running' && (
          <>
            <div className="w-12 h-12 rounded-full border-4 border-teal-500/20 border-t-teal-500 animate-spin mb-4" />
            <h3 className="text-base font-semibold text-white mb-1">Working on it...</h3>
            <p className="text-xs text-tsushin-slate max-w-md">{progressMessage || 'Creating provider instance...'}</p>
          </>
        )}
        {progressStatus === 'done' && (
          <>
            <CheckCircleIcon size={48} className="text-tsushin-success mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">Ready!</h3>
            <p className="text-xs text-tsushin-slate max-w-md">{progressMessage}</p>
          </>
        )}
        {progressStatus === 'error' && (
          <>
            <AlertTriangleIcon size={48} className="text-tsushin-vermilion mb-3" />
            <h3 className="text-base font-semibold text-white mb-1">Something went wrong</h3>
            <p className="text-xs text-tsushin-vermilion max-w-md">{progressMessage}</p>
            <button
              onClick={() => {
                started.current = false
                goToStep('review')
              }}
              className="mt-4 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
            >
              ← Back to Review
            </button>
          </>
        )}
      </div>
    </div>
  )
}
