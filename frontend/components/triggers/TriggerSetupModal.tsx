'use client'

import { useEffect, useMemo, useState } from 'react'
import type { ComponentType } from 'react'
import Modal from '@/components/ui/Modal'
import { api, type Agent, type GitHubIntegration, type GitHubTrigger, type GitHubTriggerAuthMethod, type JiraIntegration, type JiraIssuePreview, type JiraTrigger, type PRSubmittedAction, type PRSubmittedCriteria, type ScheduleTrigger, type TriggerCriteria, type TriggerKind } from '@/lib/client'
import { CalendarDaysIcon, CodeIcon, GitHubIcon, PlayIcon, type IconProps } from '@/components/ui/icons'
import CriteriaBuilder, { parseCriteriaText, type CriteriaSourceValues } from '@/components/triggers/CriteriaBuilder'
import JiraIssuePreviewList from '@/components/triggers/JiraIssuePreviewList'

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

const PR_SUBMITTED_ACTION_OPTIONS: { value: PRSubmittedAction; label: string; description: string }[] = [
  { value: 'opened', label: 'opened', description: 'New PR raised' },
  { value: 'reopened', label: 'reopened', description: 'Closed PR re-opened' },
  { value: 'synchronize', label: 'synchronize', description: 'New commits pushed to PR head' },
  { value: 'edited', label: 'edited', description: 'PR title/body edited' },
  { value: 'ready_for_review', label: 'ready_for_review', description: 'Draft promoted to ready' },
]

const DEFAULT_PR_SAMPLE_PAYLOAD = JSON.stringify({
  action: 'opened',
  pull_request: {
    number: 42,
    title: 'Add code_repository skill',
    body: 'Adds a generic Code Repository skill backed by GitHub.',
    draft: false,
    base: { ref: 'main' },
    head: { ref: 'feature/code-repo-skill' },
    user: { login: 'octocat' },
  },
}, null, 2)

