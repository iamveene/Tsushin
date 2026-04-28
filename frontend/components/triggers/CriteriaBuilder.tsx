'use client'

import { useMemo, useState } from 'react'
import type { TriggerCriteria, TriggerKind } from '@/lib/client'
import {
  CheckCircleIcon,
  CodeIcon,
  EnvelopeIcon,
  FilterIcon,
  GitHubIcon,
  PlayIcon,
  WebhookIcon,
  XCircleIcon,
} from '@/components/ui/icons'

export interface CriteriaTestResult {
  matched: boolean
  reason?: string | null
}

export interface CriteriaSourceValues {
  emailSearchQuery?: string | null
  emailSender?: string | null
  emailSubject?: string | null
  emailBodyKeyword?: string | null
  jiraJql?: string | null
  jiraProjectKey?: string | null
  githubEventsText?: string | null
  githubBranchFilter?: string | null
  githubPathFiltersText?: string | null
  githubAuthorFilter?: string | null
}

interface Props {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  kind?: TriggerKind
  source?: CriteriaSourceValues
  onSourceChange?: (patch: Partial<CriteriaSourceValues>) => void
  onTest?: (criteria: TriggerCriteria | null, payload: Record<string, unknown>) => Promise<CriteriaTestResult>
  readOnlyReason?: string | null
}

const DEFAULT_PAYLOAD = {
  type: 'incident',
  source: 'preview',
}

const JSONPATH_TEMPLATE = {
  criteria_version: 1,
  filters: {
    jsonpath_matchers: [
      {
        path: '$.type',
        operator: 'equals',
        value: 'incident',
      },
    ],
  },
  window: {
    mode: 'since_cursor',
  },
  ordering: 'oldest_first',
  dedupe_scope: 'instance',
}

const GITHUB_EVENT_OPTIONS = ['push', 'pull_request', 'issues', 'issue_comment', 'release', 'workflow_run']

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function baseCriteria(filters: Record<string, unknown>, extras: Record<string, unknown> = {}): TriggerCriteria {
  return {
    criteria_version: 1,
    filters,
    window: {
      mode: 'since_cursor',
    },
    ordering: 'oldest_first',
    dedupe_scope: 'instance',
    ...extras,
  }
}

function nullableTrim(value?: string | null): string | null {
  const trimmed = (value || '').trim()
  return trimmed || null
}

function csvValues(value?: string | null): string[] {
  return (value || '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function quoteGmailValue(value: string): string {
  return /\s/.test(value) ? `(${value})` : value
}

export function emailSourceFromSearchQuery(searchQuery?: string | null): CriteriaSourceValues {
  const query = searchQuery || ''
  const sender = query.match(/(?:^|\s)from:([^\s)]+)/)?.[1] || ''
  const subject = query.match(/(?:^|\s)subject:\(([^)]+)\)/)?.[1] || query.match(/(?:^|\s)subject:([^\s]+)/)?.[1] || ''
  return {
    emailSearchQuery: query,
    emailSender: sender,
    emailSubject: subject,
    emailBodyKeyword: '',
  }
}

export function buildEmailSearchQuery(source?: CriteriaSourceValues): string {
  const base = nullableTrim(source?.emailSearchQuery)
  const sender = nullableTrim(source?.emailSender)
  const subject = nullableTrim(source?.emailSubject)
  const parts = base ? [base] : []
  if (sender && !parts.some((part) => /\bfrom:/.test(part))) {
    parts.push(`from:${sender}`)
  }
  if (subject && !parts.some((part) => /\bsubject:/.test(part))) {
    parts.push(`subject:${quoteGmailValue(subject)}`)
  }
  return parts.join(' ').trim()
}

