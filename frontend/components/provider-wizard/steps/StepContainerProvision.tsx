'use client'

import { useEffect } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import { isContainerValid } from '@/lib/provider-wizard/reducer'

const MEM_LIMITS = [
  { value: '2g',  label: '2 GB — minimal' },
  { value: '4g',  label: '4 GB — recommended' },
  { value: '8g',  label: '8 GB — larger models' },
  { value: '16g', label: '16 GB — big models / concurrency' },
]

/**
 * Step 4 (local branch) — container provisioning options.
 *
 * This is a condensed configuration surface. The heavy-lifting wizards
 * (`OllamaSetupWizard`, `KokoroSetupWizard`) still exist and remain wired up
 * for power users via the Advanced fallback. For the guided path we collect
 * the essential settings here and let the Review → Progress steps drive the
 * actual provisioning through the same backend endpoints those wizards use.
 */
export default function StepContainerProvision() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const { draft } = state
  const vendor = draft.vendor || ''
  const isOllama = vendor === 'ollama'
  const isKokoro = vendor === 'kokoro'
  const isOpenAIWhisper = vendor === 'openai_whisper'
  const isSpeaches = vendor === 'speaches'
  const isASRLocal = isOpenAIWhisper || isSpeaches

  // Seed sensible defaults the first time the user lands on this step for
  // openai_whisper / speaches: ASR vendors need slightly different defaults
  // than the LLM-tuned 4 GB baseline.
  useEffect(() => {
    if (isOpenAIWhisper && (draft.mem_limit === '4g' || !draft.mem_limit)) {
      patchDraft({ mem_limit: '3g' })
    } else if (isSpeaches && (draft.mem_limit === '4g' || !draft.mem_limit)) {
      patchDraft({ mem_limit: '2g' })
    }
    // Seed instance_name so the Review row never shows "(unnamed)".
    if (isASRLocal && !draft.instance_name) {
      patchDraft({ instance_name: isOpenAIWhisper ? 'OpenAI Whisper' : 'Local Whisper' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendor])

  useEffect(() => {
    markStepComplete('container', isContainerValid(draft))
  }, [draft, markStepComplete])

  const setField = (k: string, v: any) => patchDraft({ [k]: v } as any)

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">Container setup</h3>
        <p className="text-xs text-tsushin-slate">
          Tsushin will provision a dedicated <span className="text-white font-medium">{isOllama ? 'Ollama' : isKokoro ? 'Kokoro' : isOpenAIWhisper ? 'OpenAI Whisper' : isSpeaches ? 'Speaches' : vendor}</span> container
          for this tenant. These settings can be adjusted later.
          {isOpenAIWhisper && (
            <> The <span className="font-mono text-white">base</span> model is loaded at boot and kept warm; switch to <span className="font-mono text-white">small</span>/<span className="font-mono text-white">large-v3</span>/<span className="font-mono text-white">turbo</span> later in Settings → ASR.</>
          )}
        </p>
      </div>

      {/* Instance name */}
      <div>
        <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
          Instance name <span className="text-tsushin-vermilion">*</span>
        </label>
        <input
          type="text"
          value={draft.instance_name}
          onChange={e => setField('instance_name', e.target.value)}
          placeholder={isOllama ? 'Ollama Local' : isKokoro ? 'Kokoro TTS' : `${vendor}-1`}
          className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50"
        />
      </div>

      {/* Memory limit */}
      <div>
        <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Memory limit</label>
        <select
          value={draft.mem_limit || '4g'}
          onChange={e => setField('mem_limit', e.target.value)}
          className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface"
        >
          {MEM_LIMITS.map(m => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>

      {/* GPU toggle (Ollama only). Kokoro runs CPU-only today. */}
      {isOllama && (
        <label className="flex items-start gap-3 p-3 bg-tsushin-ink rounded-lg border border-tsushin-border cursor-pointer">
          <input
            type="checkbox"
            checked={!!draft.gpu_enabled}
            onChange={e => setField('gpu_enabled', e.target.checked)}
            className="mt-0.5 accent-teal-500"
          />
          <div>
            <div className="text-sm font-medium text-white">GPU enabled</div>
            <div className="text-xs text-tsushin-slate">Requires an NVIDIA runtime on the host. Leave off if unsure.</div>
          </div>
        </label>
      )}

      <div className="p-3 bg-teal-500/5 border border-teal-500/20 rounded-lg">
        <p className="text-[11px] text-teal-200">
          When you click <span className="font-semibold">Next</span>, these settings are staged.
          The container is actually created on the <span className="font-semibold">Review → Create</span> step.
        </p>
      </div>
    </div>
  )
}
