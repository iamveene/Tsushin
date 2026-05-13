'use client'

import { useEffect, useState } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import { isCredentialsValid } from '@/lib/provider-wizard/reducer'
import { EyeIcon, EyeOffIcon, CheckCircleIcon, AlertTriangleIcon } from '@/components/ui/icons'
import { api } from '@/lib/client'

const VENDOR_DEFAULT_URLS: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  groq: 'https://api.groq.com/openai/v1',
  grok: 'https://api.x.ai/v1',
  openrouter: 'https://openrouter.ai/api/v1',
  deepseek: 'https://api.deepseek.com/v1',
  elevenlabs: 'https://api.elevenlabs.io/v1',
  custom: '',
}

const VERTEX_REGIONS = [
  { value: 'us-east5', label: 'us-east5 (Columbus)' },
  { value: 'us-central1', label: 'us-central1 (Iowa)' },
  { value: 'us-east4', label: 'us-east4 (Virginia)' },
  { value: 'us-west1', label: 'us-west1 (Oregon)' },
  { value: 'europe-west1', label: 'europe-west1 (Belgium)' },
  { value: 'europe-west4', label: 'europe-west4 (Netherlands)' },
  { value: 'asia-northeast1', label: 'asia-northeast1 (Tokyo)' },
  { value: 'asia-southeast1', label: 'asia-southeast1 (Singapore)' },
]

/**
 * Step 4 (cloud branch) — credentials and instance name.
 *
 * Vertex AI has its own field set (project_id, region, sa_email, private_key,
 * plus a JSON-paste helper that auto-fills those three fields). All other
 * vendors just need api_key + optional base_url.
 */
export default function StepCredentials() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const { draft } = state
  const { vendor } = draft
  const isVertex = vendor === 'vertex_ai'
  const isCustom = vendor === 'custom'
  const isOllamaHost = vendor === 'ollama' // only relevant if a future branch lands here

  const [showApiKey, setShowApiKey] = useState(false)
  const [vertexJsonPaste, setVertexJsonPaste] = useState('')

  useEffect(() => {
    markStepComplete('credentials', isCredentialsValid(draft))
  }, [draft, markStepComplete])

  const setField = (k: string, v: any) => patchDraft({ [k]: v } as any)
  const setExtra = (k: string, v: any) => patchDraft({ extra_config: { ...(draft.extra_config || {}), [k]: v } })

  const handleVertexJsonPaste = (value: string) => {
    setVertexJsonPaste(value)
    if (!value.trim()) return
    try {
      const parsed = JSON.parse(value)
      const patch: Record<string, any> = { ...(draft.extra_config || {}) }
      if (parsed.project_id) patch.project_id = parsed.project_id
      if (parsed.client_email) patch.sa_email = parsed.client_email
      if (parsed.private_key) patch.private_key = parsed.private_key
      patchDraft({ extra_config: patch })
    } catch {
      /* silently ignore — user may still be typing */
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">Connect your credentials</h3>
        <p className="text-xs text-tsushin-slate">We store the key encrypted and never expose it back to the browser after save.</p>
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
          placeholder={`e.g., ${vendor}-prod, ${vendor}-dev`}
          className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50"
        />
        <p className="text-[11px] text-tsushin-slate mt-1">A friendly label. You can have multiple instances per vendor — e.g. one prod, one dev.</p>
      </div>

      {isVertex ? (
        <>
          {/* Vertex JSON paste */}
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
              Paste Service Account JSON <span className="text-tsushin-slate text-xs font-normal">(auto-fills fields below)</span>
            </label>
            <textarea
              value={vertexJsonPaste}
              onChange={e => handleVertexJsonPaste(e.target.value)}
              placeholder="Paste your GCP service account JSON key here..."
              className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 h-24 font-mono text-xs resize-y"
            />
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
                GCP Project ID <span className="text-tsushin-vermilion">*</span>
              </label>
              <input
                type="text"
                value={draft.extra_config?.project_id || ''}
                onChange={e => setExtra('project_id', e.target.value)}
                placeholder="my-project-123"
                className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
                Region <span className="text-tsushin-vermilion">*</span>
              </label>
              <select
                value={draft.extra_config?.region || 'us-east5'}
                onChange={e => setExtra('region', e.target.value)}
                className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface"
              >
                {VERTEX_REGIONS.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
              Service Account Email <span className="text-tsushin-vermilion">*</span>
            </label>
            <input
              type="text"
              value={draft.extra_config?.sa_email || ''}
              onChange={e => setExtra('sa_email', e.target.value)}
              placeholder="name@project-id.iam.gserviceaccount.com"
              className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
              Private Key (PEM) <span className="text-tsushin-vermilion">*</span>
            </label>
            <textarea
              value={draft.extra_config?.private_key || ''}
              onChange={e => setExtra('private_key', e.target.value)}
              placeholder="Paste the PEM-encoded private key block"
              className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 h-32 font-mono text-xs resize-y"
            />
          </div>
        </>
      ) : (
        <>
          {/* Base URL */}
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
              Base URL {isCustom && <span className="text-tsushin-vermilion">*</span>}
              {!isCustom && <span className="text-tsushin-slate text-xs font-normal"> (optional)</span>}
            </label>
            <input
              type="text"
              value={draft.base_url}
              onChange={e => setField('base_url', e.target.value)}
              placeholder={VENDOR_DEFAULT_URLS[vendor || ''] || 'https://...'}
              className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50"
            />
            {!draft.base_url && !isCustom && (
              <p className="text-[11px] text-tsushin-slate mt-1">Leave empty to use the vendor default: {VENDOR_DEFAULT_URLS[vendor || ''] || 'N/A'}</p>
            )}
          </div>

          {/* API Key */}
          <div>
            <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
              API Key {!isOllamaHost && <span className="text-tsushin-vermilion">*</span>}
            </label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={draft.api_key}
                onChange={e => setField('api_key', e.target.value)}
                placeholder="sk-..."
                className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 pr-10 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-tsushin-slate hover:text-white transition-colors"
                title={showApiKey ? 'Hide' : 'Reveal'}
              >
                {showApiKey ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