export function buildCriteriaTemplate(kind: TriggerKind = 'webhook', source: CriteriaSourceValues = {}): TriggerCriteria {
  if (kind === 'email') {
    const bodyKeyword = nullableTrim(source.emailBodyKeyword)
    return baseCriteria({
      email: {
        search_query: buildEmailSearchQuery(source) || null,
        sender: nullableTrim(source.emailSender),
        subject_contains: nullableTrim(source.emailSubject),
        body_contains: bodyKeyword,
      },
      ...(bodyKeyword
        ? {
            jsonpath_matchers: [
              {
                path: '$.message.body_text',
                operator: 'contains',
                value: bodyKeyword,
              },
            ],
          }
        : {}),
    })
  }

  if (kind === 'jira') {
    return baseCriteria({
      jira: {
        project_key: nullableTrim(source.jiraProjectKey),
        jql_hint: nullableTrim(source.jiraJql),
      },
      jsonpath_matchers: [
        {
          path: '$.issue.fields.priority.name',
          operator: 'in',
          value: ['High', 'Highest'],
        },
      ],
    })
  }

  if (kind === 'github') {
    return baseCriteria({
      github: {
        events: csvValues(source.githubEventsText),
        branch: nullableTrim(source.githubBranchFilter),
        paths: csvValues(source.githubPathFiltersText),
        author: nullableTrim(source.githubAuthorFilter),
      },
      jsonpath_matchers: [
        {
          path: '$.sender.login',
          operator: 'exists',
        },
      ],
    })
  }

  return JSONPATH_TEMPLATE
}

export function formatCriteriaText(value?: TriggerCriteria | null): string {
  return value ? pretty(value) : ''
}

export function parseCriteriaText(text: string): TriggerCriteria | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Criteria must be a JSON object')
  }
  return parsed as TriggerCriteria
}

function parsePayloadText(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Payload must be a JSON object')
  }
  return parsed as Record<string, unknown>
}

function inputClass(disabled: boolean): string {
  return `w-full rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 disabled:opacity-60 ${disabled ? 'cursor-not-allowed' : ''}`
}

function textAreaClass(disabled: boolean): string {
  return `w-full rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 disabled:opacity-60 ${disabled ? 'cursor-not-allowed' : ''}`
}

function FieldLabel({ children }: { children: string }) {
  return <label className="block text-xs font-medium text-tsushin-slate">{children}</label>
}

