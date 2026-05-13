'use client'

/**
 * Flow Creation Wizard — pre-built hybrid automations (programmatic + agentic)
 *
 * 3-step flow:
 *   1. pick     — template card grid
 *   2. params   — dynamic parameter form generated from template.params_schema
 *   3. preview  — summary of the flow that will be created
 *
 * Matches the existing CreateFlowModal visual language (slate-800 modal shell,
 * teal/cyan accents, rounded-2xl, backdrop-blur). See frontend/app/flows/page.tsx
 * line 1330 for the reference pattern.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type Agent,
  type Contact,
  type Persona,
  type CustomTool,
  type FlowTemplateSummary,
  type FlowTemplateParamSpec,
  type PasswordVaultIntegration,
} from '@/lib/client'
import PasswordVaultReferencePicker, { type PasswordVaultReferenceValue } from '@/components/password-vault/PasswordVaultReferencePicker'

type Step = 'pick' | 'params' | 'preview'

interface Props {
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  onClose: () => void
  onSuccess: (flowId: number, flowName: string) => void
}

const CATEGORY_BADGES: Record<string, { label: string; className: string }> = {
  productivity: { label: 'Productivity', className: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' },
  monitoring: { label: 'Monitoring', className: 'bg-amber-500/10 text-amber-400 border-amber-500/30' },
  welcome: { label: 'Welcome', className: 'bg-violet-500/10 text-violet-400 border-violet-500/30' },
  on_demand: { label: 'On-Demand', className: 'bg-sky-500/10 text-sky-400 border-sky-500/30' },
}

const ADVANCED_TEMPLATE_PARAM_KEYS = new Set([
  'browser_session_profile_name',
  'unit_id',
  'asset',
  'timezone',
])

function IconBadge({ icon }: { icon: string }) {
  // Map template icon keys to simple SVG glyphs (matches cockpit aesthetic)
  const paths: Record<string, string> = {
    mail: 'M3 8l7.89 5.26a2 2 0 002.22 0L21 8m-18 0V18a2 2 0 002 2h14a2 2 0 002-2V8m-18 0l9 6 9-6',
    calendar: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z',
    wand: 'M15 4V2m0 14v-2M8 9h2M20 9h2M17.8 11.8L19 13M15 9h0M17.8 6.2L19 5M3 21l9-9M12.2 6.2L11 5',
    eye: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z',
    browser: 'M3.75 5.25h16.5a1.5 1.5 0 011.5 1.5v10.5a1.5 1.5 0 01-1.5 1.5H3.75a1.5 1.5 0 01-1.5-1.5V6.75a1.5 1.5 0 011.5-1.5z M2.25 8.25h19.5 M5.25 6.75h.01 M7.5 6.75h.01',
    vault: 'M7.5 10.5V8.25a4.5 4.5 0 119 0v2.25 M6.75 10.5h10.5a1.5 1.5 0 011.5 1.5v6.75a1.5 1.5 0 01-1.5 1.5H6.75a1.5 1.5 0 01-1.5-1.5V12a1.5 1.5 0 011.5-1.5z M12 14.25v2.25',
    sparkles: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z',
  }
  const d = paths[icon] || paths.wand
  return (
    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500/20 to-cyan-500/20 border border-teal-500/30 flex items-center justify-center shrink-0">
      <svg className="w-5 h-5 text-teal-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d={d} />
      </svg>
    </div>
  )
}

function StepIndicator({ current }: { current: Step }) {
  const steps: { key: Step; label: string }[] = [
    { key: 'pick', label: 'Pick template' },
    { key: 'params', label: 'Configure' },
    { key: 'preview', label: 'Preview & create' },
  ]
  const currentIdx = steps.findIndex(s => s.key === current)
  return (
    <div className="flex items-center gap-4">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-2">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors
              ${current === s.key
                ? 'bg-cyan-500 text-white'
                : i < currentIdx
                ? 'bg-green-500 text-white'
                : 'bg-slate-700 text-slate-400'}`}
          >
            {i < currentIdx ? '✓' : i + 1}
          </div>
          <span className={`text-sm ${current === s.key ? 'text-white' : 'text-slate-400'}`}>{s.label}</span>
          {i < steps.length - 1 && <div className="w-8 h-px bg-slate-700" />}
        </div>
      ))}
    </div>
  )
}

// ============================================================================
// Dynamic parameter input
// ============================================================================

interface ParamInputProps {
  spec: FlowTemplateParamSpec
  value: any
  onChange: (v: any) => void
  inputId?: string
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  passwordVaultIntegrations: PasswordVaultIntegration[]
}

function ParamInput({ spec, value, onChange, inputId, agents, contacts, personas, customTools, passwordVaultIntegrations }: ParamInputProps) {
  const common = 'w-full px-3 py-2 bg-slate-900/60 border border-slate-700 rounded-lg text-white text-sm focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none'
  const v = value ?? spec.default ?? ''

  switch (spec.type) {
    case 'text':
      return <input id={inputId} type="text" value={v} onChange={e => onChange(e.target.value)} className={common} placeholder={spec.help || ''} />
    case 'textarea':
      return <textarea id={inputId} value={v} onChange={e => onChange(e.target.value)} rows={3} className={common + ' font-mono resize-y'} placeholder={spec.help || ''} />
    case 'number':
      return <input id={inputId} type="number" value={v} onChange={e => onChange(Number(e.target.value) || 0)} min={spec.min ?? undefined} max={spec.max ?? undefined} className={common} />
    case 'time':
      return <input id={inputId} type="time" value={v} onChange={e => onChange(e.target.value)} className={common} />
    case 'toggle':
      return (
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={!!v} onChange={e => onChange(e.target.checked)} className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-teal-500 focus:ring-teal-500" />
          <span className="text-sm text-slate-300">{spec.label}</span>
        </label>
      )
    case 'select':
      return (
        <select id={inputId} value={String(v)} onChange={e => {
          const opt = spec.options?.find(o => String(o.value) === e.target.value)
          onChange(opt ? opt.value : e.target.value)
        }} className={common}>
          {!spec.required && <option value="">— none —</option>}
          {(spec.options || []).map(opt => (
            <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
          ))}
        </select>
      )
    case 'channel':
      return (
        <select id={inputId} value={String(v)} onChange={e => onChange(e.target.value)} className={common}>
          {(spec.options || []).map(opt => (
            <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
          ))}
        </select>
      )
    case 'agent':
      return (
        <select id={inputId} value={String(v)} onChange={e => onChange(Number(e.target.value))} className={common}>
          <option value="">— select an agent —</option>
          {agents.map(a => (
            <option key={a.id} value={String(a.id)}>{a.contact_name || `Agent #${a.id}`}</option>
          ))}
        </select>
      )
    case 'persona':
      return (
        <select id={inputId} value={String(v || '')} onChange={e => onChange(e.target.value ? Number(e.target.value) : null)} className={common}>
          <option value="">— default persona —</option>
          {personas.map(p => (
            <option key={p.id} value={String(p.id)}>{p.name}</option>
          ))}
        </select>
      )
    case 'password_vault_integration':
      return (
        <select id={inputId} value={String(v || '')} onChange={e => onChange(e.target.value ? Number(e.target.value) : null)} className={common}>
          <option value="">— select a Password Vault connection —</option>
          {passwordVaultIntegrations.filter(i => i.is_active).map(i => (
            <option key={i.id} value={String(i.id)}>
              {i.integration_name || i.name || `Password Vault #${i.id}`}
              {i.default_vault_name ? ` · ${i.default_vault_name}` : ''}
            </option>
          ))}
        </select>
      )
    case 'contact':
      return (
        <div className="flex gap-2">
          <input id={inputId} type="text" value={v} onChange={e => onChange(e.target.value)} className={common} placeholder="Phone or @mention" />
          {contacts.length > 0 && (
            <select aria-label="Saved contact picker" value="" onChange={e => e.target.value && onChange(e.target.value)} className={common + ' max-w-xs'}>
              <option value="">— pick contact —</option>
              {contacts.slice(0, 100).map(c => (
                <option key={c.id} value={c.phone_number || c.friendly_name}>{c.friendly_name} ({c.phone_number || 'no phone'})</option>
              ))}
            </select>
          )}
        </div>
      )
    case 'tool':
      return (
        <select id={inputId} value={String(v || '')} onChange={e => onChange(e.target.value)} className={common}>
          <option value="">— select a tool —</option>
          {customTools.filter(t => t.is_enabled).map(t => (
            <option key={t.id} value={t.name}>{t.name}</option>
          ))}
        </select>
      )
    default:
      return <input id={inputId} type="text" value={v} onChange={e => onChange(e.target.value)} className={common} />
  }
}

// ============================================================================
// Main component
// ============================================================================

export default function CreateFromTemplateModal({ agents, contacts, personas, customTools, onClose, onSuccess }: Props) {
  const [step, setStep] = useState<Step>('pick')
  const [templates, setTemplates] = useState<FlowTemplateSummary[]>([])
  const [templateDetailsById, setTemplateDetailsById] = useState<Record<string, FlowTemplateSummary>>({})
  const [passwordVaultIntegrations, setPasswordVaultIntegrations] = useState<PasswordVaultIntegration[]>([])
  const [loadingTemplates, setLoadingTemplates] = useState(true)
  const [selected, setSelected] = useState<FlowTemplateSummary | null>(null)
  const [params, setParams] = useState<Record<string, any>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [showAdvancedParams, setShowAdvancedParams] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.listFlowTemplates()
      .then(ts => { if (!cancelled) { setTemplates(ts); setLoadingTemplates(false) } })
      .catch(err => { if (!cancelled) { setSubmitError(err?.message || 'Failed to load templates'); setLoadingTemplates(false) } })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    api.listPasswordVaultIntegrations()
      .then(rows => { if (!cancelled) setPasswordVaultIntegrations(rows) })
      .catch(() => { if (!cancelled) setPasswordVaultIntegrations([]) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!selected || templateDetailsById[selected.id]) return
    let cancelled = false
    api.getFlowTemplate(selected.id)
      .then(detail => {
        if (!cancelled) {
          setTemplateDetailsById(current => ({ ...current, [selected.id]: detail }))
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTemplateDetailsById(current => ({ ...current, [selected.id]: selected }))
        }
      })
    return () => { cancelled = true }
  }, [selected, templateDetailsById])

  // Initialize params with defaults when a template is picked
  useEffect(() => {
    if (!selected) return
    const init: Record<string, any> = {}
    for (const p of selected.params_schema) {
      if (p.type === 'password_vault_integration' && passwordVaultIntegrations.length === 1) {
        init[p.key] = passwordVaultIntegrations[0].id
      } else if (p.default !== null && p.default !== undefined) {
        init[p.key] = p.default
      }
    }
    setParams(init)
    setShowAdvancedParams(false)
  }, [selected, passwordVaultIntegrations])

  const requiredMissing = useMemo(() => {
    if (!selected) return []
    return selected.params_schema
      .filter(p => p.required)
      .filter(p => {
        const v = params[p.key]
        return v === undefined || v === null || v === ''
      })
      .map(p => p.label)
  }, [selected, params])

  const selectedDetail = selected ? (templateDetailsById[selected.id] || selected) : null
  const previewSteps = selectedDetail?.preview_steps || []
  const usesPasswordVault = Boolean(selected?.params_schema.some(p => p.type === 'password_vault_integration'))
  const paramsForDisplay = selected?.params_schema.filter(spec => (
    !usesPasswordVault || !['password_vault_integration_id', 'vault', 'vault_item_ref'].includes(spec.key)
  )) || []
  const primaryParamsForDisplay = paramsForDisplay.filter(spec => !ADVANCED_TEMPLATE_PARAM_KEYS.has(spec.key))
  const advancedParamsForDisplay = paramsForDisplay.filter(spec => ADVANCED_TEMPLATE_PARAM_KEYS.has(spec.key))
  const wizardVaultValue: PasswordVaultReferenceValue = {
    password_vault_integration_id: params.password_vault_integration_id ?? null,
    password_vault_provider: passwordVaultIntegrations.find(i => i.id === Number(params.password_vault_integration_id))?.provider || null,
    password_vault_vault_id: null,
    password_vault_vault_name: params.vault || null,
    password_vault_item_id: null,
    password_vault_item_title: params.vault_item_ref || null,
    password_vault_field_name: null,
    password_vault_reference: null,
  }

  function updateWizardVaultReference(next: PasswordVaultReferenceValue) {
    setParams(prev => ({
      ...prev,
      password_vault_integration_id: next.password_vault_integration_id ? Number(next.password_vault_integration_id) : null,
      vault: next.password_vault_vault_name || next.password_vault_vault_id || prev.vault || 'FinanApp',
      vault_item_ref: next.password_vault_item_title || next.password_vault_item_id || prev.vault_item_ref || '',
    }))
  }

  async function handleCreate() {
    if (!selected) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      const res = await api.instantiateFlowTemplate(selected.id, params)
      onSuccess(res.flow_id, res.name)
    } catch (err: any) {
      setSubmitError(err?.message || 'Failed to create flow')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl max-w-4xl w-full max-h-[92vh] flex flex-col shadow-2xl border border-slate-700">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Create Flow from Template</h2>
            <p className="text-sm text-slate-400">
              {step === 'pick' && 'Pick a pre-built hybrid automation — programmatic + agentic steps, ready in one click.'}
              {step === 'params' && `Configure "${selected?.name}"`}
              {step === 'preview' && 'Review and create'}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress */}
        <div className="px-6 py-3 bg-slate-900/50 border-b border-slate-700">
          <StepIndicator current={step} />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* STEP 1 — PICK */}
          {step === 'pick' && (
            <div className="space-y-3">
              {loadingTemplates && (
                <div className="text-center py-12 text-slate-400">Loading templates…</div>
              )}
              {!loadingTemplates && submitError && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
                  Failed to load templates: {submitError}
                </div>
              )}
              {!loadingTemplates && !submitError && templates.length === 0 && (
                <div className="text-center py-12 text-slate-400">No templates available.</div>
              )}
              {!loadingTemplates && templates.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {templates.map(t => {
                    const badge = CATEGORY_BADGES[t.category] || CATEGORY_BADGES.on_demand
                    return (
                      <button
                        key={t.id}
                        onClick={() => { setSelected(t); setStep('params') }}
                        className="text-left p-4 rounded-xl bg-slate-900/60 border border-slate-700 hover:border-teal-500/60 hover:bg-slate-900/80 transition-all group"
                      >
                        <div className="flex items-start gap-3">
                          <IconBadge icon={t.icon} />
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-base font-semibold text-white group-hover:text-teal-300 transition-colors">{t.name}</h3>
                              <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border font-medium ${badge.className}`}>{badge.label}</span>
                              {t.highlights && t.highlights.some((h: string) => h.toLowerCase().includes('zero ai cost')) && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                                  Zero AI Cost
                                </span>
                              )}
                            </div>
                            <p className="text-sm text-slate-400 mt-1 leading-relaxed">{t.description}</p>
                            {t.highlights && t.highlights.length > 0 && (
                              <ul className="mt-3 space-y-1">
                                {t.highlights.map((h, i) => (
                                  <li key={i} className="text-xs text-slate-500 flex items-start gap-2">
                                    <span className="text-teal-400 mt-0.5">◆</span>
                                    <span>{h}</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                            {t.required_credentials && t.required_credentials.length > 0 && (
                              <div className="mt-3 text-[11px] text-amber-400/80">
                                Requires: {t.required_credentials.join(', ')}
                              </div>
                            )}
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* STEP 2 — PARAMS */}
          {step === 'params' && selected && (
            <div className="space-y-4 max-w-2xl">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-900/40 border border-slate-700/50">
                <IconBadge icon={selected.icon} />
                <div className="min-w-0">
                  <div className="text-white font-medium">{selected.name}</div>
                  <div className="text-xs text-slate-500">{selected.description}</div>
                </div>
              </div>

              {usesPasswordVault && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">
                    Password Vault item
                    <span className="text-teal-400 ml-1">*</span>
                  </label>
                  <PasswordVaultReferencePicker
                    value={wizardVaultValue}
                    onChange={updateWizardVaultReference}
                    compact
                  />
                </div>
              )}

              {primaryParamsForDisplay.map(spec => (
                <div key={spec.key}>
                  <label htmlFor={`flow-template-param-${spec.key}`} className="block text-sm font-medium text-slate-300 mb-1.5">
                    {spec.label}
                    {spec.required && <span className="text-teal-400 ml-1">*</span>}
                  </label>
                  <ParamInput
                    spec={spec}
                    value={params[spec.key]}
                    onChange={v => setParams(prev => ({ ...prev, [spec.key]: v }))}
                    inputId={`flow-template-param-${spec.key}`}
                    agents={agents}
                    contacts={contacts}
                    personas={personas}
                    customTools={customTools}
                    passwordVaultIntegrations={passwordVaultIntegrations}
                  />
                  {spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
                </div>
              ))}

              {advancedParamsForDisplay.length > 0 && (
                <div className="rounded-lg border border-slate-700/70 bg-slate-900/30">
                  <button
                    type="button"
                    onClick={() => setShowAdvancedParams(value => !value)}
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm text-slate-300 hover:text-white"
                  >
                    <span>Advanced options</span>
                    <span className="text-xs text-slate-500">{showAdvancedParams ? 'Hide' : 'Show'}</span>
                  </button>
                  {showAdvancedParams && (
                    <div className="space-y-4 border-t border-slate-700/70 p-3">
                      {advancedParamsForDisplay.map(spec => (
                        <div key={spec.key}>
                          <label htmlFor={`flow-template-param-${spec.key}`} className="block text-sm font-medium text-slate-300 mb-1.5">
                            {spec.label}
                            {spec.required && <span className="text-teal-400 ml-1">*</span>}
                          </label>
                          <ParamInput
                            spec={spec}
                            value={params[spec.key]}
                            onChange={v => setParams(prev => ({ ...prev, [spec.key]: v }))}
                            inputId={`flow-template-param-${spec.key}`}
                            agents={agents}
                            contacts={contacts}
                            personas={personas}
                            customTools={customTools}
                            passwordVaultIntegrations={passwordVaultIntegrations}
                          />
                          {spec.help && <p className="mt-1 text-xs text-slate-500">{spec.help}</p>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* STEP 3 — PREVIEW */}
          {step === 'preview' && selected && (
            <div className="space-y-4 max-w-2xl">
              <div className="p-4 rounded-lg bg-slate-900/40 border border-slate-700/50">
                <div className="flex items-center gap-3">
                  <IconBadge icon={selected.icon} />
                  <div className="min-w-0">
                    <div className="text-white font-semibold">{params.name || selected.name}</div>
                    <div className="text-xs text-slate-500">Template: {selected.name}</div>
                  </div>
                </div>
              </div>

              {previewSteps.length > 0 && (
                <div>
                  <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Visible step graph</h4>
                  <div className="rounded-lg bg-slate-900/40 border border-slate-700/50 divide-y divide-slate-800">
                    {previewSteps.map(previewStep => (
                      <div key={`${previewStep.position}-${previewStep.name}`} className="grid grid-cols-[3rem_1fr_10rem] gap-3 px-3 py-2 text-sm">
                        <span className="font-mono text-slate-500">#{previewStep.position}</span>
                        <span className="min-w-0 break-words text-slate-200">{previewStep.name}</span>
                        <span className="min-w-0 break-words text-right font-mono text-xs text-teal-300">{previewStep.type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h4 className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-2">Configuration</h4>
                <div className="rounded-lg bg-slate-900/40 border border-slate-700/50 divide-y divide-slate-800">
                  {selected.params_schema.map(spec => {
                    const v = params[spec.key]
                    if (v === undefined || v === null || v === '') return null
                    let display = String(v)
                    if (spec.type === 'select' || spec.type === 'channel') {
                      const opt = spec.options?.find(o => String(o.value) === String(v))
                      if (opt) display = opt.label
                    }
                    if (spec.type === 'agent') {
                      const a = agents.find(a => a.id === Number(v))
                      if (a) display = a.contact_name || `Agent #${a.id}`
                    }
                    if (spec.type === 'persona' && v) {
                      const p = personas.find(p => p.id === Number(v))
                      if (p) display = p.name
                    }
                    if (spec.type === 'password_vault_integration' && v) {
                      const integration = passwordVaultIntegrations.find(i => i.id === Number(v))
                      if (integration) {
                        display = integration.integration_name || integration.name || `Password Vault #${integration.id}`
                      }
                    }
                    return (
                      <div key={spec.key} className="px-3 py-2 flex items-start justify-between gap-4 text-sm">
                        <span className="text-slate-400 min-w-0">{spec.label}</span>
                        <span className="text-slate-200 text-right break-words min-w-0">{display}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-teal-500/5 border border-teal-500/20 text-xs text-teal-300/90">
                <strong className="text-teal-300">What happens on Create:</strong> the flow is saved with its steps wired up.
                {selected.required_credentials.length > 0 && (
                  <span className="block mt-1 text-amber-300/80">
                    Make sure the following credentials are configured in Hub → Integrations: <strong>{selected.required_credentials.join(', ')}</strong>
                  </span>
                )}
              </div>

              {submitError && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">{submitError}</div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 flex items-center justify-between bg-slate-900/30">
          <button
            onClick={() => {
              if (step === 'pick') onClose()
              else if (step === 'params') setStep('pick')
              else setStep('params')
            }}
            className="px-4 py-2 text-sm text-slate-300 hover:text-white transition-colors"
          >
            {step === 'pick' ? 'Cancel' : '← Back'}
          </button>
          <div className="flex items-center gap-3">
            {step === 'params' && (
              <>
                {requiredMissing.length > 0 && (
                  <span className="text-xs text-amber-400">Missing: {requiredMissing.join(', ')}</span>
                )}
                <button
                  onClick={() => setStep('preview')}
                  disabled={requiredMissing.length > 0}
                  className="px-5 py-2 bg-gradient-to-r from-teal-500 to-cyan-500 text-white text-sm font-medium rounded-lg hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Preview →
                </button>
              </>
            )}
            {step === 'preview' && (
              <button
                onClick={handleCreate}
                disabled={submitting}
                className="px-5 py-2 bg-gradient-to-r from-teal-500 to-cyan-500 text-white text-sm font-medium rounded-lg hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/20 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? 'Creating…' : 'Create Flow'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
