'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  api,
  type Agent,
  type ContinuousAgent,
  type ContinuousAgentActionKind,
  type ContinuousAgentCreate,
  type ContinuousAgentUpdate,
} from '@/lib/client'

type ExecutionMode = 'autonomous' | 'hybrid' | 'notify_only'
type AgentStatus = 'active' | 'paused' | 'disabled'

const EXECUTION_MODES: ExecutionMode[] = ['autonomous', 'hybrid', 'notify_only']
const STATUSES: AgentStatus[] = ['active', 'paused', 'disabled']

const ACTION_KINDS: { id: ContinuousAgentActionKind; label: string; hint: string }[] = [
  { id: 'tool_run',           label: 'Run a tool',          hint: 'Execute a sandboxed skill / tool when triggered.' },
  { id: 'send_message',       label: 'Send a message',      hint: 'Send a notification or reply when triggered.' },
  { id: 'conditional_branch', label: 'Conditional branch',  hint: 'Inspect the wake event and choose a path (e.g. escalate if X).' },
  { id: 'react_only',         label: 'React-only',          hint: 'Log/observe the event without taking external action.' },
]

const PURPOSE_MIN = 30

interface Props {
  isOpen: boolean
  onClose: () => void
  onSaved: (agent: ContinuousAgent) => void
  existing?: ContinuousAgent | null
}

interface FormState {
  agentId: number | ''
  name: string
  purpose: string
  actionKind: ContinuousAgentActionKind | ''
  executionMode: ExecutionMode
  status: AgentStatus
}

