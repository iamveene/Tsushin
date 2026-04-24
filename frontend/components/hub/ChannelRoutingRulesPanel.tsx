'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  type Agent,
  type ChannelRoutingRule,
  type ConversationalChannelType,
} from '@/lib/client'
import {
  AlertTriangleIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  EditIcon,
  PlusIcon,
  RefreshIcon,
  SaveIcon,
  TrashIcon,
  XIcon,
  ZapIcon,
} from '@/components/ui/icons'

interface ChannelRoutingRulesPanelProps {
  channelType: ConversationalChannelType
  instanceId: number
  canWrite: boolean
}

interface RuleFormState {
  id: number | null
  eventType: string
  criteriaText: string
  agentId: string
  isActive: boolean
}

const EMPTY_FORM: RuleFormState = {
  id: null,
  eventType: '',
  criteriaText: '{}',
  agentId: '',
  isActive: true,
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function channelLabel(channelType: ConversationalChannelType): string {
  return channelType.charAt(0).toUpperCase() + channelType.slice(1)
}

function agentLabel(agent: Agent): string {
  return agent.contact_name || `Agent #${agent.id}`
}

function criteriaPreview(rule: ChannelRoutingRule): string {
  try {
    return JSON.stringify(rule.criteria || {})
  } catch {
    return '{}'
  }
}

function nextPriority(rules: ChannelRoutingRule[]): number {
  if (rules.length === 0) return 10
  return Math.max(...rules.map(rule => rule.priority)) + 10
}

function ruleToForm(rule: ChannelRoutingRule): RuleFormState {
  return {
    id: rule.id,
    eventType: rule.event_type || '',
    criteriaText: JSON.stringify(rule.criteria || {}, null, 2),
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
  const [deleting, setDeleting] = useState(false)
  const [reorderingId, setReorderingId] = useState<number | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modalError, setModalError] = useState<string | null>(null)
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [form, setForm] = useState<RuleFormState | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ChannelRoutingRule | null>(null)

  const panelId = `routing-rules-${channelType}-${instanceId}`
  const busy = saving || deleting || reorderingId !== null
  const canManageRules = canWrite && !agentsError
  const canEditRules = canManageRules && agents.length > 0

  const agentNames = useMemo(() => {
    const map = new Map<number, string>()
    for (const agent of agents) {
      map.set(agent.id, agentLabel(agent))
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

  useEffect(() => {
    if (!form && !deleteTarget) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving && !deleting) {
        setForm(null)
        setDeleteTarget(null)
        setModalError(null)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [deleteTarget, deleting, form, saving])

  const toggleExpanded = async () => {
    const next = !expanded
    setExpanded(next)
    if (next && !loaded) {
      await loadRules()
    }
  }

  const startCreate = () => {
    if (!canEditRules) return
    setForm({ ...EMPTY_FORM, agentId: agents[0]?.id ? String(agents[0].id) : '' })
    setDeleteTarget(null)
    setError(null)
    setModalError(null)
  }

  const startEdit = (rule: ChannelRoutingRule) => {
    if (!canEditRules) return
    setForm(ruleToForm(rule))
    setDeleteTarget(null)
    setError(null)
    setModalError(null)
  }

  const closeModals = () => {
    if (busy) return
    setForm(null)
    setDeleteTarget(null)
    setModalError(null)
  }

  const submitForm = async () => {
    if (!form || !canEditRules) return
    setSaving(true)
    setModalError(null)
    try {
      const parsedCriteria: unknown = JSON.parse(form.criteriaText || '{}')
      if (!parsedCriteria || Array.isArray(parsedCriteria) || typeof parsedCriteria !== 'object') {
        throw new Error('Criteria must be a JSON object')
      }
      const agentId = Number(form.agentId)
      if (!Number.isFinite(agentId) || agentId <= 0) {
        throw new Error('Choose an active agent')
      }

      const payload = {
        event_type: form.eventType.trim() || null,
        criteria: parsedCriteria as Record<string, unknown>,
        agent_id: agentId,
        is_active: form.isActive,
      }

      if (form.id) {
        await api.updateChannelRoutingRule(channelType, instanceId, form.id, payload)
      } else {
        await api.createChannelRoutingRule(channelType, instanceId, {
          ...payload,
          priority: nextPriority(rules),
        })
      }

      setForm(null)
      await loadRules()
    } catch (err: unknown) {
      setModalError(getErrorMessage(err, 'Failed to save routing rule'))
    } finally {
      setSaving(false)
    }
  }

  const requestDelete = (rule: ChannelRoutingRule) => {
    if (!canManageRules) return
    setDeleteTarget(rule)
    setForm(null)
    setModalError(null)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    setError(null)
    setModalError(null)
    try {
      await api.deleteChannelRoutingRule(channelType, instanceId, deleteTarget.id)
      setDeleteTarget(null)
      await loadRules()
    } catch (err: unknown) {
      setModalError(getErrorMessage(err, 'Failed to delete routing rule'))
    } finally {
      setDeleting(false)
    }
  }

  const moveRule = async (ruleId: number, direction: -1 | 1) => {
    if (!canManageRules || reorderingId !== null) return
    const currentIndex = rules.findIndex(rule => rule.id === ruleId)
    const targetIndex = currentIndex + direction
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= rules.length) return

    const nextRules = [...rules]
    const currentRule = nextRules[currentIndex]
    nextRules[currentIndex] = nextRules[targetIndex]
    nextRules[targetIndex] = currentRule

    setReorderingId(ruleId)
    setError(null)
    try {
      const page = await api.reorderChannelRoutingRules(channelType, instanceId, {
        rule_ids: nextRules.map(rule => rule.id),
      })
      setRules(page.items)
      setLoaded(true)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to reorder routing rules'))
    } finally {
      setReorderingId(null)
    }
  }

  return (
    <div className="mt-4 overflow-hidden rounded-lg border border-tsushin-border/70 bg-black/20">
      <button
        type="button"
        onClick={toggleExpanded}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-tsushin-fog hover:text-white"
      >
        <span className="flex min-w-0 items-center gap-2">
          <ZapIcon size={14} className="shrink-0 text-cyan-300" />
          <span className="truncate">Routing Rules</span>
          {loaded && <span className="text-xs text-tsushin-slate">({rules.length})</span>}
          {!canWrite && (
            <span className="rounded-full border border-tsushin-border px-2 py-0.5 text-[11px] text-tsushin-slate">
              Read-only
            </span>
          )}
        </span>
        <span className="shrink-0 text-tsushin-slate">
          {expanded ? <ChevronDownIcon size={15} /> : <ChevronRightIcon size={15} />}
        </span>
      </button>

      {expanded && (
        <div id={panelId} className="border-t border-tsushin-border/70 p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-medium text-white">{channelLabel(channelType)} routing</p>
              <p className="mt-0.5 text-[11px] text-tsushin-slate">
                {loaded ? `${rules.length} configured` : 'Not loaded'}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {canEditRules && (
                <button
                  type="button"
                  onClick={startCreate}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-md border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-1.5 text-xs text-cyan-200 hover:text-white disabled:opacity-50"
                >
                  <PlusIcon size={14} />
                  Add
                </button>
              )}
              <button
                type="button"
                onClick={loadRules}
                disabled={loading || busy}
                title="Refresh routing rules"
                className="rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white disabled:opacity-50"
              >
                <RefreshIcon size={14} className={loading ? 'animate-spin' : ''} />
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-3 flex items-start justify-between gap-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">
              <span className="inline-flex min-w-0 items-start gap-2">
                <AlertTriangleIcon size={14} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </span>
              <button type="button" onClick={loadRules} className="shrink-0 text-red-100 underline">
                Retry
              </button>
            </div>
          )}

          {agentsError && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              <AlertTriangleIcon size={14} className="mt-0.5 shrink-0" />
              <span>{agentsError}. Write actions are disabled.</span>
            </div>
          )}

          {canWrite && !agentsError && agents.length === 0 && loaded && (
            <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              No active agents available.
            </div>
          )}

          {loading ? (
            <div className="rounded-md border border-tsushin-border/70 py-5 text-center text-xs text-tsushin-slate">
              Loading routing rules...
            </div>
          ) : rules.length === 0 ? (
            <div className="rounded-md border border-dashed border-tsushin-border px-3 py-5 text-center">
              <p className="text-sm font-medium text-white">No routing rules</p>
              {canEditRules && (
                <button
                  type="button"
                  onClick={startCreate}
                  disabled={busy}
                  className="mt-3 inline-flex items-center gap-2 rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 hover:text-white disabled:opacity-50"
                >
                  <PlusIcon size={14} />
                  Add Rule
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-hidden rounded-md border border-tsushin-border/70">
              {rules.map((rule, index) => {
                const isFirst = index === 0
                const isLast = index === rules.length - 1
                const reordering = reorderingId === rule.id
                return (
                  <div
                    key={rule.id}
                    className="grid gap-3 border-t border-tsushin-border/60 bg-tsushin-surface/35 p-3 first:border-t-0 sm:grid-cols-[auto_1fr_auto]"
                  >
                    {canManageRules && (
                      <div className="flex items-center gap-1 sm:flex-col sm:items-stretch">
                        <button
                          type="button"
                          onClick={() => moveRule(rule.id, -1)}
                          disabled={busy || isFirst}
                          title="Move up"
                          aria-label={`Move routing rule ${rule.id} up`}
                          className="rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white disabled:opacity-40"
                        >
                          {reordering ? <RefreshIcon size={13} className="animate-spin" /> : <ArrowUpIcon size={13} />}
                        </button>
                        <button
                          type="button"
                          onClick={() => moveRule(rule.id, 1)}
                          disabled={busy || isLast}
                          title="Move down"
                          aria-label={`Move routing rule ${rule.id} down`}
                          className="rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white disabled:opacity-40"
                        >
                          {reordering ? <RefreshIcon size={13} className="animate-spin" /> : <ArrowDownIcon size={13} />}
                        </button>
                      </div>
                    )}

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
                        <span className="text-xs text-tsushin-slate">
                          Event <span className="text-white">{rule.event_type || 'Any'}</span>
                        </span>
                      </div>
                      <div className="mt-2 text-xs text-tsushin-slate">
                        Agent <span className="text-white">{agentNames.get(rule.agent_id) || `Agent #${rule.agent_id}`}</span>
                      </div>
                      <code className="mt-2 block truncate rounded bg-black/30 px-2 py-1 text-[11px] text-tsushin-fog">
                        {criteriaPreview(rule)}
                      </code>
                    </div>

                    {canManageRules && (
                      <div className="flex items-start justify-end gap-1">
                        {canEditRules && (
                          <button
                            type="button"
                            onClick={() => startEdit(rule)}
                            disabled={busy}
                            title="Edit routing rule"
                            className="rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white disabled:opacity-50"
                          >
                            <EditIcon size={14} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => requestDelete(rule)}
                          disabled={busy}
                          title="Delete routing rule"
                          className="rounded-md border border-red-500/30 p-1.5 text-red-300 hover:text-white disabled:opacity-50"
                        >
                          <TrashIcon size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {form && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) closeModals()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="routing-rule-modal-title"
            className="w-full max-w-2xl rounded-lg border border-tsushin-border bg-tsushin-surface shadow-2xl"
          >
            <div className="flex items-center justify-between gap-3 border-b border-tsushin-border px-4 py-3">
              <div>
                <h3 id="routing-rule-modal-title" className="text-sm font-semibold text-white">
                  {form.id ? `Edit routing rule #${form.id}` : 'Add routing rule'}
                </h3>
                <p className="mt-0.5 text-xs text-tsushin-slate">{channelLabel(channelType)} instance #{instanceId}</p>
              </div>
              <button
                type="button"
                onClick={closeModals}
                disabled={saving}
                title="Close"
                className="rounded-md border border-tsushin-border p-1.5 text-tsushin-slate hover:text-white disabled:opacity-50"
              >
                <XIcon size={15} />
              </button>
            </div>

            <div className="space-y-4 px-4 py-4">
              {modalError && (
                <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">
                  <AlertTriangleIcon size={14} className="mt-0.5 shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <label className="block text-xs text-tsushin-slate">
                Event type
                <input
                  value={form.eventType}
                  onChange={event => setForm(current => current ? { ...current, eventType: event.target.value } : current)}
                  placeholder="Any event"
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
                      <option key={agent.id} value={agent.id}>{agentLabel(agent)}</option>
                    ))}
                  </select>
                </label>

                <label className="flex items-center justify-between gap-3 rounded-md border border-tsushin-border/70 bg-black/20 px-3 py-2 text-xs text-tsushin-slate">
                  <span>Active</span>
                  <input
                    type="checkbox"
                    checked={form.isActive}
                    onChange={event => setForm(current => current ? { ...current, isActive: event.target.checked } : current)}
                    className="h-4 w-4"
                  />
                </label>
              </div>

              <label className="block text-xs text-tsushin-slate">
                Criteria JSON
                <textarea
                  value={form.criteriaText}
                  onChange={event => setForm(current => current ? { ...current, criteriaText: event.target.value } : current)}
                  rows={7}
                  className="input mt-1 w-full resize-y font-mono text-xs"
                />
              </label>
            </div>

            <div className="flex justify-end gap-2 border-t border-tsushin-border px-4 py-3">
              <button
                type="button"
                onClick={closeModals}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-md border border-tsushin-border px-3 py-1.5 text-xs text-tsushin-slate hover:text-white disabled:opacity-50"
              >
                <XIcon size={14} />
                Cancel
              </button>
              <button
                type="button"
                onClick={submitForm}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 hover:text-white disabled:opacity-50"
              >
                <SaveIcon size={14} />
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) closeModals()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="routing-rule-delete-title"
            className="w-full max-w-md rounded-lg border border-red-500/30 bg-tsushin-surface shadow-2xl"
          >
            <div className="border-b border-tsushin-border px-4 py-3">
              <h3 id="routing-rule-delete-title" className="text-sm font-semibold text-white">
                Delete routing rule #{deleteTarget.id}
              </h3>
              <p className="mt-1 text-xs text-tsushin-slate">
                {deleteTarget.event_type || 'Any event'} - {agentNames.get(deleteTarget.agent_id) || `Agent #${deleteTarget.agent_id}`}
              </p>
            </div>

            {modalError && (
              <div className="mx-4 mt-4 flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-100">
                <AlertTriangleIcon size={14} className="mt-0.5 shrink-0" />
                <span>{modalError}</span>
              </div>
            )}

            <div className="flex justify-end gap-2 px-4 py-4">
              <button
                type="button"
                onClick={closeModals}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-md border border-tsushin-border px-3 py-1.5 text-xs text-tsushin-slate hover:text-white disabled:opacity-50"
              >
                <XIcon size={14} />
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs text-red-200 hover:text-white disabled:opacity-50"
              >
                <TrashIcon size={14} />
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
