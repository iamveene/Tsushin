'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { CustomSkill, SkillDefinition, SkillProviderIntegration } from '@/lib/client'
import { BUILT_IN_SKILLS } from '../defaults'
import { SKILL_DISPLAY_INFO, HIDDEN_SKILLS } from '@/components/skills/skill-constants'

// Shape rendered by the wizard — merges backend catalog (skill_type/applies_to/
// auto_enabled_for/wizard_visible/descriptions) with optional frontend decoration
// (display label overrides from skill-constants, or static fallback in BUILT_IN_SKILLS).
interface WizardSkillRow {
  type: string
  label: string
  description: string
  appliesTo: string[]
  autoEnabledFor: string[]
}

const PASSWORD_VAULT_CAPABILITY_ROWS = [
  { key: 'list_items', label: 'List metadata', defaultEnabled: true },
  { key: 'read_item', label: 'Resolve fields', defaultEnabled: true },
  { key: 'compose_basic_auth', label: 'Compose Basic Auth', defaultEnabled: true },
  { key: 'read_totp', label: 'Resolve TOTP', defaultEnabled: false },
  { key: 'test_connection', label: 'Test connection', defaultEnabled: true },
]

function buildPasswordVaultCapabilities(
  current?: Record<string, any>,
  integration?: SkillProviderIntegration | null,
) {
  const existing = (current?.capabilities || {}) as Record<string, { enabled?: boolean }>
  return Object.fromEntries(
    PASSWORD_VAULT_CAPABILITY_ROWS.map((capability) => {
      let defaultEnabled = capability.defaultEnabled
      if (capability.key === 'read_item' || capability.key === 'compose_basic_auth') {
        defaultEnabled = integration?.allow_secret_read ?? capability.defaultEnabled
      }
      if (capability.key === 'read_totp') {
        defaultEnabled = integration?.allow_totp_read ?? capability.defaultEnabled
      }
      if (capability.key === 'list_items') {
        defaultEnabled = integration?.allow_metadata_read ?? capability.defaultEnabled
      }
      return [
        capability.key,
        {
          enabled: typeof existing[capability.key]?.enabled === 'boolean'
            ? existing[capability.key]?.enabled
            : defaultEnabled,
          label: capability.label,
        },
      ]
    }),
  )
}

// Derive the wizard's skill catalog from the backend's /api/skills/available
// response. This is the single source of truth; the static BUILT_IN_SKILLS list
// is retained ONLY as a fallback when the API is unreachable, and is cross-checked
// against the backend registry by a CI test in backend/tests/test_wizard_drift.py.
function rowsFromBackend(skills: SkillDefinition[]): WizardSkillRow[] {
  return skills
    .filter(s => s.wizard_visible !== false)
    .filter(s => !HIDDEN_SKILLS.has(s.skill_type))
    .map(s => {
      const display = SKILL_DISPLAY_INFO[s.skill_type]
      return {
        type: s.skill_type,
        label: display?.displayName || s.skill_name,
        description: display?.description || s.skill_description,
        appliesTo: s.applies_to || ['text', 'audio', 'hybrid'],
        autoEnabledFor: s.auto_enabled_for || [],
      }
    })
}

function rowsFromFallback(): WizardSkillRow[] {
  return BUILT_IN_SKILLS.map(s => ({
    type: s.type,
    label: s.label,
    description: s.description,
    appliesTo: s.appliesTo,
    autoEnabledFor: s.autoEnabledFor || [],
  }))
}