const EMPTY_FORM: FormState = {
  agentId: '',
  name: '',
  purpose: '',
  actionKind: '',
  executionMode: 'hybrid',
  status: 'active',
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export function ContinuousAgentSetupModal({ isOpen, onClose, onSaved, existing }: Props) {
  const isEdit = Boolean(existing)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [agents, setAgents] = useState<Agent[]>([])
  const [loadingAgents, setLoadingAgents] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    setError(null)
    setForm(
      existing
        ? {
            agentId: existing.agent_id,
            name: existing.name || '',
            purpose: existing.purpose || '',
            actionKind: (existing.action_kind as ContinuousAgentActionKind) || '',
            executionMode: (existing.execution_mode as ExecutionMode) || 'hybrid',
            status: (existing.status as AgentStatus) || 'active',
          }
        : EMPTY_FORM,
    )
  }, [isOpen, existing])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setLoadingAgents(true)
    api
      .getAgents(true)
      .then((rows) => {
        if (!cancelled) setAgents(rows)
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'Failed to load agents'))
      })
      .finally(() => {
        if (!cancelled) setLoadingAgents(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  const purposeTrimmed = form.purpose.trim()
  const purposeValid = purposeTrimmed.length >= PURPOSE_MIN
  const canSubmit = useMemo(() => {
    if (submitting) return false
    if (form.agentId === '') return false
    if (!purposeValid) return false
    if (!form.actionKind) return false
    return true
  }, [form.agentId, form.actionKind, purposeValid, submitting])

  if (!isOpen) return null

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const trimmedName = form.name.trim() || null
      const actionKind = form.actionKind as ContinuousAgentActionKind
      let saved: ContinuousAgent
      if (existing) {
        const payload: ContinuousAgentUpdate = {
          name: trimmedName,
          purpose: purposeTrimmed,
          action_kind: actionKind,
          execution_mode: form.executionMode,
          status: form.status,
        }
        saved = await api.updateContinuousAgent(existing.id, payload)
      } else {
        if (form.agentId === '') {
          setError('Select an agent')
          setSubmitting(false)
          return
        }
        const payload: ContinuousAgentCreate = {
          agent_id: form.agentId as number,
          name: trimmedName,
          purpose: purposeTrimmed,
          action_kind: actionKind,
          execution_mode: form.executionMode,
          status: form.status,
        }
        saved = await api.createContinuousAgent(payload)
      }
      onSaved(saved)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save continuous agent'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose()
      }}
    >
      <div className="w-full max-w-2xl rounded-2xl border border-tsushin-border bg-tsushin-surface p-6 shadow-2xl text-white max-h-[90vh] overflow-y-auto">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">
              {isEdit ? 'Edit Continuous Agent' : 'Create Continuous Agent'}
            </h2>
            <p className="mt-1 text-sm text-tsushin-slate">
              Always-on wrapper around an existing agent. Wakes when an external event fires
              (email, Jira, GitHub, webhook). For a multi-step workflow on a schedule or
              keyword instead, create a <strong className="text-white">Flow</strong>.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md p-1 text-tsushin-slate hover:bg-tsushin-border hover:text-white disabled:opacity-40"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-tsushin-fog">Base agent</label>
            <select
              value={form.agentId === '' ? '' : String(form.agentId)}
              onChange={(event) => {
                const value = event.target.value
                setForm((prev) => ({ ...prev, agentId: value === '' ? '' : Number(value) }))
              }}
              disabled={isEdit || loadingAgents || submitting}
              className="w-full rounded-lg border border-tsushin-border bg-tsushin-bg px-3 py-2 text-sm text-white disabled:opacity-60"
            >
              <option value="">{loadingAgents ? 'Loading agents…' : 'Select an agent'}</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  #{agent.id} — {agent.contact_name || `Agent ${agent.id}`}
                </option>
              ))}
            </select>
            {isEdit && (
              <p className="mt-1 text-xs text-tsushin-slate">Base agent cannot be changed after creation.</p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-tsushin-fog">
              Purpose <span className="text-red-400">*</span>
            </label>
            <textarea
              value={form.purpose}
              maxLength={2000}
              rows={3}
              onChange={(event) => setForm((prev) => ({ ...prev, purpose: event.target.value }))}
              placeholder="e.g. When a new Jira ticket is filed by Support, check severity and notify on-call if P0/P1."
              disabled={submitting}
              className="w-full rounded-lg border border-tsushin-border bg-tsushin-bg px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
            />
            <p className={`mt-1 text-xs ${purposeValid ? 'text-tsushin-slate' : 'text-amber-300'}`}>
              {purposeTrimmed.length}/{PURPOSE_MIN}+ characters — explain what the agent does when it wakes.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-tsushin-fog">
              Action kind <span className="text-red-400">*</span>
            </label>
            <div className="grid gap-2 sm:grid-cols-2">
              {ACTION_KINDS.map((kind) => {
                const selected = form.actionKind === kind.id
                return (
                  <button
                    key={kind.id}
                    type="button"
                    onClick={() => setForm((prev) => ({ ...prev, actionKind: kind.id }))}
                    disabled={submitting}
                    className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                      selected
                        ? 'border-cyan-500/60 bg-cyan-500/10 text-white'
                        : 'border-tsushin-border bg-tsushin-bg text-tsushin-slate hover:text-white'
                    }`}
                  >
                    <div className="text-sm font-medium">{kind.label}</div>
                    <div className="mt-0.5 text-xs leading-snug text-tsushin-slate">{kind.hint}</div>
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-tsushin-fog">Display name (optional)</label>
            <input
              type="text"
              value={form.name}
              maxLength={128}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="e.g. Email Watcher"
              disabled={submitting}
              className="w-full rounded-lg border border-tsushin-border bg-tsushin-bg px-3 py-2 text-sm text-white placeholder:text-tsushin-slate"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-tsushin-fog">Execution mode</label>
            <div className="flex flex-wrap gap-2">
              {EXECUTION_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setForm((prev) => ({ ...prev, executionMode: mode }))}
                  disabled={submitting}
                  className={`rounded-lg border px-3 py-1.5 text-sm capitalize transition-colors ${
                    form.executionMode === mode
                      ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-200'
                      : 'border-tsushin-border text-tsushin-slate hover:text-white'
                  }`}
                >
                  {mode.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          {isEdit && (
            <div>
              <label className="mb-1 block text-sm font-medium text-tsushin-fog">Status</label>
              <select
                value={form.status}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, status: event.target.value as AgentStatus }))
                }
                disabled={submitting}
                className="w-full rounded-lg border border-tsushin-border bg-tsushin-bg px-3 py-2 text-sm text-white"
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create agent'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ContinuousAgentSetupModal