export default function TriggerSetupModal({ isOpen, triggerType, onClose, onSaved }: Props) {
  const config = KIND_CONFIG[triggerType]
  const Icon = config.Icon
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ tone: 'success' | 'error' | 'info'; message: string } | null>(null)
  const [jiraSampleIssues, setJiraSampleIssues] = useState<JiraIssuePreview[]>([])
  const [jiraIntegrations, setJiraIntegrations] = useState<JiraIntegration[]>([])
  const [jiraIntegrationsLoading, setJiraIntegrationsLoading] = useState(false)

  const [integrationName, setIntegrationName] = useState('')
  const [defaultAgentId, setDefaultAgentId] = useState<number | null>(null)
  const [isActive, setIsActive] = useState(true)
  const [criteriaText, setCriteriaText] = useState('')

  const [jiraIntegrationId, setJiraIntegrationId] = useState<number | null>(null)
  const [jiraProjectKey, setJiraProjectKey] = useState('')
  const [jiraJql, setJiraJql] = useState('project = OPS ORDER BY updated DESC')
  const [jiraPollInterval, setJiraPollInterval] = useState('300')
  const [jiraNotificationRecipient, setJiraNotificationRecipient] = useState('')

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

  // v0.7.0: PR Submitted criteria envelope. The first canonical criteria
  // shape we ship for GitHub triggers — locked to event_type='pull_request'
  // for now (push-based criteria coming later). The user picks a list of
  // PR actions to react to, plus optional branch/path/author filters and
  // title/body substring matchers, then can validate against a sample
  // webhook payload via /api/triggers/github/test-criteria.
  const [prSelectedActions, setPrSelectedActions] = useState<PRSubmittedAction[]>(['opened', 'reopened'])
  const [prDraftOnly, setPrDraftOnly] = useState(false)
  const [prTitleContains, setPrTitleContains] = useState('')
  const [prBodyContains, setPrBodyContains] = useState('')
  const [prSamplePayloadText, setPrSamplePayloadText] = useState('')
  const [prCriteriaResult, setPrCriteriaResult] = useState<{ matched: boolean; message: string } | null>(null)
  const [prCriteriaTesting, setPrCriteriaTesting] = useState(false)
  // v0.7.0: GitHub Hub integrations — let the trigger reuse a shared PAT
  // (stored in Hub > Developer Tools) instead of pasting a fresh one here.
  const [githubIntegrations, setGithubIntegrations] = useState<GitHubIntegration[]>([])
  const [githubIntegrationsLoading, setGithubIntegrationsLoading] = useState(false)
  const [selectedGithubIntegrationId, setSelectedGithubIntegrationId] = useState<number | null>(null)

  useEffect(() => {
    if (!isOpen) return
    setError(null)
    setTestResult(null)
    setJiraSampleIssues([])
    setSaving(false)
    setTesting(false)
    setIntegrationName(triggerType === 'schedule' ? 'Hourly schedule' : triggerType === 'jira' ? 'Jira issue watcher' : 'GitHub repository events')
    setDefaultAgentId(null)
    setIsActive(true)
    setCriteriaText('')
    setJiraIntegrationId(null)
    setJiraProjectKey('')
    setJiraJql('project = OPS ORDER BY updated DESC')
    setJiraPollInterval('300')
    setJiraNotificationRecipient('')
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
    setPrSelectedActions(['opened', 'reopened'])
    setPrDraftOnly(false)
    setPrTitleContains('')
    setPrBodyContains('')
    setPrSamplePayloadText('')
    setPrCriteriaResult(null)
    setPrCriteriaTesting(false)
    setSelectedGithubIntegrationId(null)
    setGithubIntegrations([])

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

    if (triggerType === 'jira') {
      setJiraIntegrationsLoading(true)
      api.listJiraIntegrations()
        .then((list) => {
          if (cancelled) return
          setJiraIntegrations(list)
          const firstActive = list.find((item) => item.is_active) || list[0]
          setJiraIntegrationId(firstActive?.id ?? null)
        })
        .catch(() => {
          if (!cancelled) setJiraIntegrations([])
        })
        .finally(() => {
          if (!cancelled) setJiraIntegrationsLoading(false)
        })
    }

    if (triggerType === 'github') {
      setGithubIntegrationsLoading(true)
      api.listGitHubIntegrations()
        .then((list) => {
          if (cancelled) return
          setGithubIntegrations(list)
          const firstActive = list.find((item) => item.is_active) || list[0]
          if (firstActive) {
            setSelectedGithubIntegrationId(firstActive.id)
            // Pre-fill default owner/repo from the picked Hub connection so
            // the user doesn't have to retype them. They remain editable.
            if (firstActive.default_owner && !repoOwner) setRepoOwner(firstActive.default_owner)
            if (firstActive.default_repo && !repoName) setRepoName(firstActive.default_repo)
          }
        })
        .catch(() => {
          if (!cancelled) setGithubIntegrations([])
        })
        .finally(() => {
          if (!cancelled) setGithubIntegrationsLoading(false)
        })
    }

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, triggerType])

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === defaultAgentId) || null,
    [agents, defaultAgentId],
  )
  const selectedJiraIntegration = useMemo(
    () => jiraIntegrations.find((integration) => integration.id === jiraIntegrationId) || null,
    [jiraIntegrationId, jiraIntegrations],
  )

  const canSubmit = useMemo(() => {
    if (saving || !integrationName.trim()) return false
    if (triggerType === 'jira') {
      const poll = Number(jiraPollInterval)
      return Boolean(jiraIntegrationId && jiraJql.trim() && Number.isFinite(poll) && poll >= 60 && poll <= 3600)
    }
    if (triggerType === 'schedule') {
      return Boolean(cronExpression.trim() && timezone.trim())
    }
    // GitHub: PR Submitted criteria requires at least one selected action.
    return Boolean(
      repoOwner.trim()
      && repoName.trim()
      && githubEvents.length > 0
      && prSelectedActions.length > 0,
    )
  }, [cronExpression, githubEvents.length, integrationName, jiraIntegrationId, jiraJql, jiraPollInterval, prSelectedActions.length, repoName, repoOwner, saving, timezone, triggerType])

  const buildPRSubmittedCriteria = (): PRSubmittedCriteria => ({
    // v0.7.0 release-finishing fix: canonical envelope shape per
    // backend/channels/github/criteria.py validate_pr_criteria. Was using
    // legacy flat-with-event_type shape which made the validator fall
    // through to the generic envelope and 422 on every wizard create.
    criteria_version: 1,
    event: 'pull_request',
    actions: [...prSelectedActions],
    filters: {
      branch_filter: branchFilter.trim() || null,
      path_filters: splitList(pathFiltersText),
      author_filter: authorFilter.trim() || null,
      exclude_drafts: prDraftOnly,
      title_contains: prTitleContains.trim() || null,
      body_contains: prBodyContains.trim() || null,
    },
    ordering: 'oldest_first',
  })

  const runValidation = () => {
    // For GitHub triggers we ship the structured PR Submitted envelope as
    // `trigger_criteria` instead of the free-form CriteriaBuilder JSON.
    // Other trigger kinds keep using the CriteriaBuilder text.
    let criteria: TriggerCriteria | null
    if (triggerType === 'github') {
      criteria = buildPRSubmittedCriteria() as unknown as TriggerCriteria
    } else {
      criteria = parseCriteriaText(criteriaText) as TriggerCriteria | null
    }
    const payloadTemplate = triggerType === 'schedule'
      ? parseJsonObject(payloadTemplateText, 'Payload template')
      : null
    return { criteria, payloadTemplate }
  }

  const togglePRAction = (action: PRSubmittedAction) => {
    setPrSelectedActions((current) => (
      current.includes(action)
        ? current.filter((item) => item !== action)
        : [...current, action]
    ))
  }

  const testPRSubmittedCriteria = async () => {
    setPrCriteriaResult(null)
    setPrCriteriaTesting(true)
    try {
      let samplePayload: Record<string, unknown> | null = null
      const trimmed = prSamplePayloadText.trim()
      if (trimmed) {
        try {
          samplePayload = parseJsonObject(trimmed, 'Sample payload')
        } catch (err) {
          throw err instanceof Error ? err : new Error('Sample payload is not valid JSON')
        }
      }
      const result = await api.testGitHubPRCriteria(buildPRSubmittedCriteria(), samplePayload)
      setPrCriteriaResult({
        matched: result.matched,
        message: result.matched
          ? result.message || 'Sample payload matches the criteria.'
          : result.reason || result.message || result.error || 'Sample payload was rejected.',
      })
    } catch (err) {
      setPrCriteriaResult({ matched: false, message: err instanceof Error ? err.message : 'Failed to test PR criteria' })
    } finally {
      setPrCriteriaTesting(false)
    }
  }

  const handleTest = async () => {
    setError(null)
    setTestResult(null)
    setJiraSampleIssues([])
    setTesting(true)
    try {
      if (triggerType === 'jira') {
        if (!jiraIntegrationId) {
          throw new Error('Select a Jira connection before testing.')
        }
        const result = await api.testSavedJiraIntegrationQuery(jiraIntegrationId, {
          jql: jiraJql.trim(),
          max_results: 5,
        })
        setJiraSampleIssues(result.sample_issues || result.issues || [])
        setTestResult({
          tone: result.success ? 'success' : 'error',
          message: result.success
            ? `Query returned ${result.issue_count ?? result.total ?? 0} issue(s).`
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
          jira_integration_id: jiraIntegrationId,
          project_key: jiraProjectKey.trim() || null,
          jql: jiraJql.trim(),
          trigger_criteria: criteria,
          poll_interval_seconds: Number(jiraPollInterval),
          default_agent_id: defaultAgentId,
          is_active: isActive,
        })
        if (jiraNotificationRecipient.trim()) {
          try {
            await api.createJiraNotificationSubscription(saved.id, {
              recipient_phone: jiraNotificationRecipient.trim(),
            })
          } catch {
            // The trigger is usable even if the optional notifier needs setup on the detail page.
          }
        }
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

  const updateCriteriaSource = (patch: Partial<CriteriaSourceValues>) => {
    if (patch.jiraProjectKey !== undefined) setJiraProjectKey(patch.jiraProjectKey || '')
    if (patch.jiraJql !== undefined) setJiraJql(patch.jiraJql || '')
    if (patch.cronExpression !== undefined) setCronExpression(patch.cronExpression || '')
    if (patch.timezone !== undefined) setTimezone(patch.timezone || '')
    if (patch.payloadTemplateText !== undefined) setPayloadTemplateText(patch.payloadTemplateText || '')
    if (patch.githubEventsText !== undefined) setGithubEvents(splitList(patch.githubEventsText || '') || [])
    if (patch.githubBranchFilter !== undefined) setBranchFilter(patch.githubBranchFilter || '')
    if (patch.githubPathFiltersText !== undefined) setPathFiltersText(patch.githubPathFiltersText || '')
    if (patch.githubAuthorFilter !== undefined) setAuthorFilter(patch.githubAuthorFilter || '')
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
        {triggerType === 'jira' && jiraSampleIssues.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium text-white">Sample issues</div>
            <JiraIssuePreviewList issues={jiraSampleIssues} siteUrl={selectedJiraIntegration?.site_url || ''} />
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
              <label className="block text-sm font-medium text-white">Jira Connection *</label>
              <select
                value={jiraIntegrationId ?? ''}
                onChange={(event) => setJiraIntegrationId(event.target.value ? Number(event.target.value) : null)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              >
                <option value="">{jiraIntegrationsLoading ? 'Loading Jira connections...' : 'Select a Jira connection'}</option>
                {jiraIntegrations.map((integration) => (
                  <option key={integration.id} value={integration.id}>
                    {integration.integration_name || integration.name || `Jira connection #${integration.id}`}
                  </option>
                ))}
              </select>
              <p className="text-xs text-tsushin-slate">
                {selectedJiraIntegration
                  ? `${selectedJiraIntegration.site_url} · ${selectedJiraIntegration.auth_email || 'No auth email reported'}`
                  : 'Add or edit Jira base URL and credentials in Hub > Tool APIs.'}
              </p>
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
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">WhatsApp Notification Recipient</label>
              <input
                type="tel"
                value={jiraNotificationRecipient}
                onChange={(event) => setJiraNotificationRecipient(event.target.value)}
                placeholder="+15551234567"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              />
              <p className="text-xs text-tsushin-slate">Leave blank to configure the managed WhatsApp notifier from the trigger detail page.</p>
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
            <div className="space-y-2 md:col-span-2">
              <label className="block text-sm font-medium text-white">GitHub Connection</label>
              <select
                value={selectedGithubIntegrationId ?? ''}
                onChange={(event) => {
                  const next = event.target.value ? Number(event.target.value) : null
                  setSelectedGithubIntegrationId(next)
                  if (next) {
                    const match = githubIntegrations.find((item) => item.id === next)
                    if (match?.default_owner) setRepoOwner(match.default_owner)
                    if (match?.default_repo) setRepoName(match.default_repo)
                  }
                }}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              >
                <option value="">{githubIntegrationsLoading ? 'Loading GitHub connections...' : 'Use a per-trigger PAT (no Hub connection)'}</option>
                {githubIntegrations.map((integration) => (
                  <option key={integration.id} value={integration.id}>
                    {integration.integration_name || integration.name || `GitHub connection #${integration.id}`}
                    {integration.default_owner && integration.default_repo ? ` — ${integration.default_owner}/${integration.default_repo}` : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-tsushin-slate">
                Pick a shared Hub connection (Hub &gt; Developer Tools &gt; GitHub) or leave blank and paste a PAT below for this trigger only.
              </p>
            </div>
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

            {/* v0.7.0: PR Submitted criteria envelope. The first canonical
                criteria shape we ship; the event_type is locked to
                'pull_request' for now. */}
            <div className="space-y-3 md:col-span-2 rounded-xl border border-violet-500/20 bg-violet-500/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-white">PR Submitted criteria</div>
                  <p className="mt-1 text-xs text-tsushin-slate">
                    The structured envelope the dispatcher matches incoming GitHub webhooks against. Saved as the trigger&apos;s criteria.
                  </p>
                </div>
                <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-violet-200">
                  v0.7.0
                </span>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-tsushin-slate">Event</label>
                  <input
                    type="text"
                    value="Pull Request"
                    readOnly
                    disabled
                    className="w-full cursor-not-allowed rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-tsushin-slate"
                  />
                  <p className="text-[11px] text-tsushin-slate">Locked — the only canonical criteria shipped today. Push criteria coming later.</p>
                </div>
                <div className="space-y-1">
                  <label className="flex items-start gap-2 text-xs font-medium text-tsushin-slate">
                    <input
                      type="checkbox"
                      checked={prDraftOnly}
                      onChange={(event) => setPrDraftOnly(event.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-violet-500 focus:ring-violet-500"
                    />
                    <span>Only non-draft PRs<br /><span className="font-normal text-[11px] text-tsushin-slate">When checked, draft PRs are rejected even if the action matches.</span></span>
                  </label>
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-tsushin-slate">Actions *</label>
                <div className="flex flex-wrap gap-2">
                  {PR_SUBMITTED_ACTION_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => togglePRAction(option.value)}
                      title={option.description}
                      className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                        prSelectedActions.includes(option.value)
                          ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                          : 'border-tsushin-border text-tsushin-slate hover:text-white'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {prSelectedActions.length === 0 && (
                  <p className="text-[11px] text-amber-300">Pick at least one PR action.</p>
                )}
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-tsushin-slate">Title contains</label>
                  <input
                    type="text"
                    value={prTitleContains}
                    onChange={(event) => setPrTitleContains(event.target.value)}
                    placeholder="[security]"
                    className="w-full rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-xs font-medium text-tsushin-slate">Body contains</label>
                  <input
                    type="text"
                    value={prBodyContains}
                    onChange={(event) => setPrBodyContains(event.target.value)}
                    placeholder="closes #"
                    className="w-full rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
                  />
                </div>
              </div>

              <p className="text-[11px] text-tsushin-slate">
                Branch / path / author filters reuse the values entered above — they are part of the same criteria envelope.
              </p>

              <div className="space-y-1">
                <div className="flex items-center justify-between gap-3">
                  <label className="block text-xs font-medium text-tsushin-slate">Sample payload (optional)</label>
                  <button
                    type="button"
                    onClick={() => setPrSamplePayloadText(DEFAULT_PR_SAMPLE_PAYLOAD)}
                    className="text-[11px] text-violet-300 hover:text-white"
                  >
                    Insert example
                  </button>
                </div>
                <textarea
                  value={prSamplePayloadText}
                  onChange={(event) => setPrSamplePayloadText(event.target.value)}
                  rows={5}
                  placeholder="Paste a real GitHub webhook payload here, or click Insert example."
                  className="w-full rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
                />
              </div>

              <div className="flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={testPRSubmittedCriteria}
                  disabled={prCriteriaTesting || prSelectedActions.length === 0}
                  className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {prCriteriaTesting ? 'Testing...' : 'Test against sample payload'}
                </button>
                {prCriteriaResult && (
                  <span className={`text-xs ${prCriteriaResult.matched ? 'text-green-300' : 'text-red-300'}`}>
                    {prCriteriaResult.matched ? 'Matched' : 'Rejected'}
                  </span>
                )}
              </div>
              {prCriteriaResult && (
                <div className={`rounded-lg border px-3 py-2 text-xs ${
                  prCriteriaResult.matched
                    ? 'border-green-500/30 bg-green-500/10 text-green-200'
                    : 'border-red-500/30 bg-red-500/10 text-red-200'
                }`}>
                  {prCriteriaResult.message}
                </div>
              )}
            </div>
          </div>
        )}

        {/* The free-form CriteriaBuilder is for jira/schedule. GitHub now
            uses the structured PR Submitted envelope above, which we ship
            as `trigger_criteria` directly. */}
        {triggerType !== 'github' && (
          <CriteriaBuilder
            kind={triggerType}
            value={criteriaText}
            onChange={setCriteriaText}
            disabled={saving}
            source={{
              jiraProjectKey,
              jiraJql,
              cronExpression,
              timezone,
              payloadTemplateText,
              githubEventsText: githubEvents.join(', '),
              githubBranchFilter: branchFilter,
              githubPathFiltersText: pathFiltersText,
              githubAuthorFilter: authorFilter,
            }}
            onSourceChange={updateCriteriaSource}
          />
        )}

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