export default function StepSkills() {
  const { state, patchSkills, markStepComplete } = useAgentWizard()
  const [customSkills, setCustomSkills] = useState<CustomSkill[]>([])
  const [catalog, setCatalog] = useState<WizardSkillRow[]>(() => rowsFromFallback())
  const [passwordVaultIntegrations, setPasswordVaultIntegrations] = useState<SkillProviderIntegration[]>([])
  const [passwordVaultLoading, setPasswordVaultLoading] = useState(false)

  useEffect(() => {
    api.getCustomSkills().then(setCustomSkills).catch(() => setCustomSkills([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    setPasswordVaultLoading(true)
    api.getSkillProviders('password_vault')
      .then((providers) => {
        if (cancelled) return
        const provider = providers.find(p => p.provider_type === 'onepassword') || providers[0]
        setPasswordVaultIntegrations(provider?.available_integrations || [])
      })
      .catch(() => {
        if (!cancelled) setPasswordVaultIntegrations([])
      })
      .finally(() => {
        if (!cancelled) setPasswordVaultLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    api.getAvailableSkills()
      .then(skills => {
        if (cancelled) return
        const rows = rowsFromBackend(skills)
        // If the backend returned an empty/degraded list, keep the fallback.
        if (rows.length > 0) setCatalog(rows)
      })
      .catch(() => {
        // Network or auth failure — keep the fallback rows already in state.
      })
    return () => { cancelled = true }
  }, [])

  const agentType = state.draft.type
  const available = useMemo(() => {
    if (!agentType) return []
    return catalog.filter(s => s.appliesTo.includes(agentType))
  }, [agentType, catalog])

  // Auto-enable skills that are locked for audio/hybrid
  useEffect(() => {
    if (!agentType) return
    const next = { ...state.draft.skills.builtIns }
    let changed = false
    for (const s of catalog) {
      if (s.autoEnabledFor.includes(agentType) && !next[s.type]?.is_enabled) {
        next[s.type] = { is_enabled: true, config: next[s.type]?.config || {} }
        changed = true
      }
    }
    if (changed) patchSkills({ builtIns: next })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentType, catalog])

  const passwordVaultSkill = state.draft.skills.builtIns.password_vault
  const passwordVaultEnabled = passwordVaultSkill?.is_enabled ?? false
  const selectedPasswordVaultIntegrationId = Number(passwordVaultSkill?.config?.integration_id || 0) || null
  const passwordVaultNeedsConnection =
    passwordVaultEnabled && !passwordVaultLoading && passwordVaultIntegrations.length === 0
  const passwordVaultNeedsSelection =
    passwordVaultEnabled && !passwordVaultLoading && passwordVaultIntegrations.length > 0 && !selectedPasswordVaultIntegrationId

  useEffect(() => {
    markStepComplete('skills', !(passwordVaultNeedsConnection || passwordVaultNeedsSelection))
  }, [markStepComplete, passwordVaultNeedsConnection, passwordVaultNeedsSelection])

  function buildPasswordVaultConfig(
    current: Record<string, any> | undefined,
    integration?: SkillProviderIntegration | null,
  ) {
    return {
      ...(current || {}),
      execution_mode: 'tool',
      provider: integration?.provider || 'onepassword',
      integration_id: integration?.integration_id ?? current?.integration_id ?? null,
      reference_mode: 'vault_reference',
      capabilities: buildPasswordVaultCapabilities(current, integration),
    }
  }

  function patchPasswordVaultConfig(patch: Record<string, any>) {
    const current = state.draft.skills.builtIns.password_vault
    patchSkills({
      builtIns: {
        ...state.draft.skills.builtIns,
        password_vault: {
          is_enabled: true,
          config: {
            ...(current?.config || {}),
            ...patch,
          },
        },
      },
    })
  }

  function selectPasswordVaultIntegration(integrationId: number | null) {
    const integration = passwordVaultIntegrations.find(item => item.integration_id === integrationId) || null
    patchPasswordVaultConfig(buildPasswordVaultConfig(passwordVaultSkill?.config, integration))
  }

  function togglePasswordVaultCapability(capabilityKey: string, enabled: boolean) {
    const currentConfig = passwordVaultSkill?.config || {}
    const currentCapabilities = (currentConfig.capabilities || buildPasswordVaultCapabilities(currentConfig)) as Record<string, any>
    patchPasswordVaultConfig({
      capabilities: {
        ...currentCapabilities,
        [capabilityKey]: {
          ...(currentCapabilities[capabilityKey] || {}),
          enabled,
        },
      },
    })
  }

  useEffect(() => {
    if (!passwordVaultEnabled || passwordVaultLoading || selectedPasswordVaultIntegrationId) return
    if (passwordVaultIntegrations.length !== 1) return
    selectPasswordVaultIntegration(passwordVaultIntegrations[0].integration_id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passwordVaultEnabled, passwordVaultLoading, passwordVaultIntegrations.length, selectedPasswordVaultIntegrationId])

  const isLocked = (skillType: string) => {
    const def = catalog.find(s => s.type === skillType)
    return !!def?.autoEnabledFor.includes(agentType!)
  }

  const toggleBuiltin = (skillType: string) => {
    if (isLocked(skillType)) return
    const current = state.draft.skills.builtIns[skillType]
    const nextEnabled = !(current?.is_enabled ?? false)
    const selectedVault = passwordVaultIntegrations.find(item => item.integration_id === selectedPasswordVaultIntegrationId)
      || passwordVaultIntegrations[0]
      || null
    patchSkills({
      builtIns: {
        ...state.draft.skills.builtIns,
        [skillType]: {
          is_enabled: nextEnabled,
          config: skillType === 'password_vault' && nextEnabled
            ? buildPasswordVaultConfig(current?.config, selectedVault)
            : (current?.config || {}),
        },
      },
    })
  }

  const toggleCustom = (id: number) => {
    const ids = new Set(state.draft.skills.customIds)
    if (ids.has(id)) ids.delete(id)
    else ids.add(id)
    patchSkills({ customIds: Array.from(ids) })
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Pick the skills it can use</h3>
        <p className="text-sm text-gray-300">You can always change these later from the agent's page.</p>
      </div>

      <div className="space-y-2">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Built-in</div>
        {available.map(s => {
          const enabled = state.draft.skills.builtIns[s.type]?.is_enabled ?? false
          const locked = isLocked(s.type)
          return (
            <div
              key={s.type}
              className={`flex items-start gap-3 p-3 rounded-xl border transition-colors ${
                enabled ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              } ${locked ? 'opacity-80' : ''}`}
            >
              <input
                type="checkbox"
                aria-label={`Enable ${s.label}`}
                checked={enabled}
                disabled={locked}
                onChange={() => toggleBuiltin(s.type)}
                className="mt-0.5"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="text-white text-sm font-medium">{s.label}</div>
                  {locked && <span className="px-2 py-0.5 text-xs rounded-full bg-white/10 text-gray-300">Required for this type</span>}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">{s.description}</div>
                {s.type === 'password_vault' && enabled && (
                  <div className="mt-3 space-y-3 rounded-lg border border-white/10 bg-black/20 p-3">
                    {passwordVaultLoading ? (
                      <div className="text-xs text-gray-400">Loading 1Password connections...</div>
                    ) : passwordVaultIntegrations.length === 0 ? (
                      <div className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-100">
                        Create a Password Vault provider first in <a href="/hub?tab=tool-apis" className="font-medium underline decoration-dotted underline-offset-2">Hub Tool APIs</a>, then return here and select it.
                      </div>
                    ) : (
                      <>
                        <div>
                          <label className="mb-1 block text-xs font-medium text-gray-300">1Password connection</label>
                          <select
                            value={selectedPasswordVaultIntegrationId || ''}
                            onChange={(event) => selectPasswordVaultIntegration(event.target.value ? Number(event.target.value) : null)}
                            className="w-full rounded-lg border border-white/10 bg-gray-950 px-3 py-2 text-xs text-white"
                          >
                            <option value="">Select a connection...</option>
                            {passwordVaultIntegrations.map((integration) => (
                              <option key={integration.integration_id} value={integration.integration_id}>
                                {integration.name}{integration.default_vault ? ` · ${integration.default_vault}` : ''}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {PASSWORD_VAULT_CAPABILITY_ROWS.map((capability) => {
                            const capabilityConfig = (passwordVaultSkill?.config?.capabilities || {})[capability.key]
                            const checked = typeof capabilityConfig?.enabled === 'boolean'
                              ? capabilityConfig.enabled
                              : capability.defaultEnabled
                            return (
                              <label key={capability.key} className="flex items-center gap-2 text-xs text-gray-300">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(event) => togglePasswordVaultCapability(capability.key, event.target.checked)}
                                />
                                <span>{capability.label}</span>
                              </label>
                            )
                          })}
                        </div>
                        <div className="text-[11px] text-gray-500">
                          Secret values stay outside prompts; the agent receives redacted outputs or short-lived handles.
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {customSkills.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Custom</div>
          {customSkills.map(cs => {
            const selected = state.draft.skills.customIds.includes(cs.id)
            return (
              <label
                key={cs.id}
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  selected ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                }`}
              >
                <input type="checkbox" checked={selected} onChange={() => toggleCustom(cs.id)} className="mt-0.5" />
                <div className="flex-1">
                  <div className="text-white text-sm font-medium">{cs.name}</div>
                  {cs.description && <div className="text-xs text-gray-400 mt-0.5">{cs.description}</div>}
                </div>
              </label>
            )
          })}
        </div>
      )}

      <div className="text-xs text-gray-500">
        Selecting zero skills is fine — you can add them later.
      </div>
    </div>
  )
}
