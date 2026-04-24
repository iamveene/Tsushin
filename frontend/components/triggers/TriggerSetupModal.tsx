'use client'

import { useEffect, useMemo, useState } from 'react'
import type { ComponentType } from 'react'
import Modal from '@/components/ui/Modal'
import { api, type Agent, type GitHubTrigger, type GitHubTriggerAuthMethod, type JiraTrigger, type ScheduleTrigger, type TriggerCriteria, type TriggerKind } from '@/lib/client'
import { CalendarDaysIcon, CodeIcon, GitHubIcon, PlayIcon, type IconProps } from '@/components/ui/icons'
import CriteriaBuilder, { parseCriteriaText } from '@/components/triggers/CriteriaBuilder'

type BreadthTriggerKind = Extract<TriggerKind, 'jira' | 'schedule' | 'github'>
type SavedTrigger = JiraTrigger | ScheduleTrigger | GitHubTrigger

interface Props {
  isOpen: boolean
  triggerType: BreadthTriggerKind
  onClose: () => void
  onSaved?: (trigger: SavedTrigger) => void
}

const KIND_CONFIG: Record<BreadthTriggerKind, {
  title: string
  description: string
  accent: string
  button: string
  Icon: ComponentType<IconProps>
}> = {
  jira: {
    title: 'Create Jira Trigger',
    description: 'Poll a JQL query and wake an agent when matching issues change.',
    accent: 'border-blue-500/30 bg-blue-500/10 text-blue-100',
    button: 'bg-blue-600 hover:bg-blue-500',
    Icon: CodeIcon,
  },
  schedule: {
    title: 'Create Schedule Trigger',
    description: 'Use a cron expression to wake agents with a structured payload.',
    accent: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
    button: 'bg-amber-500 hover:bg-amber-400 text-[#1c1300]',
    Icon: CalendarDaysIcon,
  },
  github: {
    title: 'Create GitHub Trigger',
    description: 'Listen for repository activity and wake agents from signed GitHub events.',
    accent: 'border-violet-500/30 bg-violet-500/10 text-violet-100',
    button: 'bg-violet-600 hover:bg-violet-500',
    Icon: GitHubIcon,
  },
}

const GITHUB_EVENT_OPTIONS = ['push', 'pull_request', 'issues', 'issue_comment', 'release', 'workflow_run']

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function parseJsonObject(text: string, label: string): Record<string, unknown> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return parsed as Record<string, unknown>
}

function splitList(text: string): string[] | null {
  const values = text
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean)
  return values.length > 0 ? values : null
}

