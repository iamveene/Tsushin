'use client'

import { useEffect, useRef } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import { api, authenticatedFetch } from '@/lib/client'
import type { ProviderInstanceCreate, TTSInstanceCreate } from '@/lib/client'
import { CheckCircleIcon, AlertTriangleIcon } from '@/components/ui/icons'

/**
 * Step 7 — terminal progress step. Fires the actual create call when entered.
 *
 * For cloud LLMs/Image: POST /api/provider-instances
 * For Ollama (local): POST /api/provider-instances with vendor=ollama, then
 *   provision container + optional model pulls.
 * For Kokoro (local TTS): POST /api/tts-instances (the TTS route auto-provisions
 *   the container when auto_provision=true).
 * For ElevenLabs (cloud TTS): save the api_key via the legacy api_keys surface —
 *   we rely on the same backend entry point as /hub/api-keys.
 *
 * Failures surface a Retry → back to Review. The `fireComplete` callback hands
 * control back to the Hub so it can refetch the instance list.
 */
export default function StepProgress() {
  const { state, setProgress, fireComplete, patchDraft, goToStep } = useProviderWizard()
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
      if (draft.modality === 'tts' && draft.vendor === 'kokoro') {
        const body: TTSInstanceCreate = {
          vendor: 'kokoro',
          instance_name: draft.instance_name,
          is_default: draft.is_default,
          auto_provision: true,
          mem_limit: draft.mem_limit || '1.5g',
        }
        const result = await api.createTTSInstance(body)
        createdInstanceId = result.id
        setProgress({ message: 'TTS container provisioning...' })
      }
      // Branch 2: TTS ElevenLabs — legacy api_keys surface (/api/api-keys)
      else if (draft.modality === 'tts' && draft.vendor === 'elevenlabs') {
        const res = await authenticatedFetch('/api/api-keys', {
          method: 'POST',
          body: JSON.stringify({
            service: 'elevenlabs',
            api_key: draft.api_key,
            is_active: true,
          }),
        })
        if (!res.ok) {
          const txt = await res.text().catch(() => '')
          throw new Error(`Failed to save ElevenLabs API key (${res.status}) ${txt}`)
        }
      }
      // Branch 3: LLM/Image cloud or Ollama local — /api/provider-instances
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
          // Vertex stores the key in extra_config.private_key, not api_key.
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
          } catch (_e) {
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
