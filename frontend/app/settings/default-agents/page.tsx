'use client'

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'
import {
  api,
  DefaultAgentInstanceBinding,
  DefaultAgentsSettings,
  UserChannelDefaultAgent,
} from '@/lib/client'

const CHANNEL_LABELS: Record<string, string> = {
  whatsapp: 'WhatsApp',
  telegram: 'Telegram',
  slack: 'Slack',
  discord: 'Discord',
  email: 'Email',
  webhook: 'Webhook',
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20',
  paused: 'bg-amber-500/10 text-amber-300 border border-amber-500/20',
  connected: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20',
  disconnected: 'bg-red-500/10 text-red-300 border border-red-500/20',
}

const HEALTH_STYLES: Record<string, string> = {
  healthy: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20',
  degraded: 'bg-amber-500/10 text-amber-300 border border-amber-500/20',
  unavailable: 'bg-red-500/10 text-red-300 border border-red-500/20',
  unknown: 'bg-white/5 text-tsushin-slate border border-white/10',
}

const USER_DEFAULT_CHANNELS = ['whatsapp', 'telegram', 'slack', 'discord'] as const

type UserDefaultFormState = {
  channel_type: string
  user_identifier: string
  agent_id: string
}

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

const toSelectValue = (agentId?: number | null) => (agentId == null ? '' : String(agentId))

const fromSelectValue = (value: string): number | null => {
  if (!value) return null
  const parsed = Number.parseInt(value, 10)
  return Number.isNaN(parsed) ? null : parsed
}

const getInstanceKey = (binding: Pick<DefaultAgentInstanceBinding, 'channel_type' | 'instance_id'>) =>
  `${binding.channel_type}:${binding.instance_id}`

const getChannelLabel = (channelType: string) => CHANNEL_LABELS[channelType] || channelType

const buildInitialUserForm = (
  settings: DefaultAgentsSettings | null,
  previous?: UserDefaultFormState,
): UserDefaultFormState => {
  const firstAgentId = settings?.available_agents[0]?.id
  const preservedAgentId =
    previous?.agent_id &&
    settings?.available_agents.some((agent) => String(agent.id) === previous.agent_id)
      ? previous.agent_id
      : undefined

  return {
    channel_type: previous?.channel_type || USER_DEFAULT_CHANNELS[0],
    user_identifier: previous?.user_identifier || '',
    agent_id: preservedAgentId || toSelectValue(firstAgentId ?? null),
  }
}

