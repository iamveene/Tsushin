'use client'

import { useEffect } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'

function summarizeKey(apiKey: string, vendor: string | null, extra: Record<string, any> | undefined): string {
  if (vendor === 'vertex_ai') {
    const pk: string = (extra?.private_key || '') as string
    if (!pk) return '(not provided)'
    return `${pk.slice(0, 16)}…${pk.slice(-6)} (${pk.length} chars)`
  }
  if (!apiKey) return '(not provided)'
  return `${apiKey.slice(0, 4)}…${apiKey.slice(-4)}`
}

/**
 * Step 6 — review summary. Each row is click-to-edit which jumps the user
 * back to the relevant step.
 */
export default function StepReview() {
  const { state, markStepComplete, goToStep } = useProviderWizard()
  const { draft } = state

  useEffect(() => {
    markStepComplete('review', true)
  }, [markStepComplete])

  const rows: Array<{ label: string; value: React.ReactNode; editStep: Parameters<typeof goToStep>[0] | null }> = [
    {
      label: 'Modality',
      value: draft.modality === 'llm' ? 'Language Model' : draft.modality === 'tts' ? 'Text-to-Speech' : draft.modality === 'image' ? 'Image Generation' : '—',
      editStep: 'modality',
    },
    {
      label: 'Hosting',
      value: draft.hosting === 'cloud' ? 'Cloud / API' : draft.hosting === 'local' ? 'Self-hosted container' : '—',
      editStep: 'hosting',
    },
    { label: 'Vendor', value: draft.vendor || '—', editStep: 'vendor' },
    {
      label: 'Instance name',
      value: draft.instance_name || '(unnamed)',
      editStep: draft.hosting === 'local' ? 'container' : 'credentials',
    },
  ]

  if (draft.hosting === 'cloud') {
    if (draft.base_url) {
      rows.push({ label: 'Base URL', value: <span className="font-mono">{draft.base_url}</span>, editStep: 'credentials' })
    }
    rows.push({
      label: 'API Key',
      value: <span className="font-mono text-tsushin-accent">{summarizeKey(draft.api_key, draft.vendor, draft.extra_config)}</span>,
      editStep: 'credentials',
    })
    if (draft.vendor === 'vertex_ai') {
      rows.push({ label: 'GCP Project', value: draft.extra_config?.project_id || '—', editStep: 'credentials' })
      rows.push({ label: 'Region', value: draft.extra_config?.region || '—', editStep: 'credentials' })
      rows.push({ label: 'Service Account', value: <span className="font-mono text-xs break-all">{draft.extra_config?.sa_email || '—'}</span>, editStep: 'credentials' })
    }
  } else {
    rows.push({ label: 'Memory limit', value: draft.mem_limit || '—', editStep: 'container' })
    if (draft.vendor === 'ollama') {
      rows.push({ label: 'GPU', value: draft.gpu_enabled ? 'Enabled' : 'Disabled', editStep: 'container' })
      rows.push({
        label: 'Starter models',
        value: (draft.pull_models || []).length > 0
          ? <span className="font-mono text-xs">{(draft.pull_models || []).join(', ')}</span>
          : '(none — skipped)',
        editStep: 'pullModels',
      })
    }
  }

  rows.push({
    label: 'Models',
    value: draft.available_models.length > 0
      ? <span className="font-mono text-xs">{draft.available_models.join(', ')}</span>
      : '(none yet — auto-detect on save)',
    editStep: 'testAndModels',
  })
  rows.push({ label: 'Default instance', value: draft.is_default ? 'Yes' : 'No', editStep: 'testAndModels' })

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">Review</h3>
        <p className="text-xs text-tsushin-slate">One last look before creating. Click any row to jump back and edit.</p>
      </div>

      <div className="rounded-xl border border-tsushin-border bg-tsushin-ink/40 divide-y divide-white/5 overflow-hidden">
        {rows.map((r, i) => (
          <button
            key={i}
            onClick={() => r.editStep && goToStep(r.editStep)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-white/5 transition-colors"
          >
            <span className="text-xs uppercase tracking-wider text-tsushin-slate">{r.label}</span>
            <span className="text-sm text-white truncate ml-3 max-w-[60%] text-right">{r.value}</span>
          </button>
        ))}
      </div>

      <p className="text-[11px] text-tsushin-slate text-center">
        Click <span className="text-teal-400 font-semibold">Create</span> below to save. {draft.hosting === 'local' ? 'Provisioning the container may take 1–2 minutes.' : 'Your key is encrypted at rest.'}
      </p>
    </div>
  )
}