export default function TriggerSetupModal({ isOpen, triggerType, onClose, onSaved }: Props) {
  const config = KIND_CONFIG[triggerType]
  const Icon = config.Icon
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ tone: 'success' | 'error' | 'info'; message: string } | null>(null)

  const [integrationName, setIntegrationName] = useState('')
  const [defaultAgentId, setDefaultAgentId] = useState<number | null>(null)
  const [isActive, setIsActive] = useState(true)
  const [criteriaText, setCriteriaText] = useState('')

  const [jiraSiteUrl, setJiraSiteUrl] = useState('')
  const [jiraProjectKey, setJiraProjectKey] = useState('')
  const [jiraJql, setJiraJql] = useState('project = OPS ORDER BY updated DESC')
  const [jiraAuthEmail, setJiraAuthEmail] = useState('')
  const [jiraApiToken, setJiraApiToken] = useState('')
  const [jiraPollInterval, setJiraPollInterval] = useState('300')

  const [cronExpression, setCronExpression] = useState('0 * * * *')
  const [timezone, setTimezone] = useState('UTC')
  const [payloadTemplateText, setPayloadTemplateText] = useState('{\n  "source": "schedule"\n}')

  const [githubAuthMethod, setGithubAuthMethod] = useState<GitHubTriggerAuthMethod>('pat')
  const [repoOwner, setRepoOwner] = useState('')
  const [repoName, setRepoName] = useState('')
  const [installationId, setInstallationId] = useState('')
  const [patToken, setPatToken] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [githubEvents, setGithubEvents] = useState<string[]>(['push', 'pull_request'])
  const [branchFilter, setBranchFilter] = useState('')
  const [pathFiltersText, setPathFiltersText] = useState('')
  const [authorFilter, setAuthorFilter] = useState('')

  useEffect(() => {
    if (!isOpen) return
    setError(null)
    setTestResult(null)
    setSaving(false)
    setTesting(false)
    setIntegrationName(triggerType === 'schedule' ? 'Hourly schedule' : triggerType === 'jira' ? 'Jira issue watcher' : 'GitHub repository events')
    setDefaultAgentId(null)
    setIsActive(true)
    setCriteriaText('')
    setJiraSiteUrl('')
    setJiraProjectKey('')
    setJiraJql('project = OPS ORDER BY updated DESC')
    setJiraAuthEmail('')
    setJiraApiToken('')
    setJiraPollInterval('300')
    setCronExpression('0 * * * *')
    setTimezone('UTC')
    setPayloadTemplateText('{\n  "source": "schedule"\n}')
    setGithubAuthMethod('pat')
    setRepoOwner('')
    setRepoName('')
    setInstallationId('')
    setPatToken('')
    setWebhookSecret('')
    setGithubEvents(['push', 'pull_request'])
    setBranchFilter('')
    setPathFiltersText('')
    setAuthorFilter('')

    let cancelled = false
    setAgentsLoading(true)
    api.getAgents(true)
      .then((list) => {
        if (!cancelled) setAgents(list)
      })
      .catch(() => {
        if (!cancelled) setAgents([])
      })
      .finally(() => {
        if (!cancelled) setAgentsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [isOpen, triggerType])

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === defaultAgentId) || null,
    [agents, defaultAgentId],
  )

  const canSubmit = useMemo(() => {
    if (saving || !integrationName.trim()) return false
    if (triggerType === 'jira') {
      const poll = Number(jiraPollInterval)
      return Boolean(jiraSiteUrl.trim() && jiraJql.trim() && Number.isFinite(poll) && poll >= 60 && poll <= 3600)
    }
    if (triggerType === 'schedule') {
      return Boolean(cronExpression.trim() && timezone.trim())
    }
    return Boolean(repoOwner.trim() && repoName.trim() && githubEvents.length > 0)
  }, [cronExpression, githubEvents.length, integrationName, jiraJql, jiraPollInterval, jiraSiteUrl, repoName, repoOwner, saving, timezone, triggerType])

  const runValidation = () => {
    const criteria = parseCriteriaText(criteriaText)
    const payloadTemplate = triggerType === 'schedule'
      ? parseJsonObject(payloadTemplateText, 'Payload template')
      : null
    return { criteria: criteria as TriggerCriteria | null, payloadTemplate }
  }

  const handleTest = async () => {
    setError(null)
    setTestResult(null)
    setTesting(true)
    try {
      if (triggerType === 'jira') {
        const result = await api.testJiraTriggerQuery({
          site_url: jiraSiteUrl.trim(),
          jql: jiraJql.trim(),
          auth_email: jiraAuthEmail.trim() || null,
          api_token: jiraApiToken.trim() || null,
        })
        setTestResult({
          tone: result.success ? 'success' : 'error',
          message: result.success
            ? `Query returned ${result.issue_count ?? 0} issue(s).`
            : result.error || result.message || 'Jira query test failed',
        })
      } else if (triggerType === 'schedule') {
        const { payloadTemplate } = runValidation()
        const result = await api.previewScheduleTrigger({
          cron_expression: cronExpression.trim(),
          timezone: timezone.trim(),
          payload_template: payloadTemplate,
        })
        const times = result.next_fire_times || result.next_fire_preview || result.next_runs || []
        setTestResult({
          tone: result.error ? 'error' : 'success',
          message: result.error || (times.length > 0 ? `Next runs: ${times.slice(0, 3).join(', ')}` : result.message || 'Schedule preview returned no runs.'),
        })
      } else {
        const result = await api.testGitHubTriggerConnection({
          auth_method: githubAuthMethod,
          repo_owner: repoOwner.trim(),
          repo_name: repoName.trim(),
          installation_id: installationId.trim() || null,
          pat_token: patToken.trim() || null,
        })
        setTestResult({
          tone: result.success ? 'success' : 'error',
          message: result.success
            ? result.message || `Connected to ${result.repository || `${repoOwner}/${repoName}`}.`
            : result.error || result.message || 'GitHub connection failed',
        })
      }
    } catch (err: unknown) {
      setTestResult({ tone: 'error', message: getErrorMessage(err, 'Validation failed') })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!canSubmit) return
    setError(null)
    setTestResult(null)
    setSaving(true)
    try {
      const { criteria, payloadTemplate } = runValidation()
      let saved: SavedTrigger
      if (triggerType === 'jira') {
        saved = await api.createJiraTrigger({
          integration_name: integrationName.trim(),
          site_url: jiraSiteUrl.trim(),
          project_key: jiraProjectKey.trim() || null,
          jql: jiraJql.trim(),
          auth_email: jiraAuthEmail.trim() || null,
          api_token: jiraApiToken.trim() || null,
          trigger_criteria: criteria,
          poll_interval_seconds: Number(jiraPollInterval),
          default_agent_id: defaultAgentId,
          is_active: isActive,
        })
      } else if (triggerType === 'schedule') {
        saved = await api.createScheduleTrigger({
          integration_name: integrationName.trim(),
          cron_expression: cronExpression.trim(),
          timezone: timezone.trim(),
          payload_template: payloadTemplate,
          trigger_criteria: criteria,
          default_agent_id: defaultAgentId,
          is_active: isActive,
        })
      } else {
        saved = await api.createGitHubTrigger({
          integration_name: integrationName.trim(),
          auth_method: githubAuthMethod,
          repo_owner: repoOwner.trim(),
          repo_name: repoName.trim(),
          installation_id: installationId.trim() || null,
          pat_token: patToken.trim() || null,
          webhook_secret: webhookSecret.trim() || null,
          events: githubEvents,
          branch_filter: branchFilter.trim() || null,
          path_filters: splitList(pathFiltersText),
          author_filter: authorFilter.trim() || null,
          trigger_criteria: criteria,
          default_agent_id: defaultAgentId,
          is_active: isActive,
        })
      }
      onSaved?.(saved)
      onClose()
    } catch (err: unknown) {
      setError(getErrorMessage(err, `Failed to create ${triggerType} trigger`))
    } finally {
      setSaving(false)
    }
  }

  const toggleGitHubEvent = (eventName: string) => {
    setGithubEvents((current) => (
      current.includes(eventName)
        ? current.filter((item) => item !== eventName)
        : [...current, eventName]
    ))
  }

  const testLabel = triggerType === 'schedule' ? 'Preview' : 'Test'

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={config.title}
      size="xl"
      footer={(
        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white disabled:opacity-50"
          >
            Cancel
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || saving}
              className="inline-flex items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
            >
              <PlayIcon size={14} />
              {testing ? `${testLabel}ing...` : testLabel}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSubmit}
              className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40 ${config.button}`}
            >
              {saving ? 'Creating...' : 'Create Trigger'}
            </button>
          </div>
        </div>
      )}
    >
      <div className="space-y-5">
        <div className={`rounded-xl border px-4 py-3 ${config.accent}`}>
          <div className="flex items-start gap-3">
            <Icon size={18} className="mt-0.5 shrink-0" />
            <p className="text-sm">{config.description}</p>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error}
          </div>
        )}
        {testResult && (
          <div className={`rounded-xl border px-4 py-3 text-sm ${
            testResult.tone === 'success'
              ? 'border-green-500/30 bg-green-500/10 text-green-200'
              : testResult.tone === 'error'
              ? 'border-red-500/30 bg-red-500/10 text-red-200'
              : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200'
          }`}>
            {testResult.message}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-white">Trigger Name *</label>
            <input
              type="text"
              value={integrationName}
              onChange={(event) => setIntegrationName(event.target.value)}
              className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
            />
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-medium text-white">Default Agent</label>
            <select
              value={defaultAgentId ?? ''}
              onChange={(event) => setDefaultAgentId(event.target.value ? Number(event.target.value) : null)}
              className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
            >
              <option value="">No default agent</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.contact_name}
                </option>
              ))}
            </select>
            <p className="text-xs text-tsushin-slate">
              {agentsLoading ? 'Loading active agents...' : selectedAgent ? `Wake ${selectedAgent.contact_name} by default.` : 'Optional default agent for wake events.'}
            </p>
          </div>
        </div>

        {triggerType === 'jira' && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Jira Site URL *</label>
              <input
                type="url"
                value={jiraSiteUrl}
                onChange={(event) => setJiraSiteUrl(event.target.value)}
                placeholder="https://acme.atlassian.net"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Project Key</label>
              <input
                type="text"
                value={jiraProjectKey}
                onChange={(event) => setJiraProjectKey(event.target.value.toUpperCase())}
                placeholder="OPS"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <label className="block text-sm font-medium text-white">JQL *</label>
              <textarea
                value={jiraJql}
                onChange={(event) => setJiraJql(event.target.value)}
                rows={3}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Auth Email</label>
              <input
                type="email"
                value={jiraAuthEmail}
                onChange={(event) => setJiraAuthEmail(event.target.value)}
                placeholder="ops@example.com"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">API Token</label>
              <input
                type="password"
                value={jiraApiToken}
                onChange={(event) => setJiraApiToken(event.target.value)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Poll Interval (seconds)</label>
              <input
                type="number"
                min={60}
                max={3600}
                step={60}
                value={jiraPollInterval}
                onChange={(event) => setJiraPollInterval(event.target.value)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
            </div>
          </div>
        )}

        {triggerType === 'schedule' && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Cron Expression *</label>
              <input
                type="text"
                value={cronExpression}
                onChange={(event) => setCronExpression(event.target.value)}
                placeholder="0 * * * *"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-sm text-white placeholder:text-tsushin-slate focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Timezone *</label>
              <input
                type="text"
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
                placeholder="America/Sao_Paulo"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/30"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <label className="block text-sm font-medium text-white">Payload Template</label>
              <textarea
                value={payloadTemplateText}
                onChange={(event) => setPayloadTemplateText(event.target.value)}
                rows={4}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/30"
              />
            </div>
          </div>
        )}

        {triggerType === 'github' && (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Repository Owner *</label>
              <input
                type="text"
                value={repoOwner}
                onChange={(event) => setRepoOwner(event.target.value)}
                placeholder="octo-org"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Repository Name *</label>
              <input
                type="text"
                value={repoName}
                onChange={(event) => setRepoName(event.target.value)}
                placeholder="platform"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Auth Method</label>
              <select
                value={githubAuthMethod}
                onChange={(event) => setGithubAuthMethod(event.target.value as GitHubTriggerAuthMethod)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              >
                <option value="pat">Personal access token</option>
                <option value="app">GitHub App</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">{githubAuthMethod === 'pat' ? 'PAT Token' : 'Installation ID'}</label>
              <input
                type={githubAuthMethod === 'pat' ? 'password' : 'text'}
                value={githubAuthMethod === 'pat' ? patToken : installationId}
                onChange={(event) => githubAuthMethod === 'pat' ? setPatToken(event.target.value) : setInstallationId(event.target.value)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <label className="block text-sm font-medium text-white">Events *</label>
              <div className="flex flex-wrap gap-2">
                {GITHUB_EVENT_OPTIONS.map((eventName) => (
                  <button
                    key={eventName}
                    type="button"
                    onClick={() => toggleGitHubEvent(eventName)}
                    className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                      githubEvents.includes(eventName)
                        ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                        : 'border-tsushin-border text-tsushin-slate hover:text-white'
                    }`}
                  >
                    {eventName.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Webhook Secret</label>
              <input
                type="password"
                value={webhookSecret}
                onChange={(event) => setWebhookSecret(event.target.value)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Branch Filter</label>
              <input
                type="text"
                value={branchFilter}
                onChange={(event) => setBranchFilter(event.target.value)}
                placeholder="main"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Path Filters</label>
              <textarea
                value={pathFiltersText}
                onChange={(event) => setPathFiltersText(event.target.value)}
                rows={3}
                placeholder="frontend/**&#10;backend/api/**"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Author Filter</label>
              <input
                type="text"
                value={authorFilter}
                onChange={(event) => setAuthorFilter(event.target.value)}
                placeholder="octocat"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
          </div>
        )}

        <CriteriaBuilder value={criteriaText} onChange={setCriteriaText} disabled={saving} />

        <label className="flex items-start gap-3 rounded-xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(event) => setIsActive(event.target.checked)}
            className="mt-1 h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-cyan-500 focus:ring-cyan-500"
          />
          <div>
            <div className="text-sm font-medium text-white">{isActive ? 'Enable this trigger immediately' : 'Create it paused'}</div>
            <p className="mt-1 text-xs text-tsushin-slate">Paused triggers keep their configuration but do not emit wake events until resumed.</p>
          </div>
        </label>
      </div>
    </Modal>
  )
}