export default function DefaultAgentsSettingsPage() {
  const { loading: authLoading, hasPermission } = useRequireAuth()
  const canRead = hasPermission('org.settings.read')
  const canEdit = hasPermission('org.settings.write')

  const [settings, setSettings] = useState<DefaultAgentsSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [tenantDraft, setTenantDraft] = useState('')
  const [instanceDrafts, setInstanceDrafts] = useState<Record<string, string>>({})
  const [userDrafts, setUserDrafts] = useState<Record<number, string>>({})
  const [newUserDefault, setNewUserDefault] = useState<UserDefaultFormState>(
    buildInitialUserForm(null),
  )
  const [tenantSaving, setTenantSaving] = useState(false)
  const [savingInstanceKey, setSavingInstanceKey] = useState<string | null>(null)
  const [savingUserId, setSavingUserId] = useState<number | 'new' | null>(null)

  const availableAgents = settings?.available_agents || []
  const hasAgents = availableAgents.length > 0

  const syncDrafts = useCallback((data: DefaultAgentsSettings) => {
    setTenantDraft(toSelectValue(data.tenant_default_agent_id))

    const nextInstanceDrafts: Record<string, string> = {}
    ;[...data.channel_defaults, ...data.trigger_defaults].forEach((binding) => {
      nextInstanceDrafts[getInstanceKey(binding)] = toSelectValue(binding.default_agent_id)
    })
    setInstanceDrafts(nextInstanceDrafts)

    const nextUserDrafts: Record<number, string> = {}
    data.user_defaults.forEach((entry) => {
      nextUserDrafts[entry.id] = String(entry.agent_id)
    })
    setUserDrafts(nextUserDrafts)
    setNewUserDefault((previous) => buildInitialUserForm(data, previous))
  }, [])

  const loadSettings = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.getDefaultAgentSettings()
      setSettings(data)
      syncDrafts(data)
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to load default-agent settings'))
    } finally {
      setLoading(false)
    }
  }, [syncDrafts])

  useEffect(() => {
    if (authLoading || !canRead) return
    void loadSettings()
  }, [authLoading, canRead, loadSettings])

  const handleTenantSave = async () => {
    setTenantSaving(true)
    setError('')
    setSuccess('')
    try {
      await api.updateTenantDefaultAgent(fromSelectValue(tenantDraft))
      await loadSettings()
      setSuccess('Tenant default agent updated.')
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to update tenant default agent'))
    } finally {
      setTenantSaving(false)
    }
  }

  const handleInstanceSave = async (binding: DefaultAgentInstanceBinding) => {
    const key = getInstanceKey(binding)
    setSavingInstanceKey(key)
    setError('')
    setSuccess('')
    try {
      await api.updateInstanceDefaultAgent(
        binding.channel_type,
        binding.instance_id,
        fromSelectValue(instanceDrafts[key] || ''),
      )
      await loadSettings()
      setSuccess(`${binding.display_name} updated.`)
    } catch (error: unknown) {
      setError(getErrorMessage(error, `Failed to update ${binding.display_name}`))
    } finally {
      setSavingInstanceKey(null)
    }
  }

  const handleExistingUserSave = async (entry: UserChannelDefaultAgent) => {
    setSavingUserId(entry.id)
    setError('')
    setSuccess('')
    try {
      await api.upsertUserChannelDefaultAgent({
        channel_type: entry.channel_type,
        user_identifier: entry.user_identifier,
        agent_id: fromSelectValue(userDrafts[entry.id] || '') || entry.agent_id,
      })
      await loadSettings()
      setSuccess(`User default for ${entry.user_identifier} updated.`)
    } catch (error: unknown) {
      setError(getErrorMessage(error, `Failed to update ${entry.user_identifier}`))
    } finally {
      setSavingUserId(null)
    }
  }

  const handleDeleteUserDefault = async (entry: UserChannelDefaultAgent) => {
    if (!window.confirm(`Remove the default-agent override for ${entry.user_identifier}?`)) return
    setSavingUserId(entry.id)
    setError('')
    setSuccess('')
    try {
      await api.deleteUserChannelDefaultAgent(entry.id)
      await loadSettings()
      setSuccess(`User default for ${entry.user_identifier} removed.`)
    } catch (error: unknown) {
      setError(getErrorMessage(error, `Failed to remove ${entry.user_identifier}`))
    } finally {
      setSavingUserId(null)
    }
  }

  const handleAddUserDefault = async () => {
    const userIdentifier = newUserDefault.user_identifier.trim()
    const agentId = fromSelectValue(newUserDefault.agent_id)

    if (!userIdentifier) {
      setError('Enter a user identifier before saving.')
      return
    }

    if (!agentId) {
      setError('Select an agent before saving.')
      return
    }

    setSavingUserId('new')
    setError('')
    setSuccess('')
    try {
      await api.upsertUserChannelDefaultAgent({
        channel_type: newUserDefault.channel_type,
        user_identifier: userIdentifier,
        agent_id: agentId,
      })
      await loadSettings()
      setSuccess(`User default for ${userIdentifier} saved.`)
      setNewUserDefault(buildInitialUserForm(settings))
    } catch (error: unknown) {
      setError(getErrorMessage(error, 'Failed to save user default'))
    } finally {
      setSavingUserId(null)
    }
  }

  const renderStatusBadge = (label: string | null | undefined, styles: Record<string, string>) => {
    if (!label) return null
    const key = label.toLowerCase()
    return (
      <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium capitalize ${styles[key] || 'bg-white/5 text-tsushin-slate border border-white/10'}`}>
        {label}
      </span>
    )
  }

  const renderInstanceSection = (
    title: string,
    description: string,
    emptyState: ReactNode,
    bindings: DefaultAgentInstanceBinding[],
  ) => (
    <section className="glass-card rounded-xl p-6">
      <div className="mb-5">
        <h2 className="text-xl font-semibold text-white">{title}</h2>
        <p className="mt-1 text-sm text-tsushin-slate">{description}</p>
      </div>

      {bindings.length === 0 ? (
        emptyState
      ) : (
        <div className="space-y-4">
          {bindings.map((binding) => {
            const key = getInstanceKey(binding)
            const draftValue = instanceDrafts[key] ?? toSelectValue(binding.default_agent_id)
            const hasChanges = fromSelectValue(draftValue) !== (binding.default_agent_id ?? null)
            return (
              <div
                key={key}
                className="rounded-xl border border-white/5 bg-black/10 p-4"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-semibold text-white">{binding.display_name}</h3>
                      <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-tsushin-slate">
                        {getChannelLabel(binding.channel_type)}
                      </span>
                      {renderStatusBadge(binding.status, STATUS_STYLES)}
                      {renderStatusBadge(binding.health_status, HEALTH_STYLES)}
                    </div>
                    <p className="mt-2 text-sm text-tsushin-slate">
                      Current default:{' '}
                      <span className="text-white">
                        {binding.default_agent_name || 'Falls back to the tenant default'}
                      </span>
                    </p>
                  </div>

                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <select
                      value={draftValue}
                      onChange={(event) =>
                        setInstanceDrafts((current) => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                      disabled={!canEdit || !hasAgents}
                      className="select min-w-[220px]"
                    >
                      <option value="">Use tenant default</option>
                      {availableAgents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name}
                        </option>
                      ))}
                    </select>
                    {canEdit && (
                      <button
                        type="button"
                        onClick={() => handleInstanceSave(binding)}
                        disabled={!hasAgents || !hasChanges || savingInstanceKey === key}
                        className="btn-primary whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {savingInstanceKey === key ? 'Saving...' : 'Save'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )

  if (authLoading || (canRead && loading)) {
    return (
      <div className="min-h-screen bg-[#07070d] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-teal-400" />
      </div>
    )
  }

  if (!canRead) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="glass-card rounded-xl p-8 text-center">
          <h2 className="text-xl font-semibold text-white mb-2">Access Denied</h2>
          <p className="text-tsushin-slate">
            You don&apos;t have permission to view default-agent settings.
          </p>
        </div>
      </div>
    )
  }

  const tenantHasChanges = fromSelectValue(tenantDraft) !== (settings?.tenant_default_agent_id ?? null)

  return (
    <div className="min-h-screen bg-[#07070d] text-white">
      <div className="container mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <Link href="/settings" className="text-sm text-tsushin-slate hover:text-teal-400 transition-colors">
          &larr; Back to Settings
        </Link>

        <div className="mt-6 mb-8 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-sm text-tsushin-slate mb-2">
              <span>Organization Settings</span>
              <span>/</span>
              <span className="text-white">Default Agents</span>
            </div>
            <h1 className="text-3xl font-display font-bold text-white">Default Agents</h1>
            <p className="mt-2 max-w-3xl text-tsushin-slate">
              Define the fallback agent at the tenant, channel, trigger, and per-user levels.
              Contact-specific assignments still live in Studio.
            </p>
          </div>
          {!canEdit && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 md:max-w-sm">
              You have view-only access here. Changes require <code className="rounded bg-black/20 px-1 py-0.5">org.settings.write</code>.
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            {success}
          </div>
        )}

        {!hasAgents && (
          <div className="mb-6 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-tsushin-slate">
            No active agents are available for assignment yet. Create an agent in{' '}
            <Link href="/agents" className="text-teal-400 hover:underline">
              Agent Studio
            </Link>{' '}
            before saving new defaults.
          </div>
        )}

        <div className="space-y-6">
          <section className="glass-card rounded-xl p-6">
            <div className="mb-5">
              <h2 className="text-xl font-semibold text-white">Tenant Default</h2>
              <p className="mt-1 text-sm text-tsushin-slate">
                This is the last-resort fallback when no contact, user, channel, or trigger override matches.
              </p>
            </div>

            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
              <div>
                <label className="block text-sm font-medium text-white mb-2">Default fallback agent</label>
                <select
                  value={tenantDraft}
                  onChange={(event) => setTenantDraft(event.target.value)}
                  disabled={!canEdit || !hasAgents}
                  className="select w-full"
                >
                  <option value="">No tenant default</option>
                  {availableAgents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </select>
                <p className="mt-2 text-sm text-tsushin-slate">
                  Current fallback:{' '}
                  <span className="text-white">
                    {settings?.tenant_default_agent_name || 'No tenant default configured'}
                  </span>
                </p>
              </div>

              {canEdit && (
                <button
                  type="button"
                  onClick={handleTenantSave}
                  disabled={!hasAgents || !tenantHasChanges || tenantSaving}
                  className="btn-primary whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {tenantSaving ? 'Saving...' : 'Save Tenant Default'}
                </button>
              )}
            </div>
          </section>

          {renderInstanceSection(
            'Channel Defaults',
            'Channel-instance defaults apply when a message arrives through a configured communication channel and nothing more specific matches first.',
            <div className="rounded-xl border border-white/5 bg-black/10 px-4 py-5 text-sm text-tsushin-slate">
              No channel instances are configured yet. Set them up in{' '}
              <Link href="/hub?tab=communication" className="text-teal-400 hover:underline">
                Hub &gt; Communication
              </Link>.
            </div>,
            settings?.channel_defaults || [],
          )}

          {renderInstanceSection(
            'Trigger Defaults',
            'Trigger defaults let each inbound trigger route to its own fallback agent before the tenant-wide default is used.',
            <div className="rounded-xl border border-white/5 bg-black/10 px-4 py-5 text-sm text-tsushin-slate">
              No trigger instances are configured yet. Create them in{' '}
              <Link href="/hub?tab=communication" className="text-teal-400 hover:underline">
                Hub &gt; Communication
              </Link>.
            </div>,
            settings?.trigger_defaults || [],
          )}

          <section className="glass-card rounded-xl p-6">
            <div className="mb-5">
              <h2 className="text-xl font-semibold text-white">User Defaults</h2>
              <p className="mt-1 text-sm text-tsushin-slate">
                Route a known channel identifier to a preferred agent without creating a contact-level mapping.
              </p>
            </div>

            <div className="mb-5 rounded-xl border border-white/5 bg-black/10 px-4 py-4 text-sm text-tsushin-slate">
              Contact-specific routing still lives in{' '}
              <Link href="/agents/contacts" className="text-teal-400 hover:underline">
                Studio / Contacts
              </Link>{' '}
              and takes precedence over the user defaults defined here.
            </div>

            {settings?.user_defaults.length ? (
              <div className="space-y-4">
                {settings.user_defaults.map((entry) => {
                  const draftValue = userDrafts[entry.id] || String(entry.agent_id)
                  const hasChanges = fromSelectValue(draftValue) !== entry.agent_id
                  return (
                    <div
                      key={entry.id}
                      className="rounded-xl border border-white/5 bg-black/10 p-4"
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-base font-semibold text-white">{entry.user_identifier}</h3>
                            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-tsushin-slate">
                              {getChannelLabel(entry.channel_type)}
                            </span>
                          </div>
                          <p className="mt-2 text-sm text-tsushin-slate">
                            Current agent:{' '}
                            <span className="text-white">{entry.agent_name || `Agent #${entry.agent_id}`}</span>
                          </p>
                        </div>

                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                          <select
                            value={draftValue}
                            onChange={(event) =>
                              setUserDrafts((current) => ({
                                ...current,
                                [entry.id]: event.target.value,
                              }))
                            }
                            disabled={!canEdit || !hasAgents}
                            className="select min-w-[220px]"
                          >
                            {availableAgents.map((agent) => (
                              <option key={agent.id} value={agent.id}>
                                {agent.name}
                              </option>
                            ))}
                          </select>
                          {canEdit && (
                            <>
                              <button
                                type="button"
                                onClick={() => handleExistingUserSave(entry)}
                                disabled={!hasAgents || !hasChanges || savingUserId === entry.id}
                                className="btn-primary whitespace-nowrap disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {savingUserId === entry.id ? 'Saving...' : 'Save'}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDeleteUserDefault(entry)}
                                disabled={savingUserId === entry.id}
                                className="btn-ghost whitespace-nowrap border border-red-500/20 text-red-300 hover:bg-red-500/10"
                              >
                                Remove
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div className="rounded-xl border border-white/5 bg-black/10 px-4 py-5 text-sm text-tsushin-slate">
                No user-specific default agents are configured yet.
              </div>
            )}

            {canEdit && (
              <div className="mt-6 border-t border-white/5 pt-6">
                <h3 className="text-lg font-semibold text-white">Add User Default</h3>
                <p className="mt-1 text-sm text-tsushin-slate">
                  Use the channel-native identifier for the person you want to route.
                </p>

                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Channel</label>
                    <select
                      value={newUserDefault.channel_type}
                      onChange={(event) =>
                        setNewUserDefault((current) => ({
                          ...current,
                          channel_type: event.target.value,
                        }))
                      }
                      className="select w-full"
                    >
                      {USER_DEFAULT_CHANNELS.map((channelType) => (
                        <option key={channelType} value={channelType}>
                          {getChannelLabel(channelType)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">User identifier</label>
                    <input
                      type="text"
                      value={newUserDefault.user_identifier}
                      onChange={(event) =>
                        setNewUserDefault((current) => ({
                          ...current,
                          user_identifier: event.target.value,
                        }))
                      }
                      className="input w-full"
                      placeholder="e.g. +5511999999999 or U12345678"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-white mb-2">Agent</label>
                    <select
                      value={newUserDefault.agent_id}
                      onChange={(event) =>
                        setNewUserDefault((current) => ({
                          ...current,
                          agent_id: event.target.value,
                        }))
                      }
                      disabled={!hasAgents}
                      className="select w-full"
                    >
                      <option value="">Select an agent</option>
                      {availableAgents.map((agent) => (
                        <option key={agent.id} value={agent.id}>
                          {agent.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                  <button
                    type="button"
                    onClick={handleAddUserDefault}
                    disabled={!hasAgents || savingUserId === 'new'}
                    className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {savingUserId === 'new' ? 'Saving...' : 'Save User Default'}
                  </button>
                  <p className="text-xs text-tsushin-slate">
                    These rules are separate from contact mappings and are best for raw channel identifiers before a contact record exists.
                  </p>
                </div>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-white/5 bg-white/[0.02] p-5">
            <h3 className="text-sm font-semibold text-gray-300 mb-2">Routing order</h3>
            <div className="space-y-2 text-xs text-gray-500">
              <p>
                Channels: explicit routing chosen by the caller, then Studio / Contacts mappings, then user defaults,
                then the channel default, then any legacy bound agent, then the tenant default.
              </p>
              <p>
                Triggers: explicit routing chosen by the caller, then the trigger default, then any legacy bound
                agent, then the tenant default.
              </p>
              <p>
                If no active agent resolves for a trigger, it fails closed instead of silently enqueueing work.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