export default function CriteriaBuilder({
  value,
  onChange,
  disabled = false,
  kind = 'webhook',
  source = {},
  onSourceChange,
  onTest,
  readOnlyReason,
}: Props) {
  const [payloadText, setPayloadText] = useState(pretty(DEFAULT_PAYLOAD))
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null)
  const hasCriteria = value.trim().length > 0
  const canEditSource = Boolean(onSourceChange) && !disabled

  const config = useMemo(() => {
    if (kind === 'email') return { title: 'Email criteria', Icon: EnvelopeIcon, accent: 'text-cyan-200' }
    if (kind === 'jira') return { title: 'Jira criteria', Icon: CodeIcon, accent: 'text-blue-200' }
    if (kind === 'github') return { title: 'GitHub criteria', Icon: GitHubIcon, accent: 'text-violet-200' }
    return { title: 'Webhook criteria', Icon: WebhookIcon, accent: 'text-cyan-200' }
  }, [kind])

  const Icon = config.Icon

  const updateSource = (patch: Partial<CriteriaSourceValues>) => {
    if (!onSourceChange || disabled) return
    onSourceChange(patch)
  }

  const applyTemplate = (nextKind: TriggerKind = kind) => {
    onChange(pretty(buildCriteriaTemplate(nextKind, source)))
    setMessage({ tone: 'info', text: `${nextKind[0].toUpperCase()}${nextKind.slice(1)} template inserted.` })
  }

  const clearCriteria = () => {
    onChange('')
    setMessage(null)
  }

  const applyEmailQuery = () => {
    const nextQuery = buildEmailSearchQuery(source)
    updateSource({ emailSearchQuery: nextQuery })
    onChange(pretty(buildCriteriaTemplate('email', { ...source, emailSearchQuery: nextQuery })))
    setMessage({ tone: 'info', text: 'Email criteria preview refreshed.' })
  }

  const toggleGithubEvent = (eventName: string) => {
    const current = csvValues(source.githubEventsText)
    const next = current.includes(eventName)
      ? current.filter((item) => item !== eventName)
      : [...current, eventName]
    updateSource({ githubEventsText: next.join(', ') })
  }

  const testCriteria = async () => {
    if (!onTest || testing) return
    setTesting(true)
    setMessage(null)
    try {
      const criteria = parseCriteriaText(value)
      const payload = parsePayloadText(payloadText)
      const result = await onTest(criteria, payload)
      setMessage({
        tone: result.matched ? 'success' : 'error',
        text: result.matched ? 'Criteria matched the payload.' : `No match${result.reason ? `: ${result.reason}` : ''}.`,
      })
    } catch (error: unknown) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : 'Criteria test failed' })
    } finally {
      setTesting(false)
    }
  }

  const renderKindControls = () => {
    if (kind === 'email') {
      return (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <FieldLabel>Gmail search</FieldLabel>
            <input
              value={source.emailSearchQuery || ''}
              onChange={(event) => updateSource({ emailSearchQuery: event.target.value })}
              disabled={!canEditSource}
              placeholder="newer_than:1d -category:promotions"
              className={inputClass(!canEditSource)}
            />
          </div>
          <div className="space-y-2">
            <FieldLabel>Sender</FieldLabel>
            <input
              value={source.emailSender || ''}
              onChange={(event) => updateSource({ emailSender: event.target.value })}
              disabled={!canEditSource}
              placeholder="alerts@example.com"
              className={inputClass(!canEditSource)}
            />
          </div>
          <div className="space-y-2">
            <FieldLabel>Subject contains</FieldLabel>
            <input
              value={source.emailSubject || ''}
              onChange={(event) => updateSource({ emailSubject: event.target.value })}
              disabled={!canEditSource}
              placeholder="incident"
              className={inputClass(!canEditSource)}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <FieldLabel>Body keyword</FieldLabel>
            <input
              value={source.emailBodyKeyword || ''}
              onChange={(event) => updateSource({ emailBodyKeyword: event.target.value })}
              disabled={!canEditSource}
              placeholder="XYZ"
              className={inputClass(!canEditSource)}
            />
          </div>
          <button
            type="button"
            onClick={applyEmailQuery}
            disabled={disabled}
            className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200 hover:text-white disabled:opacity-50 md:col-span-2"
          >
            Apply Email Preview
          </button>
        </div>
      )
    }

    if (kind === 'jira') {
      return (
        <div className="grid gap-3 md:grid-cols-[160px_minmax(0,1fr)]">
          <div className="space-y-2">
            <FieldLabel>Project</FieldLabel>
            <input
              value={source.jiraProjectKey || ''}
              onChange={(event) => updateSource({ jiraProjectKey: event.target.value.toUpperCase() })}
              disabled={!canEditSource}
              placeholder="OPS"
              className={inputClass(!canEditSource)}
            />
          </div>
          <div className="space-y-2">
            <FieldLabel>JQL</FieldLabel>
            <textarea
              value={source.jiraJql || ''}
              onChange={(event) => updateSource({ jiraJql: event.target.value })}
              disabled={!canEditSource}
              rows={3}
              placeholder="project = OPS AND statusCategory != Done ORDER BY updated DESC"
              className={textAreaClass(!canEditSource)}
            />
          </div>
          <button
            type="button"
            onClick={() => applyTemplate('jira')}
            disabled={disabled}
            className="rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-xs text-blue-200 hover:text-white disabled:opacity-50 md:col-span-2"
          >
            Priority JSON Template
          </button>
        </div>
      )
    }

    if (kind === 'github') {
      const selectedEvents = csvValues(source.githubEventsText)
      return (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <FieldLabel>Events</FieldLabel>
            <div className="flex flex-wrap gap-2">
              {GITHUB_EVENT_OPTIONS.map((eventName) => (
                <button
                  key={eventName}
                  type="button"
                  onClick={() => toggleGithubEvent(eventName)}
                  disabled={!canEditSource}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    selectedEvents.includes(eventName)
                      ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                      : 'border-tsushin-border text-tsushin-slate hover:text-white'
                  } disabled:opacity-50`}
                >
                  {eventName.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <FieldLabel>Branch</FieldLabel>
            <input
              value={source.githubBranchFilter || ''}
              onChange={(event) => updateSource({ githubBranchFilter: event.target.value })}
              disabled={!canEditSource}
              placeholder="main"
              className={inputClass(!canEditSource)}
            />
          </div>
          <div className="space-y-2">
            <FieldLabel>Author</FieldLabel>
            <input
              value={source.githubAuthorFilter || ''}
              onChange={(event) => updateSource({ githubAuthorFilter: event.target.value })}
              disabled={!canEditSource}
              placeholder="octocat"
              className={inputClass(!canEditSource)}
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <FieldLabel>Path filters</FieldLabel>
            <textarea
              value={source.githubPathFiltersText || ''}
              onChange={(event) => updateSource({ githubPathFiltersText: event.target.value })}
              disabled={!canEditSource}
              rows={3}
              placeholder={'frontend/**\nbackend/api/**'}
              className={textAreaClass(!canEditSource)}
            />
          </div>
          <button
            type="button"
            onClick={() => applyTemplate('github')}
            disabled={disabled}
            className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-2 text-xs text-violet-200 hover:text-white disabled:opacity-50 md:col-span-2"
          >
            GitHub JSON Template
          </button>
        </div>
      )
    }

    return (
      <div className="grid gap-3">
        <button
          type="button"
          onClick={() => applyTemplate('webhook')}
          disabled={disabled}
          className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200 hover:text-white disabled:opacity-50"
        >
          JSONPath Template
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/60 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <Icon size={16} className={config.accent} /> {config.title}
        </h3>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => applyTemplate(kind)}
            disabled={disabled}
            className="rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-1.5 text-xs text-tsushin-fog hover:text-white disabled:opacity-50"
          >
            Template
          </button>
          <button
            type="button"
            onClick={clearCriteria}
            disabled={disabled}
            className="rounded-lg border border-tsushin-border bg-transparent px-3 py-1.5 text-xs text-tsushin-slate hover:text-white disabled:opacity-50"
          >
            Clear JSON
          </button>
        </div>
      </div>

      {readOnlyReason && (
        <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-100">
          {readOnlyReason}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(260px,0.9fr)_minmax(0,1.1fr)]">
        <div className="space-y-4">
          <div className="rounded-lg border border-tsushin-border/70 bg-black/10 p-3">
            <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
              <FilterIcon size={14} /> Helpers
            </div>
            {renderKindControls()}
          </div>

          {onTest && (
            <div className="rounded-lg border border-tsushin-border/70 bg-black/10 p-3">
              <FieldLabel>Test payload</FieldLabel>
              <textarea
                value={payloadText}
                onChange={(event) => setPayloadText(event.target.value)}
                rows={5}
                disabled={disabled}
                className={`${textAreaClass(disabled)} mt-2`}
              />
              <button
                type="button"
                onClick={testCriteria}
                disabled={disabled || testing}
                className="mt-3 inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
              >
                <PlayIcon size={14} />
                {testing ? 'Testing...' : 'Test Criteria'}
              </button>
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 flex items-center justify-between gap-3">
            <label className="text-xs font-medium uppercase tracking-wide text-tsushin-slate">Raw JSON</label>
            {!hasCriteria && (
              <span className="rounded-full border border-tsushin-border px-2 py-0.5 text-[11px] text-tsushin-slate">No extra criteria</span>
            )}
          </div>
          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            rows={16}
            disabled={disabled}
            placeholder={pretty(buildCriteriaTemplate(kind, source))}
            className={`${textAreaClass(disabled)} min-h-[360px]`}
          />
        </div>
      </div>

      {message && (
        <div className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
          message.tone === 'success'
            ? 'border-green-500/30 bg-green-500/10 text-green-200'
            : message.tone === 'error'
            ? 'border-red-500/30 bg-red-500/10 text-red-200'
            : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200'
        }`}>
          {message.tone === 'success' ? <CheckCircleIcon size={14} className="mt-0.5 shrink-0" /> : <XCircleIcon size={14} className="mt-0.5 shrink-0" />}
          <span>{message.text}</span>
        </div>
      )}
    </div>
  )
}
