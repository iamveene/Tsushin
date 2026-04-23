'use client'

import { useCallback, useMemo, useState } from 'react'
import {
  api,
  type Agent,
  type ChannelRoutingRule,
  type ChannelRoutingRuleCreate,
  type ConversationalChannelType,
} from '@/lib/client'
import { EditIcon, PlusIcon, RefreshIcon, TrashIcon, ZapIcon } from '@/components/ui/icons'

interface ChannelRoutingRulesPanelProps {
  channelType: ConversationalChannelType
  instanceId: number
  canWrite: boolean
}

interface RuleFormState {
  id: number | null
  eventType: string
  criteriaText: string
  priority: string
  agentId: string
  isActive: boolean
}

const EMPTY_FORM: RuleFormState = {
  id: null,
  eventType: '',
  criteriaText: '{}',
  priority: '100',
  agentId: '',
  isActive: true,
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function channelLabel(channelType: ConversationalChannelType): string {
  return channelType.charAt(0).toUpperCase() + channelType.slice(1)
}

function ruleToForm(rule: ChannelRoutingRule): RuleFormState {
  return {
    id: rule.id,
    eventType: rule.event_type || '',
    criteriaText: JSON.stringify(rule.criteria || {}, null, 2),
    priority: String(rule.priority),
    agentId: String(rule.agent_id),
    isActive: rule.is_active,
  }
}

export default function ChannelRoutingRulesPanel({
  channelType,
  instanceId,
  canWrite,
}: ChannelRoutingRulesPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [rules, setRules] = useState<ChannelRoutingRule[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [form, setForm] = useState<RuleFormState | null>(null)

  const agentNames = useMemo(() => {
    const map = new Map<number, string>()
    for (const agent of agents) {
      map.set(agent.id, agent.contact_name || `Agent #${agent.id}`)
    }
    return map
  }, [agents])

  const loadRules = useCallback(async () => {
    setLoading(true)
    setError(null)
    setAgentsError(null)
    try {
      const rulePage = await api.listChannelRoutingRules(channelType, instanceId, { limit: 100 })
      setRules(rulePage.items)
      try {
        const agentRows = await api.getAgents(true)
        setAgents(agentRows)
      } catch (agentErr: unknown) {
        setAgents([])
        setAgentsError(getErrorMessage(agentErr, 'Agent lookup unavailable'))
      }
      setLoaded(true)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load routing rules'))
    } finally {
      setLoading(false)
    }
  }, [channelType, instanceId])

  const toggleExpanded = async () => {
    const next = !expanded
    setExpanded(next)
    if (next && !loaded) {
      await loadRules()
    }
  }

  const startCreate = () => {
    setForm({ ...EMPTY_FORM, agentId: agents[0]?.id ? String(agents[0].id) : '' })
    setError(null)
  }

  const startEdit = (rule: ChannelRoutingRule) => {
    setForm(ruleToForm(rule))
    setError(null)
  }

  const cancelForm = () => {
    setForm(null)
    setError(null)
  }

  const submitForm = async () => {
    if (!form) return
    setSaving(true)
    setError(null)
    try {
      const parsedCriteria: unknown = JSON.parse(form.criteriaText || '{}')
      if (!parsedCriteria || Array.isArray(parsedCriteria) || typeof parsedCriteria !== 'object') {
        throw new Error('Criteria must be a JSON object')
      }
      const agentId = Number(form.agentId)
      if (!Number.isFinite(agentId) || agentId <= 0) {
        throw new Error('Choose an active agent')
      }
      const priority = Number(form.priority)
      if (!Number.isFinite(priority) || priority < 0) {
        throw new Error('Priority must be 0 or greater')
      }
      const payload: ChannelRoutingRuleCreate = {
        event_type: form.eventType.trim() || null,
        criteria: parsedCriteria as Record<string, unknown>,
        priority,
        agent_id: agentId,
        is_active: form.isActive,
      }
      if (form.id) {
        await api.updateChannelRoutingRule(channelType, instanceId, form.id, payload)
      } else {
        await api.createChannelRoutingRule(channelType, instanceId, payload)
      }
      setForm(null)
      await loadRules()
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save routing rule'))
    } finally {
      setSaving(false)
    }
  }

  const deleteRule = async (rule: ChannelRoutingRule) => {
    if (!confirm(`Delete routing rule #${rule.id}?`)) return
    setSaving(true)
    setError(null)
    try {
      await api.deleteChannelRoutingRule(channelType, instanceId, rule.id)
      await loadRules()
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to delete routing rule'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-tsushin-border/70 bg-black/20">
      <button
        type="button"
        onClick={toggleExpanded}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-tsushin-fog hover:text-white"
      >
        <span className="flex items-center gap-2">
          <ZapIcon size={14} className="text-cyan-300" />
          Routing Rules
          {loaded && <span className="text-xs text-tsushin-slate">({rules.length})</span>}
        </span>
        <span className="text-xs text-tsushin-slate">{expanded ? 'Hide' : 'Manage'}</span>
      </button>

      {expanded && (
        <div className="border-t border-tsushin-border/70 p-3">
          <div className="mb-3 flex items-start justify-between gap-3">
            <p className="text-xs text-tsushin-slate">
              Match {channelLabel(channelType)} events to an active agent. Email and Webhook triggers are not shown because the routing-rule API only accepts conversational channels.
            </p>
            <button
              type="button"
              onClick={loadRules}
              disabled={loading}
              title="Refresh routing rules"
              className="shrink-0 rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white disabled:opacity-50"
            >
              <RefreshIcon size={14} />
            </button>
          </div>

          {error && (
            <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}

          {loading ? (
            <div className="py-4 text-center text-xs text-tsushin-slate">Loading routing rules...</div>
          ) : rules.length === 0 ? (
            <div className="rounded-md border border-dashed border-tsushin-border px-3 py-4 text-center text-xs text-tsushin-slate">
              No routing rules for this {channelType} instance.
            </div>
          ) : (
            <div className="space-y-2">
              {rules.map(rule => (
                <div key={rule.id} className="rounded-md border border-tsushin-border/70 bg-tsushin-surface/50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs text-cyan-200">#{rule.id}</span>
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${
                          rule.is_active
                            ? 'border-green-500/30 bg-green-500/10 text-green-300'
                            : 'border-gray-500/30 bg-gray-500/10 text-gray-300'
                        }`}>
                          {rule.is_active ? 'Active' : 'Paused'}
                        </span>
                        <span className="text-xs text-tsushin-slate">Priority {rule.priority}</span>
                      </div>
                      <div className="mt-2 text-xs text-tsushin-slate">
                        Event: <span className="text-white">{rule.event_type || 'Any'}</span>
                      </div>
                      <div className="mt-1 text-xs text-tsushin-slate">
                        Agent: <span className="text-white">{agentNames.get(rule.agent_id) || `Agent #${rule.agent_id}`}</span>
                      </div>
                      <code className="mt-2 block truncate rounded bg-black/30 px-2 py-1 text-[11px] text-tsushin-fog">
                        {JSON.stringify(rule.criteria || {})}
                      </code>
                    </div>
                    {canWrite && agents.length > 0 && (
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          onClick={() => startEdit(rule)}
                          title="Edit routing rule"
                          className="rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white"
                        >
                          <EditIcon size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteRule(rule)}
                          disabled={saving}
                          title="Delete routing rule"
                          className="rounded-md border border-red-500/30 p-1.5 text-red-300 hover:text-white disabled:opacity-50"
                        >
                          <TrashIcon size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {agentsError && (
            <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              Agent lookup is unavailable; routing rules are read-only in this view.
            </div>
          )}

          {canWrite && agents.length > 0 && !form && (
            <button
              type="button"
              onClick={startCreate}
              className="mt-3 inline-flex items-center gap-2 rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 hover:text-white"
            >
              <PlusIcon size={14} />
              Add Rule
            </button>
          )}

          {form && (
            <div className="mt-3 rounded-md border border-cyan-500/30 bg-cyan-500/5 p-3">
              <div className="mb-3 text-sm font-semibold text-white">
                {form.id ? `Edit routing rule #${form.id}` : 'Add routing rule'}
              </div>
              <div className="space-y-3">
                <label className="block text-xs text-tsushin-slate">
                  Event type
                  <input
                    value={form.eventType}
                    onChange={event => setForm(current => current ? { ...current, eventType: event.target.value } : current)}
                    placeholder="message, dm, mention, or blank for any"
                    className="input mt-1 w-full text-sm"
                  />
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-xs text-tsushin-slate">
                    Agent
                    <select
                      value={form.agentId}
                      onChange={event => setForm(current => current ? { ...current, agentId: event.target.value } : current)}
                      className="input mt-1 w-full text-sm"
                    >
                      <option value="">Choose agent</option>
                      {agents.map(agent => (
                        <option key={agent.id} value={agent.id}>{agent.contact_name || `Agent #${agent.id}`}</option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-xs text-tsushin-slate">
                    Priority
                    <input
                      type="number"
                      min="0"
                      value={form.priority}
                      onChange={event => setForm(current => current ? { ...current, priority: event.target.value } : current)}
                      className="input mt-1 w-full text-sm"
                    />
                  </label>
                </div>
                <label className="flex items-center gap-2 text-xs text-tsushin-slate">
                  <input
                    type="checkbox"
                    checked={form.isActive}
                    onChange={event => setForm(current => current ? { ...current, isActive: event.target.checked } : current)}
                  />
                  Rule is active
                </label>
                <label className="block text-xs text-tsushin-slate">
                  Criteria JSON
                  <textarea
                    value={form.criteriaText}
                    onChange={event => setForm(current => current ? { ...current, criteriaText: event.target.value } : current)}
                    rows={5}
                    className="input mt-1 w-full font-mono text-xs"
                  />
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={submitForm}
                    disabled={saving}
                    className="rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 hover:text-white disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : 'Save Rule'}
                  </button>
                  <button
                    type="button"
                    onClick={cancelForm}
                    disabled={saving}
                    className="rounded-md border border-tsushin-border px-3 py-1.5 text-xs text-tsushin-slate hover:text-white disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
