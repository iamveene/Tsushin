'use client'

import {
  type ComponentType,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useState,
} from 'react'
import { useRouter } from 'next/navigation'
import GoogleAppCredentialsStep from '@/components/integrations/GoogleAppCredentialsStep'
import Wizard, { type WizardStep } from '@/components/ui/Wizard'
import {
  api,
  type Agent,
  type EmailTrigger,
  type GitHubIntegration,
  type GitHubTrigger,
  type JiraIntegration,
  type JiraIssuePreview,
  type JiraTrigger,
  type PRSubmittedAction,
  type PRSubmittedCriteria,
  type TriggerCatalogEntry,
  type TriggerCriteria,
  type TriggerRecapConfig,
  type WebhookIntegration,
  type WebhookIntegrationCreate,
  type WebhookIntegrationCreateResponse,
} from '@/lib/client'
import MemoryRecapStep, { DEFAULT_RECAP_CONFIG } from '@/components/triggers/MemoryRecapStep'
import {
  buildCriteriaTemplate,
  emailSourceFromSearchQuery,
  parseCriteriaText,
} from '@/components/triggers/CriteriaBuilder'
import CriteriaBuilder from '@/components/triggers/CriteriaBuilder'
import JiraIssuePreviewList from '@/components/triggers/JiraIssuePreviewList'
import useGmailOAuthPoller from '@/hooks/useGmailOAuthPoller'
import {
  CodeIcon,
  EnvelopeIcon,
  GitHubIcon,
  WebhookIcon,
  type IconProps,
} from '@/components/ui/icons'

export type TriggerId = 'email' | 'webhook' | 'jira' | 'github'

export type SavedTriggerAny =
  | EmailTrigger
  | JiraTrigger
  | GitHubTrigger
  | WebhookIntegration

interface Props {
  isOpen: boolean
  onClose: () => void
  onCreated?: (kind: TriggerId, triggerId: number, flowId: number | null) => void
  /** Optional pre-selected kind (e.g., when launched from a kind-specific entry). */
  initialKind?: TriggerId | null
}

// The Memory Recap step is only included when `case_memory_enabled` is true on
// the backend. When the flag is off the step is dropped from the visible step
// list AND skipped during navigation (step 3 → step 5) — it's not just
// disabled, it's invisible. The numeric step indices (1..5) are kept stable
// across both shapes so existing setStep(N) call-sites stay correct; we just
// route around step 4 when the flag is off.
const WIZARD_STEPS_WITH_RECAP: WizardStep[] = [
  { id: 'kind', label: 'Trigger', description: 'Choose the event source.' },
  { id: 'source', label: 'Source', description: 'Connect credentials or configure the source.' },
  { id: 'criteria', label: 'Criteria', description: 'Define what events to match.' },
  { id: 'memory_recap', label: 'Memory Recap', description: 'Configure recall of past similar cases.' },
  { id: 'confirm', label: 'Confirm', description: 'Review, save, and open the auto-flow.' },
]

const WIZARD_STEPS_WITHOUT_RECAP: WizardStep[] = [
  { id: 'kind', label: 'Trigger', description: 'Choose the event source.' },
  { id: 'source', label: 'Source', description: 'Connect credentials or configure the source.' },
  { id: 'criteria', label: 'Criteria', description: 'Define what events to match.' },
  { id: 'confirm', label: 'Confirm', description: 'Review, save, and open the auto-flow.' },
]

function getWizardSteps(caseMemoryEnabled: boolean): WizardStep[] {
  return caseMemoryEnabled ? WIZARD_STEPS_WITH_RECAP : WIZARD_STEPS_WITHOUT_RECAP
}

interface KindEntry {
  id: TriggerId
  display_name: string
  description: string
  setup_hint: string
  Icon: ComponentType<IconProps>
  iconClass: string
  iconBg: string
}

const KIND_CATALOG: KindEntry[] = [
  {
    id: 'email',
    display_name: 'Email',
    description: 'Watch Gmail inbox activity and wake agents from matching messages.',
    setup_hint: 'Reuses the tenant Gmail OAuth integrations under Hub → Productivity.',
    Icon: EnvelopeIcon,
    iconClass: 'text-emerald-300',
    iconBg: 'bg-red-500/10',
  },
  {
    id: 'webhook',
    display_name: 'Webhook',
    description: 'Receive signed external events and optionally call back a customer system.',
    setup_hint: 'Generates a unique inbound URL and HMAC secret for the trigger.',
    Icon: WebhookIcon,
    iconClass: 'text-cyan-300',
    iconBg: 'bg-cyan-500/10',
  },
  {
    id: 'jira',
    display_name: 'Jira',
    description: 'Watch Jira issues with JQL and wake agents from matching issues.',
    setup_hint: 'Select a Hub Jira connection, or create one from the source step.',
    Icon: CodeIcon,
    iconClass: 'text-blue-300',
    iconBg: 'bg-blue-500/10',
  },
  {
    id: 'github',
    display_name: 'GitHub',
    description: 'Receive signed repository events and wake agents from matching activity.',
    setup_hint: 'Select a Hub GitHub connection, then wire the webhook secret shown after save.',
    Icon: GitHubIcon,
    iconClass: 'text-violet-300',
    iconBg: 'bg-violet-500/10',
  },
]

type WizardTone = 'default' | 'gmail' | 'whatsapp' | 'mcp'
const KIND_TONE: Record<TriggerId, WizardTone> = {
  email: 'gmail',
  webhook: 'default',
  jira: 'default',
  github: 'default',
}

const KIND_ACCENT_BUTTON: Record<TriggerId, string> = {
  email: 'bg-red-600 hover:bg-red-500 text-white',
  webhook: 'bg-cyan-600 hover:bg-cyan-500 text-white',
  jira: 'bg-blue-600 hover:bg-blue-500 text-white',
  github: 'bg-violet-600 hover:bg-violet-500 text-white',
}

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

function gmailCapabilityLabel(integration: { can_send: boolean; can_draft?: boolean }): string {
  if (integration.can_send && integration.can_draft) return 'Read + send/draft'
  if (integration.can_send) return 'Read + send/reply'
  return 'Read-only'
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

const GITHUB_EVENT_OPTIONS = ['push', 'pull_request', 'issues', 'issue_comment', 'release', 'workflow_run']

export default function TriggerCreationWizard({
  isOpen,
  onClose,
  onCreated,
  initialKind = null,
}: Props) {
  const router = useRouter()

  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1)
  const [kind, setKind] = useState<TriggerId | null>(initialKind)
  const [savedTrigger, setSavedTrigger] = useState<SavedTriggerAny | null>(null)
  const [autoFlowId, setAutoFlowId] = useState<number | null>(null)
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null)
  const [secretCopied, setSecretCopied] = useState(false)

  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'success'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)

  const [catalog, setCatalog] = useState<KindEntry[]>(KIND_CATALOG)
  const [catalogLoadError, setCatalogLoadError] = useState<string | null>(null)

  // Universal fields
  const [defaultAgentId, setDefaultAgentId] = useState<number | null>(null)
  const [isActive, setIsActive] = useState(true)
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoaded, setAgentsLoaded] = useState(false)

  // v0.7.x Wave 2-D — per-trigger Memory Recap config. Persisted only when
  // `recapConfig.enabled === true`; the backend leaves the row absent
  // otherwise, so we don't fire the PUT in that branch.
  const [recapConfig, setRecapConfig] = useState<TriggerRecapConfig>(DEFAULT_RECAP_CONFIG)
  // Resolved from `GET /api/feature-flags`. Defaults to `false` until the
  // response arrives so we don't briefly show a step that may then disappear;
  // on 404/error the client returns `{ case_memory_enabled: true }` so older
  // backends keep the previous permissive behavior.
  const [caseMemoryEnabled, setCaseMemoryEnabled] = useState(false)

  // Email-specific state
  const [emailIntegrationId, setEmailIntegrationId] = useState<number | null>(null)
  const [emailIntegrationName, setEmailIntegrationName] = useState('')
  const [emailSearchQuery, setEmailSearchQuery] = useState('')
  const [emailPollIntervalSeconds, setEmailPollIntervalSeconds] = useState('60')
  const [emailCredentialsOk, setEmailCredentialsOk] = useState(false)

  // Webhook-specific state
  const [webhookName, setWebhookName] = useState('')
  const [webhookCallbackUrl, setWebhookCallbackUrl] = useState('')
  const [webhookCallbackEnabled, setWebhookCallbackEnabled] = useState(false)
  const [webhookIpAllowlistText, setWebhookIpAllowlistText] = useState('')
  const [webhookRateLimitRpm, setWebhookRateLimitRpm] = useState('60')
  const [webhookCriteriaText, setWebhookCriteriaText] = useState('')

  // Jira-specific state
  const [jiraIntegrationId, setJiraIntegrationId] = useState<number | null>(null)
  const [jiraIntegrations, setJiraIntegrations] = useState<JiraIntegration[]>([])
  const [jiraIntegrationsLoading, setJiraIntegrationsLoading] = useState(false)
  const [jiraIntegrationName, setJiraIntegrationName] = useState('Jira issue watcher')
  const [jiraProjectKey, setJiraProjectKey] = useState('')
  const [jiraJql, setJiraJql] = useState('project = OPS ORDER BY updated DESC')
  const [jiraPollInterval, setJiraPollInterval] = useState('300')
  const [jiraCriteriaText, setJiraCriteriaText] = useState('')
  const [jiraSampleIssues, setJiraSampleIssues] = useState<JiraIssuePreview[]>([])
  const [jiraTesting, setJiraTesting] = useState(false)
  const [jiraTestResult, setJiraTestResult] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  // GitHub-specific state — v0.7.0-fix Phase 3: integration linkage required;
  // no per-trigger credentials, auth-method toggle, installation id, or
  // per-trigger test-connection.
  const [githubIntegrationName, setGithubIntegrationName] = useState('GitHub repository events')
  const [githubIntegrations, setGithubIntegrations] = useState<GitHubIntegration[]>([])
  const [githubIntegrationsLoading, setGithubIntegrationsLoading] = useState(false)
  const [selectedGithubIntegrationId, setSelectedGithubIntegrationId] = useState<number | null>(null)
  const [repoOwner, setRepoOwner] = useState('')
  const [repoName, setRepoName] = useState('')
  const [githubWebhookSecret, setGithubWebhookSecret] = useState('')
  const [githubEvents, setGithubEvents] = useState<string[]>(['push', 'pull_request'])
  const [branchFilter, setBranchFilter] = useState('')
  const [pathFiltersText, setPathFiltersText] = useState('')
  const [authorFilter, setAuthorFilter] = useState('')
  // PR Submitted criteria envelope (verbatim from TriggerSetupModal)
  const [prSelectedActions, setPrSelectedActions] = useState<PRSubmittedAction[]>(['opened', 'reopened'])
  const [prDraftOnly, setPrDraftOnly] = useState(false)
  const [prTitleContains, setPrTitleContains] = useState('')
  const [prBodyContains, setPrBodyContains] = useState('')
  const [prSamplePayloadText, setPrSamplePayloadText] = useState('')
  const [prCriteriaResult, setPrCriteriaResult] = useState<{ matched: boolean; message: string } | null>(null)
  const [prCriteriaTesting, setPrCriteriaTesting] = useState(false)

  // Reset state every time the wizard re-opens.
  useEffect(() => {
    if (!isOpen) return
    setStep(initialKind ? 2 : 1)
    setKind(initialKind)
    setSavedTrigger(null)
    setAutoFlowId(null)
    setWebhookSecret(null)
    setSecretCopied(false)
    setSaveState('idle')
    setSaveError(null)
    setDefaultAgentId(null)
    setIsActive(true)

    setEmailIntegrationId(null)
    setEmailIntegrationName('')
    setEmailSearchQuery('')
    setEmailPollIntervalSeconds('60')
    setEmailCredentialsOk(false)

    setWebhookName('')
    setWebhookCallbackUrl('')
    setWebhookCallbackEnabled(false)
    setWebhookIpAllowlistText('')
    setWebhookRateLimitRpm('60')
    setWebhookCriteriaText('')

    setJiraIntegrationId(null)
    setJiraIntegrationName('Jira issue watcher')
    setJiraProjectKey('')
    setJiraJql('project = OPS ORDER BY updated DESC')
    setJiraPollInterval('300')
    setJiraCriteriaText('')
    setJiraSampleIssues([])
    setJiraTesting(false)
    setJiraTestResult(null)

    setGithubIntegrationName('GitHub repository events')
    setSelectedGithubIntegrationId(null)
    setRepoOwner('')
    setRepoName('')
    setGithubWebhookSecret('')
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

    setRecapConfig(DEFAULT_RECAP_CONFIG)
  }, [initialKind, isOpen])

  // Pull tenant feature flags whenever the wizard opens. The Memory Recap
  // step renders conditionally on `case_memory_enabled`; when the backend
  // route is missing we get `{ case_memory_enabled: true }` from the client
  // so older deployments keep showing the step.
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    api.getFeatureFlags()
      .then((flags) => {
        if (cancelled) return
        setCaseMemoryEnabled(!!flags.case_memory_enabled)
      })
      .catch(() => {
        // Defensive: getFeatureFlags already swallows errors, but keep a
        // local catch to avoid breaking the wizard if the helper changes.
        if (!cancelled) setCaseMemoryEnabled(true)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  // The visible step list adapts to whether case-memory is enabled. When
  // off, the Memory Recap step is omitted and step navigation skips
  // straight from Criteria (step 3) to Confirm (step 5).
  const wizardSteps = getWizardSteps(caseMemoryEnabled)

  // Defensive: if the flags resolve to off AFTER the user already
  // advanced to step 4, route them forward to step 5 so they don't see
  // an invisible step. Won't fire in the common path (forward navigation
  // already skips step 4 when the flag is off).
  useEffect(() => {
    if (step === 4 && !caseMemoryEnabled) {
      setStep(5)
    }
  }, [step, caseMemoryEnabled])

  // Pull live trigger catalog descriptions when the wizard opens.
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    api.getTriggerCatalog()
      .then((list) => {
        if (cancelled || !Array.isArray(list) || list.length === 0) return
        const liveById = new Map<string, TriggerCatalogEntry>(list.map((entry) => [entry.id, entry]))
        setCatalog(
          KIND_CATALOG.map((fallback) => {
            const live = liveById.get(fallback.id)
            return live
              ? {
                  ...fallback,
                  display_name: live.display_name || fallback.display_name,
                  description: live.description || fallback.description,
                  setup_hint: live.setup_hint || fallback.setup_hint,
                }
              : fallback
          }),
        )
      })
      .catch((err) => {
        if (!cancelled) setCatalogLoadError(err?.message || 'Could not load live trigger catalog')
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  // Lazy-load agents the first time the user reaches the Notification or
  // Source step (both kinds may pick a default agent).
  useEffect(() => {
    if (!isOpen || agentsLoaded || step < 2) return
    let cancelled = false
    api.getAgents(true)
      .then((list) => {
        if (cancelled) return
        setAgents(list)
        setAgentsLoaded(true)
      })
      .catch(() => {
        if (!cancelled) setAgentsLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [agentsLoaded, isOpen, step])

  const gmailPoller = useGmailOAuthPoller({
    enabled: isOpen && kind === 'email',
    onNewIntegration: (integration) => {
      setEmailIntegrationId(integration.id)
      setEmailIntegrationName((current) => current.trim() || `Inbox: ${integration.email_address}`)
    },
  })

  // Fetch Jira integrations the first time the user lands on the Jira source step.
  const [jiraIntegrationsFetched, setJiraIntegrationsFetched] = useState(false)
  useEffect(() => {
    if (!isOpen) {
      setJiraIntegrationsFetched(false)
      return
    }
    if (kind !== 'jira' || step < 2 || jiraIntegrationsFetched) return
    let cancelled = false
    setJiraIntegrationsLoading(true)
    api.listJiraIntegrations()
      .then((list) => {
        if (cancelled) return
        setJiraIntegrations(list)
        const firstActive = list.find((item) => item.is_active) || list[0]
        if (firstActive) setJiraIntegrationId((current) => current ?? firstActive.id)
        setJiraIntegrationsFetched(true)
      })
      .catch(() => {
        if (!cancelled) {
          setJiraIntegrations([])
          setJiraIntegrationsFetched(true)
        }
      })
      .finally(() => {
        if (!cancelled) setJiraIntegrationsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, jiraIntegrationsFetched, kind, step])

  // Fetch GitHub integrations the first time the user lands on the GitHub source step.
  const [githubIntegrationsFetched, setGithubIntegrationsFetched] = useState(false)
  useEffect(() => {
    if (!isOpen) {
      setGithubIntegrationsFetched(false)
      return
    }
    if (kind !== 'github' || step < 2 || githubIntegrationsFetched) return
    let cancelled = false
    setGithubIntegrationsLoading(true)
    api.listGitHubIntegrations()
      .then((list) => {
        if (cancelled) return
        setGithubIntegrations(list)
        const firstActive = list.find((item) => item.is_active) || list[0]
        if (firstActive) {
          setSelectedGithubIntegrationId((current) => current ?? firstActive.id)
          if (firstActive.default_owner) setRepoOwner((current) => current || firstActive.default_owner || '')
          if (firstActive.default_repo) setRepoName((current) => current || firstActive.default_repo || '')
        }
        setGithubIntegrationsFetched(true)
      })
      .catch(() => {
        if (!cancelled) {
          setGithubIntegrations([])
          setGithubIntegrationsFetched(true)
        }
      })
      .finally(() => {
        if (!cancelled) setGithubIntegrationsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [githubIntegrationsFetched, isOpen, kind, step])

  const tone: WizardTone = kind ? KIND_TONE[kind] : 'default'
  const accentButtonClass = kind
    ? KIND_ACCENT_BUTTON[kind]
    : 'bg-tsushin-accent text-[#051218] hover:opacity-90'

  const selectedGmailAccount = useMemo(
    () => gmailPoller.integrations.find((entry) => entry.id === emailIntegrationId) || null,
    [emailIntegrationId, gmailPoller.integrations],
  )

  const emailPollValue = Number(emailPollIntervalSeconds)
  const emailPollIntervalValid =
    Number.isInteger(emailPollValue) && emailPollValue >= 30 && emailPollValue <= 3600

  const jiraPollValue = Number(jiraPollInterval)
  const jiraPollIntervalValid =
    Number.isFinite(jiraPollValue) && jiraPollValue >= 60 && jiraPollValue <= 3600

  const sourceValid = useMemo(() => {
    if (!kind) return false
    if (kind === 'email') {
      return Boolean(
        emailIntegrationId &&
          emailCredentialsOk &&
          emailIntegrationName.trim() &&
          emailPollIntervalValid,
      )
    }
    if (kind === 'webhook') {
      return webhookName.trim().length > 0
    }
    if (kind === 'jira') {
      return Boolean(
        jiraIntegrationId &&
          jiraIntegrationName.trim() &&
          jiraJql.trim() &&
          jiraPollIntervalValid,
      )
    }
    if (kind === 'github') {
      return Boolean(
        selectedGithubIntegrationId &&
          githubIntegrationName.trim() &&
          repoOwner.trim() &&
          repoName.trim() &&
          githubEvents.length > 0,
      )
    }
    return false
  }, [
    emailCredentialsOk,
    emailIntegrationId,
    emailIntegrationName,
    emailPollIntervalValid,
    githubEvents.length,
    githubIntegrationName,
    jiraIntegrationId,
    jiraIntegrationName,
    jiraJql,
    jiraPollIntervalValid,
    kind,
    repoName,
    repoOwner,
    selectedGithubIntegrationId,
    webhookName,
  ])

  const criteriaValid = useMemo(() => {
    if (!kind) return false
    if (kind === 'github') {
      return prSelectedActions.length > 0
    }
    return true
  }, [kind, prSelectedActions.length])

  const handleClose = useCallback(() => {
    if (saveState === 'saving') return
    onClose()
  }, [onClose, saveState])

  const handleOpenFlowEditor = useCallback(() => {
    if (!autoFlowId) return
    onClose()
    router.push(`/flows?edit=${autoFlowId}`)
  }, [autoFlowId, onClose, router])

  const handleCopySecret = useCallback(async () => {
    if (!webhookSecret) return
    try {
      await navigator.clipboard.writeText(webhookSecret)
      setSecretCopied(true)
      setTimeout(() => setSecretCopied(false), 2000)
    } catch {
      // best-effort: clipboard may be denied
    }
  }, [webhookSecret])

  const handleJiraTestQuery = useCallback(async () => {
    if (!jiraIntegrationId || !jiraJql.trim()) return
    setJiraTestResult(null)
    setJiraSampleIssues([])
    setJiraTesting(true)
    try {
      const result = await api.testSavedJiraIntegrationQuery(jiraIntegrationId, {
        jql: jiraJql.trim(),
        max_results: 5,
      })
      setJiraSampleIssues(result.sample_issues || result.issues || [])
      setJiraTestResult({
        tone: result.success ? 'success' : 'error',
        message: result.success
          ? `Query returned ${result.issue_count ?? result.total ?? 0} issue(s).`
          : result.error || result.message || 'Jira query test failed',
      })
    } catch (error: unknown) {
      setJiraTestResult({ tone: 'error', message: getErrorMessage(error, 'Jira query test failed') })
    } finally {
      setJiraTesting(false)
    }
  }, [jiraIntegrationId, jiraJql])

  const buildPRSubmittedCriteria = useCallback((): PRSubmittedCriteria => ({
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
  }), [authorFilter, branchFilter, pathFiltersText, prBodyContains, prDraftOnly, prSelectedActions, prTitleContains])

  const handleTestPRSubmittedCriteria = useCallback(async () => {
    setPrCriteriaResult(null)
    setPrCriteriaTesting(true)
    try {
      let samplePayload: Record<string, unknown> | null = null
      const trimmed = prSamplePayloadText.trim()
      if (trimmed) {
        try {
          const parsed = JSON.parse(trimmed)
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            throw new Error('Sample payload must be a JSON object')
          }
          samplePayload = parsed as Record<string, unknown>
        } catch (error: unknown) {
          throw new Error(`Sample payload is not valid JSON: ${getErrorMessage(error, 'parse error')}`)
        }
      }
      const result = await api.testGitHubPRCriteria(buildPRSubmittedCriteria(), samplePayload)
      setPrCriteriaResult({
        matched: result.matched,
        message: result.matched
          ? result.message || 'Sample payload matches the criteria.'
          : result.reason || result.message || result.error || 'Sample payload was rejected.',
      })
    } catch (error: unknown) {
      setPrCriteriaResult({ matched: false, message: getErrorMessage(error, 'Failed to test PR criteria') })
    } finally {
      setPrCriteriaTesting(false)
    }
  }, [buildPRSubmittedCriteria, prSamplePayloadText])

  const handleSave = useCallback(async () => {
    if (!kind) return
    setSaveError(null)
    setSaveState('saving')

    // v0.7.x Wave 2-D — best-effort persistence of the per-trigger Memory
    // Recap config. Failures here must NOT block trigger creation; we surface
    // the error via `saveError` after the success status flip so the operator
    // sees both signals (trigger created, recap save failed).
    const persistRecapIfNeeded = async (
      kindForRecap: 'email' | 'webhook' | 'jira' | 'github',
      triggerId: number,
    ): Promise<string | null> => {
      if (!recapConfig.enabled) return null
      try {
        await api.putTriggerRecapConfig(kindForRecap, triggerId, recapConfig)
        return null
      } catch (err: unknown) {
        return getErrorMessage(err, 'Failed to save Memory Recap config')
      }
    }

    try {
      switch (kind) {
        case 'email': {
          if (!emailIntegrationId) {
            throw new Error('Pick a Gmail account before saving.')
          }
          if (!emailIntegrationName.trim()) {
            throw new Error('Trigger name is required.')
          }
          if (!emailPollIntervalValid) {
            throw new Error('Poll interval must be between 30 and 3600 seconds.')
          }
          const trigger_criteria = buildCriteriaTemplate(
            'email',
            emailSourceFromSearchQuery(emailSearchQuery),
          )
          const result = await api.createEmailTrigger({
            integration_name: emailIntegrationName.trim(),
            gmail_integration_id: emailIntegrationId,
            default_agent_id: defaultAgentId,
            search_query: emailSearchQuery.trim() || null,
            trigger_criteria,
            poll_interval_seconds: emailPollValue,
            is_active: isActive,
          })
          const flowId = result.auto_flow_id ?? null
          const recapErr = await persistRecapIfNeeded('email', result.id)
          setSavedTrigger(result)
          setAutoFlowId(flowId)
          setSaveState('success')
          if (recapErr) setSaveError(`Trigger created, but Memory Recap save failed: ${recapErr}`)
          onCreated?.('email', result.id, flowId)
          return
        }

        case 'webhook': {
          if (!webhookName.trim()) {
            throw new Error('Integration name is required.')
          }
          let parsedCriteria: TriggerCriteria | null = null
          if (webhookCriteriaText.trim()) {
            try {
              parsedCriteria = parseCriteriaText(webhookCriteriaText)
            } catch (error: unknown) {
              throw new Error(`Invalid criteria JSON: ${getErrorMessage(error, 'parse error')}`)
            }
          }
          const ipAllowlist = webhookIpAllowlistText
            .split(/[\n,]/)
            .map((line) => line.trim())
            .filter(Boolean)
          const rateLimitValue = Number(webhookRateLimitRpm)
          const payload: WebhookIntegrationCreate = {
            integration_name: webhookName.trim(),
            callback_url: webhookCallbackUrl.trim() || null,
            callback_enabled: webhookCallbackEnabled,
            ip_allowlist: ipAllowlist.length > 0 ? ipAllowlist : null,
            rate_limit_rpm: Number.isFinite(rateLimitValue) && rateLimitValue > 0 ? rateLimitValue : 60,
            default_agent_id: defaultAgentId,
            trigger_criteria: parsedCriteria,
          }
          const result: WebhookIntegrationCreateResponse = await api.createWebhookIntegration(payload)
          const flowId = result.integration.auto_flow_id ?? null
          const recapErr = await persistRecapIfNeeded('webhook', result.integration.id)
          setSavedTrigger(result.integration)
          setWebhookSecret(result.api_secret)
          setAutoFlowId(flowId)
          setSaveState('success')
          if (recapErr) setSaveError(`Trigger created, but Memory Recap save failed: ${recapErr}`)
          onCreated?.('webhook', result.integration.id, flowId)
          return
        }

        case 'jira': {
          if (!jiraIntegrationId) {
            throw new Error('Pick a Jira connection before saving.')
          }
          if (!jiraIntegrationName.trim()) {
            throw new Error('Trigger name is required.')
          }
          if (!jiraJql.trim()) {
            throw new Error('JQL is required.')
          }
          if (!jiraPollIntervalValid) {
            throw new Error('Poll interval must be between 60 and 3600 seconds.')
          }
          let parsedCriteria: TriggerCriteria | null = null
          if (jiraCriteriaText.trim()) {
            try {
              parsedCriteria = parseCriteriaText(jiraCriteriaText)
            } catch (error: unknown) {
              throw new Error(`Invalid criteria JSON: ${getErrorMessage(error, 'parse error')}`)
            }
          }
          const result = await api.createJiraTrigger({
            integration_name: jiraIntegrationName.trim(),
            jira_integration_id: jiraIntegrationId,
            project_key: jiraProjectKey.trim() || null,
            jql: jiraJql.trim(),
            trigger_criteria: parsedCriteria,
            poll_interval_seconds: jiraPollValue,
            default_agent_id: defaultAgentId,
            is_active: isActive,
          })
          const flowId = result.auto_flow_id ?? null
          const recapErr = await persistRecapIfNeeded('jira', result.id)
          setSavedTrigger(result)
          setAutoFlowId(flowId)
          setSaveState('success')
          if (recapErr) setSaveError(`Trigger created, but Memory Recap save failed: ${recapErr}`)
          onCreated?.('jira', result.id, flowId)
          return
        }

        case 'github': {
          if (!githubIntegrationName.trim()) {
            throw new Error('Trigger name is required.')
          }
          if (!selectedGithubIntegrationId) {
            throw new Error('Pick a Hub GitHub integration to link this trigger to.')
          }
          if (!repoOwner.trim() || !repoName.trim()) {
            throw new Error('Repository owner and name are required.')
          }
          if (githubEvents.length === 0) {
            throw new Error('Pick at least one GitHub event.')
          }
          if (prSelectedActions.length === 0) {
            throw new Error('Pick at least one PR Submitted action.')
          }
          const criteria = buildPRSubmittedCriteria() as unknown as TriggerCriteria
          const result = await api.createGitHubTrigger({
            integration_name: githubIntegrationName.trim(),
            github_integration_id: selectedGithubIntegrationId,
            repo_owner: repoOwner.trim(),
            repo_name: repoName.trim(),
            webhook_secret: githubWebhookSecret.trim() || null,
            events: githubEvents,
            branch_filter: branchFilter.trim() || null,
            path_filters: splitList(pathFiltersText),
            author_filter: authorFilter.trim() || null,
            trigger_criteria: criteria,
            default_agent_id: defaultAgentId,
            is_active: isActive,
          })
          const flowId = result.auto_flow_id ?? null
          const recapErr = await persistRecapIfNeeded('github', result.id)
          setSavedTrigger(result)
          setAutoFlowId(flowId)
          setSaveState('success')
          if (recapErr) setSaveError(`Trigger created, but Memory Recap save failed: ${recapErr}`)
          onCreated?.('github', result.id, flowId)
          return
        }
      }
    } catch (error: unknown) {
      setSaveState('idle')
      setSaveError(getErrorMessage(error, 'Failed to save trigger.'))
    }
  }, [
    authorFilter,
    branchFilter,
    buildPRSubmittedCriteria,
    defaultAgentId,
    emailIntegrationId,
    emailIntegrationName,
    emailPollIntervalValid,
    emailPollValue,
    emailSearchQuery,
    githubEvents,
    githubIntegrationName,
    githubWebhookSecret,
    isActive,
    jiraCriteriaText,
    jiraIntegrationId,
    jiraIntegrationName,
    jiraJql,
    jiraPollIntervalValid,
    jiraPollValue,
    jiraProjectKey,
    kind,
    onCreated,
    pathFiltersText,
    prSelectedActions.length,
    recapConfig,
    repoName,
    repoOwner,
    selectedGithubIntegrationId,
    webhookCallbackEnabled,
    webhookCallbackUrl,
    webhookCriteriaText,
    webhookIpAllowlistText,
    webhookName,
    webhookRateLimitRpm,
  ])

  // ---------------------------------------------------------------- footer
  const renderFooter = (content: ReactNode) => (
    <div className="flex flex-wrap items-center justify-between gap-3">{content}</div>
  )

  // ---------------------------------------------------------------- step 1
  if (step === 1) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title="Create Trigger"
        steps={wizardSteps}
        currentStep={1}
        tone={tone}
        stepTitle="Pick a trigger type"
        stepDescription="Triggers wake agents from events outside regular chat channels. Pick the source, then walk through the unified setup."
        footer={renderFooter(
          <>
            <button
              type="button"
              onClick={handleClose}
              className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => kind && setStep(2)}
              disabled={!kind}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-40 ${accentButtonClass}`}
            >
              Continue to Setup
            </button>
          </>,
        )}
      >
        <div className="space-y-5">
          {catalogLoadError && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              Using offline trigger catalog — {catalogLoadError}
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2" role="radiogroup" aria-label="Trigger type">
            {catalog.map((entry) => {
              const selected = kind === entry.id
              const Icon = entry.Icon
              return (
                <button
                  key={entry.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => setKind(entry.id)}
                  className={`rounded-2xl border p-4 text-left transition-all ${
                    selected
                      ? 'border-tsushin-accent/50 bg-tsushin-accent/10'
                      : 'border-tsushin-border/70 bg-tsushin-slate/5 hover:bg-tsushin-slate/10'
                  }`}
                >
                  <div className="mb-3 flex items-center gap-3">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${entry.iconBg}`}>
                      <Icon size={18} className={entry.iconClass} />
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold text-white">{entry.display_name}</div>
                      <p className="mt-1 text-xs text-tsushin-slate">{entry.description}</p>
                    </div>
                  </div>
                  <p className="text-[11px] text-tsushin-slate/80">{entry.setup_hint}</p>
                </button>
              )
            })}
          </div>
        </div>
      </Wizard>
    )
  }

  // ---------------------------------------------------------------- step 2 (Source)
  if (step === 2 && kind) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title="Create Trigger"
        steps={wizardSteps}
        currentStep={2}
        tone={tone}
        stepTitle={sourceStepTitle(kind)}
        stepDescription={sourceStepDescription(kind)}
        footer={renderFooter(
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Discard
              </button>
            </div>
            <button
              type="button"
              onClick={() => setStep(3)}
              disabled={!sourceValid}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-40 ${accentButtonClass}`}
            >
              Continue to Criteria
            </button>
          </>,
        )}
      >
        {kind === 'email' && (
          <EmailSourceBody
            credentialsOk={emailCredentialsOk}
            onCredentialsReady={() => setEmailCredentialsOk(true)}
            integrations={gmailPoller.integrations}
            integrationsLoading={gmailPoller.integrationsLoading}
            popupOpen={gmailPoller.popupOpen}
            popupError={gmailPoller.popupError}
            onConnectNew={gmailPoller.startAuthorization}
            selectedIntegrationId={emailIntegrationId}
            onSelectIntegration={(id) => {
              setEmailIntegrationId(id)
              const match = gmailPoller.integrations.find((entry) => entry.id === id)
              if (match) {
                setEmailIntegrationName((current) => current.trim() || `Inbox: ${match.email_address}`)
              }
            }}
            integrationName={emailIntegrationName}
            onIntegrationNameChange={setEmailIntegrationName}
            pollIntervalSeconds={emailPollIntervalSeconds}
            onPollIntervalChange={setEmailPollIntervalSeconds}
            pollIntervalValid={emailPollIntervalValid}
            agents={agents}
            defaultAgentId={defaultAgentId}
            onDefaultAgentChange={setDefaultAgentId}
            isActive={isActive}
            onIsActiveChange={setIsActive}
          />
        )}

        {kind === 'webhook' && (
          <WebhookSourceBody
            integrationName={webhookName}
            onIntegrationNameChange={setWebhookName}
            callbackUrl={webhookCallbackUrl}
            onCallbackUrlChange={setWebhookCallbackUrl}
            callbackEnabled={webhookCallbackEnabled}
            onCallbackEnabledChange={setWebhookCallbackEnabled}
            ipAllowlistText={webhookIpAllowlistText}
            onIpAllowlistChange={setWebhookIpAllowlistText}
            rateLimitRpm={webhookRateLimitRpm}
            onRateLimitChange={setWebhookRateLimitRpm}
            agents={agents}
            defaultAgentId={defaultAgentId}
            onDefaultAgentChange={setDefaultAgentId}
            isActive={isActive}
            onIsActiveChange={setIsActive}
          />
        )}

        {kind === 'jira' && (
          <JiraSourceBody
            integrations={jiraIntegrations}
            integrationsLoading={jiraIntegrationsLoading}
            integrationId={jiraIntegrationId}
            onIntegrationIdChange={setJiraIntegrationId}
            integrationName={jiraIntegrationName}
            onIntegrationNameChange={setJiraIntegrationName}
            projectKey={jiraProjectKey}
            onProjectKeyChange={setJiraProjectKey}
            jql={jiraJql}
            onJqlChange={setJiraJql}
            pollInterval={jiraPollInterval}
            onPollIntervalChange={setJiraPollInterval}
            pollIntervalValid={jiraPollIntervalValid}
            agents={agents}
            defaultAgentId={defaultAgentId}
            onDefaultAgentChange={setDefaultAgentId}
            isActive={isActive}
            onIsActiveChange={setIsActive}
          />
        )}

        {kind === 'github' && (
          <GitHubSourceBody
            integrationName={githubIntegrationName}
            onIntegrationNameChange={setGithubIntegrationName}
            integrations={githubIntegrations}
            integrationsLoading={githubIntegrationsLoading}
            selectedIntegrationId={selectedGithubIntegrationId}
            onIntegrationSelect={(next) => {
              setSelectedGithubIntegrationId(next)
              if (next) {
                const match = githubIntegrations.find((item) => item.id === next)
                if (match?.default_owner) setRepoOwner(match.default_owner)
                if (match?.default_repo) setRepoName(match.default_repo)
              }
            }}
            repoOwner={repoOwner}
            onRepoOwnerChange={setRepoOwner}
            repoName={repoName}
            onRepoNameChange={setRepoName}
            webhookSecret={githubWebhookSecret}
            onWebhookSecretChange={setGithubWebhookSecret}
            events={githubEvents}
            onToggleEvent={(eventName) => setGithubEvents((current) => (
              current.includes(eventName)
                ? current.filter((item) => item !== eventName)
                : [...current, eventName]
            ))}
            agents={agents}
            defaultAgentId={defaultAgentId}
            onDefaultAgentChange={setDefaultAgentId}
            isActive={isActive}
            onIsActiveChange={setIsActive}
          />
        )}
      </Wizard>
    )
  }

  // ---------------------------------------------------------------- step 3 (Criteria)
  if (step === 3 && kind) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title="Create Trigger"
        steps={wizardSteps}
        currentStep={3}
        tone={tone}
        stepTitle="Match the events that should wake your agents"
        stepDescription="Refine which messages, payloads, or repository events count as a hit. Leave defaults to receive everything from the chosen source."
        footer={renderFooter(
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Discard
              </button>
            </div>
            <button
              type="button"
              // Skip step 4 (Memory Recap) entirely when case-memory is
              // off — the wizard goes Criteria → Review & Save in that
              // case, mirroring how `wizardSteps` drops the step from
              // the visible list.
              onClick={() => setStep(caseMemoryEnabled ? 4 : 5)}
              disabled={!criteriaValid}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-40 ${accentButtonClass}`}
            >
              {caseMemoryEnabled ? 'Configure Memory' : 'Review & Save'}
            </button>
          </>,
        )}
      >
        {kind === 'email' && (
          <EmailCriteriaBody
            searchQuery={emailSearchQuery}
            onSearchQueryChange={setEmailSearchQuery}
          />
        )}
        {kind === 'webhook' && (
          <WebhookCriteriaBody
            criteriaText={webhookCriteriaText}
            onCriteriaTextChange={setWebhookCriteriaText}
          />
        )}
        {kind === 'jira' && (
          <JiraCriteriaBody
            jql={jiraJql}
            integrationSiteUrl={jiraIntegrations.find((i) => i.id === jiraIntegrationId)?.site_url || ''}
            sampleIssues={jiraSampleIssues}
            testing={jiraTesting}
            testResult={jiraTestResult}
            canTest={Boolean(jiraIntegrationId && jiraJql.trim())}
            onTestQuery={handleJiraTestQuery}
            criteriaText={jiraCriteriaText}
            onCriteriaTextChange={setJiraCriteriaText}
            projectKey={jiraProjectKey}
            onProjectKeyChange={setJiraProjectKey}
            onJqlChange={setJiraJql}
          />
        )}

        {kind === 'github' && (
          <GitHubCriteriaBody
            prSelectedActions={prSelectedActions}
            onTogglePRAction={(action) => setPrSelectedActions((current) => (
              current.includes(action)
                ? current.filter((item) => item !== action)
                : [...current, action]
            ))}
            prDraftOnly={prDraftOnly}
            onPrDraftOnlyChange={setPrDraftOnly}
            prTitleContains={prTitleContains}
            onPrTitleContainsChange={setPrTitleContains}
            prBodyContains={prBodyContains}
            onPrBodyContainsChange={setPrBodyContains}
            prSamplePayloadText={prSamplePayloadText}
            onPrSamplePayloadChange={setPrSamplePayloadText}
            prCriteriaResult={prCriteriaResult}
            prCriteriaTesting={prCriteriaTesting}
            onTestPRSubmittedCriteria={handleTestPRSubmittedCriteria}
            branchFilter={branchFilter}
            onBranchFilterChange={setBranchFilter}
            pathFiltersText={pathFiltersText}
            onPathFiltersChange={setPathFiltersText}
            authorFilter={authorFilter}
            onAuthorFilterChange={setAuthorFilter}
          />
        )}
      </Wizard>
    )
  }

  // ---------------------------------------------------------------- step 4 (Memory Recap)
  // The useEffect above redirects step 4 → step 5 whenever the flag is
  // off, so this branch only fires when caseMemoryEnabled is true.
  if (step === 4 && kind && caseMemoryEnabled) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title="Create Trigger"
        steps={wizardSteps}
        currentStep={4}
        tone={tone}
        stepTitle="Recall past similar cases on every wake"
        stepDescription="When this trigger fires, run a recall query against case memory and inject snippets of similar past cases into the agent's prompt. Off by default."
        footer={renderFooter(
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(3)}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Discard
              </button>
            </div>
            <button
              type="button"
              onClick={() => setStep(5)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-opacity ${accentButtonClass}`}
            >
              Review &amp; Save
            </button>
          </>,
        )}
      >
        <MemoryRecapStep
          triggerKind={kind}
          initialConfig={recapConfig}
          onChange={setRecapConfig}
          triggerInstanceId={(savedTrigger as { id?: number } | null)?.id ?? null}
          caseMemoryEnabled={caseMemoryEnabled}
        />
      </Wizard>
    )
  }

  // ---------------------------------------------------------------- step 5 (Confirm)
  if (saveState === 'success' && savedTrigger && kind) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title="Create Trigger"
        steps={wizardSteps}
        currentStep={5}
        tone={tone}
        status="success"
        statusTitle={`${displayKind(kind)} trigger created`}
        statusDescription={`"${triggerLabel(savedTrigger)}" is now ${triggerActiveLabel(savedTrigger)}.`}
        statusBody={(
          <PostSaveSummary
            kind={kind}
            savedTrigger={savedTrigger}
            autoFlowId={autoFlowId}
            webhookSecret={webhookSecret}
            secretCopied={secretCopied}
            onCopySecret={handleCopySecret}
          />
        )}
        footer={renderFooter(
          <>
            <button
              type="button"
              onClick={handleClose}
              className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
            >
              Done
            </button>
            {autoFlowId ? (
              <button
                type="button"
                onClick={handleOpenFlowEditor}
                className={`rounded-lg px-4 py-2 text-sm font-medium transition-opacity ${accentButtonClass}`}
              >
                Open Flow Editor
              </button>
            ) : (
              <span className="rounded-lg border border-tsushin-border/30 bg-tsushin-slate/5 px-4 py-2 text-xs text-tsushin-slate/60">
                Wired flow not generated (flows feature flag disabled)
              </span>
            )}
          </>,
        )}
      />
    )
  }

  if (kind) {
    // Pre-save Confirm view.
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title="Create Trigger"
        steps={wizardSteps}
        currentStep={5}
        tone={tone}
        status={saveState === 'saving' ? 'loading' : 'idle'}
        statusTitle={saveState === 'saving' ? 'Saving trigger…' : undefined}
        statusDescription={saveState === 'saving' ? 'Persisting the trigger and wiring its auto-flow.' : undefined}
        stepTitle="Review and create the trigger"
        stepDescription="Double-check every field. Saving creates the trigger and its wired auto-flow in one step."
        footer={saveState === 'saving'
          ? renderFooter(
              <div className="ml-auto rounded-lg border border-tsushin-border/70 bg-tsushin-slate/10 px-4 py-2 text-sm text-tsushin-slate">
                Saving…
              </div>,
            )
          : renderFooter(
              <>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    // Mirror the forward-skip: when case-memory is off,
                    // step 4 (Memory Recap) is invisible, so the
                    // Confirm view's Back button must jump to step 3
                    // (Criteria) instead.
                    onClick={() => setStep(caseMemoryEnabled ? 4 : 3)}
                    className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={handleClose}
                    className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
                  >
                    Discard
                  </button>
                </div>
                <button
                  type="button"
                  onClick={handleSave}
                  className={`rounded-lg px-4 py-2 text-sm font-medium transition-opacity ${accentButtonClass}`}
                >
                  Create Trigger
                </button>
              </>,
            )}
      >
        <div className="space-y-5">
          {saveError && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {saveError}
            </div>
          )}
          <PreSaveSummary
            kind={kind}
            agents={agents}
            defaultAgentId={defaultAgentId}
            isActive={isActive}
            email={{
              integrationName: emailIntegrationName,
              account: selectedGmailAccount?.email_address || null,
              query: emailSearchQuery,
              pollSeconds: emailPollValue,
            }}
            webhook={{
              integrationName: webhookName,
              callbackUrl: webhookCallbackUrl,
              callbackEnabled: webhookCallbackEnabled,
              ipAllowlist: webhookIpAllowlistText,
              rateLimit: webhookRateLimitRpm,
            }}
            jira={{
              integrationName: jiraIntegrationName,
              connection: jiraIntegrations.find((i) => i.id === jiraIntegrationId)?.integration_name
                || jiraIntegrations.find((i) => i.id === jiraIntegrationId)?.name
                || null,
              projectKey: jiraProjectKey,
              jql: jiraJql,
              pollSeconds: jiraPollValue,
            }}
            github={{
              integrationName: githubIntegrationName,
              integrationId: selectedGithubIntegrationId,
              repoOwner,
              repoName,
              events: githubEvents,
              prActions: prSelectedActions,
            }}
          />
        </div>
      </Wizard>
    )
  }

  // No kind selected and step > 1 — defensive fallback.
  return null
}

// ============================================================================
// Step body helpers
// ============================================================================

function sourceStepTitle(kind: TriggerId): string {
  switch (kind) {
    case 'email':
      return 'Connect a Gmail account for this trigger'
    case 'webhook':
      return 'Configure the inbound webhook integration'
    case 'jira':
      return 'Connect a Jira workspace and pick a JQL'
    case 'github':
      return 'Connect a GitHub repository to watch'
  }
}

function sourceStepDescription(kind: TriggerId): string {
  switch (kind) {
    case 'email':
      return 'Reuses Gmail OAuth integrations from Hub → Productivity. Connect a new account here without leaving the wizard.'
    case 'webhook':
      return 'Generates a unique inbound URL and signed secret you can hand to a third-party system.'
    case 'jira':
      return 'Pick a configured Jira connection and the JQL the trigger should poll.'
    case 'github':
      return 'Pick a Hub GitHub integration, then wire a webhook so repository events fire this trigger.'
  }
}

function displayKind(kind: TriggerId): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1)
}

function triggerLabel(saved: SavedTriggerAny): string {
  return (saved as { integration_name?: string }).integration_name || 'Trigger'
}

function triggerActiveLabel(saved: SavedTriggerAny): string {
  return (saved as { is_active?: boolean }).is_active === false ? 'paused' : 'active'
}

// ============================================================================
// Email step bodies
// ============================================================================

interface EmailSourceBodyProps {
  credentialsOk: boolean
  onCredentialsReady: () => void
  integrations: ReturnType<typeof useGmailOAuthPoller>['integrations']
  integrationsLoading: boolean
  popupOpen: boolean
  popupError: string | null
  onConnectNew: () => Promise<void>
  selectedIntegrationId: number | null
  onSelectIntegration: (id: number) => void
  integrationName: string
  onIntegrationNameChange: (value: string) => void
  pollIntervalSeconds: string
  onPollIntervalChange: (value: string) => void
  pollIntervalValid: boolean
  agents: Agent[]
  defaultAgentId: number | null
  onDefaultAgentChange: (id: number | null) => void
  isActive: boolean
  onIsActiveChange: (value: boolean) => void
}

function EmailSourceBody({
  credentialsOk,
  onCredentialsReady,
  integrations,
  integrationsLoading,
  popupOpen,
  popupError,
  onConnectNew,
  selectedIntegrationId,
  onSelectIntegration,
  integrationName,
  onIntegrationNameChange,
  pollIntervalSeconds,
  onPollIntervalChange,
  pollIntervalValid,
  agents,
  defaultAgentId,
  onDefaultAgentChange,
  isActive,
  onIsActiveChange,
}: EmailSourceBodyProps) {
  const idPrefix = useId()
  const integrationNameId = `${idPrefix}-name`
  const pollIntervalId = `${idPrefix}-poll`
  const defaultAgentId_ = `${idPrefix}-agent`
  return (
    <div className="space-y-5">
      <GoogleAppCredentialsStep tone="gmail" onReady={onCredentialsReady} />

      {!credentialsOk && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Confirm Google OAuth credentials above before continuing.
        </div>
      )}

      {popupError && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {popupError}
        </div>
      )}

      {integrationsLoading ? (
        <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 px-4 py-8 text-center text-sm text-tsushin-slate">
          Loading Gmail accounts…
        </div>
      ) : integrations.length > 0 ? (
        <div className="space-y-3">
          <div className="text-sm font-medium text-white">Existing Gmail accounts</div>
          <div className="space-y-2">
            {integrations.map((integration) => (
              <label
                key={integration.id}
                className="flex cursor-pointer items-center gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4 hover:bg-tsushin-slate/10"
              >
                <input
                  type="radio"
                  name="trigger-wizard-gmail-account"
                  checked={selectedIntegrationId === integration.id}
                  onChange={() => onSelectIntegration(integration.id)}
                  className="h-4 w-4 border-white/20 bg-[#0a0a0f] text-red-500 focus:ring-red-500"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-white">{integration.email_address}</div>
                  <div className="mt-1 text-xs text-tsushin-slate">
                    {integration.name} · {gmailCapabilityLabel(integration)}
                  </div>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    integration.health_status === 'healthy'
                      ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : 'border border-yellow-500/30 bg-yellow-500/10 text-yellow-300'
                  }`}
                >
                  {integration.health_status}
                </span>
              </label>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-tsushin-border/70 bg-tsushin-slate/5 px-4 py-8 text-center">
          <div className="text-sm font-medium text-white">No Gmail accounts connected yet</div>
          <p className="mt-2 text-sm text-tsushin-slate">
            Connect the first account below and it will be selected automatically for this trigger.
          </p>
        </div>
      )}

      <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-white">Connect a new Gmail account</div>
            <p className="mt-1 text-xs text-tsushin-slate">
              Opens the same Google consent flow used by the Gmail setup wizard.
            </p>
          </div>
          <button
            type="button"
            onClick={onConnectNew}
            disabled={popupOpen || !credentialsOk}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-opacity hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {popupOpen ? 'Waiting for Google consent…' : 'Connect New Account'}
          </button>
        </div>
        {popupOpen && (
          <p className="mt-3 text-xs text-tsushin-slate">
            When the Google popup finishes, this wizard will refresh the account list automatically.
          </p>
        )}
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor={integrationNameId} className="block text-sm font-medium text-white">
            Trigger Name <span className="text-red-400">*</span>
          </label>
          <input
            id={integrationNameId}
            type="text"
            value={integrationName}
            onChange={(event) => onIntegrationNameChange(event.target.value)}
            placeholder="Inbox: ops@example.com"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
          />
          <p className="text-xs text-tsushin-slate">Human label shown in Triggers and Hub.</p>
        </div>
        <div className="space-y-2">
          <label htmlFor={pollIntervalId} className="block text-sm font-medium text-white">
            Poll interval (seconds) <span className="text-red-400">*</span>
          </label>
          <input
            id={pollIntervalId}
            type="number"
            min={30}
            max={3600}
            step={30}
            value={pollIntervalSeconds}
            onChange={(event) => onPollIntervalChange(event.target.value)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
          />
          <p className={`text-xs ${pollIntervalValid ? 'text-tsushin-slate' : 'text-amber-300'}`}>
            Use a value between 30 and 3600 seconds.
          </p>
        </div>
        <div className="space-y-2">
          <label htmlFor={defaultAgentId_} className="block text-sm font-medium text-white">Default agent</label>
          <select
            id={defaultAgentId_}
            value={defaultAgentId ?? ''}
            onChange={(event) => onDefaultAgentChange(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
          >
            <option value="">No default agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.contact_name}
              </option>
            ))}
          </select>
          <p className="text-xs text-tsushin-slate">Optional. Wakes a specific agent on each match.</p>
        </div>
        <label className="flex items-center gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(event) => onIsActiveChange(event.target.checked)}
            className="h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-red-500 focus:ring-red-500"
          />
          <div>
            <div className="text-sm font-medium text-white">{isActive ? 'Active on save' : 'Create paused'}</div>
            <p className="mt-1 text-xs text-tsushin-slate">
              You can flip this later from the trigger detail page.
            </p>
          </div>
        </label>
      </div>
    </div>
  )
}

interface EmailCriteriaBodyProps {
  searchQuery: string
  onSearchQueryChange: (value: string) => void
}

function EmailCriteriaBody({ searchQuery, onSearchQueryChange }: EmailCriteriaBodyProps) {
  const idPrefix = useId()
  const searchQueryId = `${idPrefix}-search`
  const previewQuery = searchQuery.trim() || 'label:inbox is:unread'
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label htmlFor={searchQueryId} className="block text-sm font-medium text-white">Gmail Search Query</label>
        <textarea
          id={searchQueryId}
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          rows={3}
          placeholder="label:inbox is:unread newer_than:2d"
          className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
        />
        <p className="text-xs text-tsushin-slate">
          Leave blank to watch all new inbox activity. Any valid Gmail search query works here.
        </p>
      </div>

      <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
        <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Watches</div>
        <div className="mt-2 font-mono text-sm text-emerald-200">{previewQuery}</div>
        <p className="mt-2 text-xs text-tsushin-slate">
          The trigger criteria envelope is generated automatically from this query.
        </p>
      </div>
    </div>
  )
}

// ============================================================================
// Webhook step bodies
// ============================================================================

interface WebhookSourceBodyProps {
  integrationName: string
  onIntegrationNameChange: (value: string) => void
  callbackUrl: string
  onCallbackUrlChange: (value: string) => void
  callbackEnabled: boolean
  onCallbackEnabledChange: (value: boolean) => void
  ipAllowlistText: string
  onIpAllowlistChange: (value: string) => void
  rateLimitRpm: string
  onRateLimitChange: (value: string) => void
  agents: Agent[]
  defaultAgentId: number | null
  onDefaultAgentChange: (id: number | null) => void
  isActive: boolean
  onIsActiveChange: (value: boolean) => void
}

function WebhookSourceBody({
  integrationName,
  onIntegrationNameChange,
  callbackUrl,
  onCallbackUrlChange,
  callbackEnabled,
  onCallbackEnabledChange,
  ipAllowlistText,
  onIpAllowlistChange,
  rateLimitRpm,
  onRateLimitChange,
  agents,
  defaultAgentId,
  onDefaultAgentChange,
  isActive,
  onIsActiveChange,
}: WebhookSourceBodyProps) {
  const idPrefix = useId()
  const integrationNameId = `${idPrefix}-name`
  const callbackUrlId = `${idPrefix}-callback`
  const ipAllowlistId = `${idPrefix}-ip`
  const rateLimitId = `${idPrefix}-rate`
  const defaultAgentSelectId = `${idPrefix}-agent`
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
        The webhook secret is auto-generated and shown once on the Confirm step. Copy it before closing the wizard.
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor={integrationNameId} className="block text-sm font-medium text-white">
            Integration Name <span className="text-red-400">*</span>
          </label>
          <input
            id={integrationNameId}
            type="text"
            value={integrationName}
            onChange={(event) => onIntegrationNameChange(event.target.value)}
            placeholder="Stripe → ops"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={callbackUrlId} className="block text-sm font-medium text-white">Callback URL (optional)</label>
          <input
            id={callbackUrlId}
            type="url"
            value={callbackUrl}
            onChange={(event) => onCallbackUrlChange(event.target.value)}
            placeholder="https://example.com/hooks/return"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
          />
          <label className="mt-1 flex items-center gap-2 text-xs text-tsushin-slate">
            <input
              type="checkbox"
              checked={callbackEnabled}
              onChange={(event) => onCallbackEnabledChange(event.target.checked)}
              className="h-3.5 w-3.5 rounded border-white/20 bg-[#0a0a0f] text-cyan-500 focus:ring-cyan-500"
            />
            Enable outbound callback to this URL
          </label>
        </div>

        <div className="space-y-2 md:col-span-2">
          <label htmlFor={ipAllowlistId} className="block text-sm font-medium text-white">IP Allowlist (one CIDR per line)</label>
          <textarea
            id={ipAllowlistId}
            value={ipAllowlistText}
            onChange={(event) => onIpAllowlistChange(event.target.value)}
            rows={3}
            placeholder={`192.0.2.0/24\n203.0.113.42/32`}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
          />
          <p className="text-xs text-tsushin-slate">Leave blank to allow any source IP.</p>
        </div>

        <div className="space-y-2">
          <label htmlFor={rateLimitId} className="block text-sm font-medium text-white">Rate Limit (requests / minute)</label>
          <input
            id={rateLimitId}
            type="number"
            min={1}
            value={rateLimitRpm}
            onChange={(event) => onRateLimitChange(event.target.value)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={defaultAgentSelectId} className="block text-sm font-medium text-white">Default agent</label>
          <select
            id={defaultAgentSelectId}
            value={defaultAgentId ?? ''}
            onChange={(event) => onDefaultAgentChange(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
          >
            <option value="">No default agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.contact_name}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(event) => onIsActiveChange(event.target.checked)}
            className="h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-cyan-500 focus:ring-cyan-500"
          />
          <div>
            <div className="text-sm font-medium text-white">{isActive ? 'Active on save' : 'Create paused'}</div>
            <p className="mt-1 text-xs text-tsushin-slate">Paused webhooks reject inbound requests until resumed.</p>
          </div>
        </label>
      </div>
    </div>
  )
}

interface WebhookCriteriaBodyProps {
  criteriaText: string
  onCriteriaTextChange: (value: string) => void
}

function WebhookCriteriaBody({ criteriaText, onCriteriaTextChange }: WebhookCriteriaBodyProps) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-tsushin-slate">
        Provide an optional criteria envelope to filter inbound payloads. Leave empty to accept everything.
      </p>
      <CriteriaBuilder
        kind="webhook"
        value={criteriaText}
        onChange={onCriteriaTextChange}
      />
    </div>
  )
}

// ============================================================================
// Jira step bodies
// ============================================================================

interface JiraSourceBodyProps {
  integrations: JiraIntegration[]
  integrationsLoading: boolean
  integrationId: number | null
  onIntegrationIdChange: (id: number | null) => void
  integrationName: string
  onIntegrationNameChange: (value: string) => void
  projectKey: string
  onProjectKeyChange: (value: string) => void
  jql: string
  onJqlChange: (value: string) => void
  pollInterval: string
  onPollIntervalChange: (value: string) => void
  pollIntervalValid: boolean
  agents: Agent[]
  defaultAgentId: number | null
  onDefaultAgentChange: (id: number | null) => void
  isActive: boolean
  onIsActiveChange: (value: boolean) => void
}

function JiraSourceBody({
  integrations,
  integrationsLoading,
  integrationId,
  onIntegrationIdChange,
  integrationName,
  onIntegrationNameChange,
  projectKey,
  onProjectKeyChange,
  jql,
  onJqlChange,
  pollInterval,
  onPollIntervalChange,
  pollIntervalValid,
  agents,
  defaultAgentId,
  onDefaultAgentChange,
  isActive,
  onIsActiveChange,
}: JiraSourceBodyProps) {
  const idPrefix = useId()
  const integrationNameId = `${idPrefix}-name`
  const connectionId = `${idPrefix}-conn`
  const projectKeyId = `${idPrefix}-project`
  const pollIntervalId = `${idPrefix}-poll`
  const jqlId = `${idPrefix}-jql`
  const defaultAgentSelectId = `${idPrefix}-agent`
  const selected = integrations.find((entry) => entry.id === integrationId) || null

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor={integrationNameId} className="block text-sm font-medium text-white">
            Trigger Name <span className="text-red-400">*</span>
          </label>
          <input
            id={integrationNameId}
            type="text"
            value={integrationName}
            onChange={(event) => onIntegrationNameChange(event.target.value)}
            placeholder="Jira issue watcher"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={connectionId} className="block text-sm font-medium text-white">
            Jira Connection <span className="text-red-400">*</span>
          </label>
          <select
            id={connectionId}
            value={integrationId ?? ''}
            onChange={(event) => onIntegrationIdChange(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          >
            <option value="">
              {integrationsLoading ? 'Loading Jira connections…' : 'Select a Jira connection'}
            </option>
            {integrations.map((integration) => (
              <option key={integration.id} value={integration.id}>
                {integration.integration_name || integration.name || `Jira connection #${integration.id}`}
              </option>
            ))}
          </select>
          <p className="text-xs text-tsushin-slate">
            {selected
              ? selected.site_url
              : 'Add a Jira connection in Hub > Tool APIs, then return here and refresh the wizard.'}
          </p>
        </div>

        {!integrationsLoading && integrations.length === 0 && (
          <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-4 md:col-span-2">
            <div className="text-sm font-medium text-white">No Jira connections yet</div>
            <p className="mt-1 text-xs text-tsushin-slate">
              Jira triggers require a Hub Jira connection. Create one in Tool APIs, then come back to select it here.
            </p>
            <a
              href="/hub?tab=tool-apis"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex rounded-lg border border-blue-400/40 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-100 hover:text-white"
            >
              Create Jira connection
            </a>
          </div>
        )}

        <div className="space-y-2">
          <label htmlFor={projectKeyId} className="block text-sm font-medium text-white">Project Key</label>
          <input
            id={projectKeyId}
            type="text"
            value={projectKey}
            onChange={(event) => onProjectKeyChange(event.target.value.toUpperCase())}
            placeholder="OPS"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={pollIntervalId} className="block text-sm font-medium text-white">
            Poll Interval (seconds) <span className="text-red-400">*</span>
          </label>
          <input
            id={pollIntervalId}
            type="number"
            min={60}
            max={3600}
            step={60}
            value={pollInterval}
            onChange={(event) => onPollIntervalChange(event.target.value)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          />
          <p className={`text-xs ${pollIntervalValid ? 'text-tsushin-slate' : 'text-amber-300'}`}>
            Use a value between 60 and 3600 seconds.
          </p>
        </div>

        <div className="space-y-2 md:col-span-2">
          <label htmlFor={jqlId} className="block text-sm font-medium text-white">
            JQL <span className="text-red-400">*</span>
          </label>
          <textarea
            id={jqlId}
            value={jql}
            onChange={(event) => onJqlChange(event.target.value)}
            rows={3}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={defaultAgentSelectId} className="block text-sm font-medium text-white">Default agent</label>
          <select
            id={defaultAgentSelectId}
            value={defaultAgentId ?? ''}
            onChange={(event) => onDefaultAgentChange(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          >
            <option value="">No default agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.contact_name}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(event) => onIsActiveChange(event.target.checked)}
            className="h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-blue-500 focus:ring-blue-500"
          />
          <div>
            <div className="text-sm font-medium text-white">{isActive ? 'Active on save' : 'Create paused'}</div>
            <p className="mt-1 text-xs text-tsushin-slate">Paused triggers stop polling Jira until resumed.</p>
          </div>
        </label>
      </div>
    </div>
  )
}

interface JiraCriteriaBodyProps {
  jql: string
  integrationSiteUrl: string
  sampleIssues: JiraIssuePreview[]
  testing: boolean
  testResult: { tone: 'success' | 'error'; message: string } | null
  canTest: boolean
  onTestQuery: () => void
  criteriaText: string
  onCriteriaTextChange: (value: string) => void
  projectKey: string
  onProjectKeyChange: (value: string) => void
  onJqlChange: (value: string) => void
}

function JiraCriteriaBody({
  jql,
  integrationSiteUrl,
  sampleIssues,
  testing,
  testResult,
  canTest,
  onTestQuery,
  criteriaText,
  onCriteriaTextChange,
  projectKey,
  onProjectKeyChange,
  onJqlChange,
}: JiraCriteriaBodyProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-blue-500/20 bg-blue-500/5 p-4">
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="text-xs uppercase tracking-[0.18em] text-blue-200">JQL preview</div>
          <button
            type="button"
            onClick={onTestQuery}
            disabled={!canTest || testing}
            className="rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-1.5 text-xs text-blue-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {testing ? 'Testing…' : 'Test Query'}
          </button>
        </div>
        <pre className="whitespace-pre-wrap break-words rounded-lg bg-black/40 px-3 py-2 font-mono text-xs text-blue-100">
{jql.trim() || '(JQL is empty — go back to the Source step to set it.)'}
        </pre>
      </div>

      {testResult && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${
          testResult.tone === 'success'
            ? 'border-green-500/30 bg-green-500/10 text-green-200'
            : 'border-red-500/30 bg-red-500/10 text-red-200'
        }`}>
          {testResult.message}
        </div>
      )}

      {sampleIssues.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm font-medium text-white">Sample issues</div>
          <JiraIssuePreviewList issues={sampleIssues} siteUrl={integrationSiteUrl} />
        </div>
      )}

      <CriteriaBuilder
        kind="jira"
        value={criteriaText}
        onChange={onCriteriaTextChange}
        source={{
          jiraProjectKey: projectKey,
          jiraJql: jql,
        }}
        onSourceChange={(patch) => {
          if (patch.jiraProjectKey !== undefined) onProjectKeyChange(patch.jiraProjectKey || '')
          if (patch.jiraJql !== undefined) onJqlChange(patch.jiraJql || '')
        }}
      />
    </div>
  )
}

// ============================================================================
// GitHub step bodies
// ============================================================================

interface GitHubSourceBodyProps {
  integrationName: string
  onIntegrationNameChange: (value: string) => void
  integrations: GitHubIntegration[]
  integrationsLoading: boolean
  selectedIntegrationId: number | null
  onIntegrationSelect: (id: number | null) => void
  repoOwner: string
  onRepoOwnerChange: (value: string) => void
  repoName: string
  onRepoNameChange: (value: string) => void
  webhookSecret: string
  onWebhookSecretChange: (value: string) => void
  events: string[]
  onToggleEvent: (eventName: string) => void
  agents: Agent[]
  defaultAgentId: number | null
  onDefaultAgentChange: (id: number | null) => void
  isActive: boolean
  onIsActiveChange: (value: boolean) => void
}

function GitHubSourceBody({
  integrationName,
  onIntegrationNameChange,
  integrations,
  integrationsLoading,
  selectedIntegrationId,
  onIntegrationSelect,
  repoOwner,
  onRepoOwnerChange,
  repoName,
  onRepoNameChange,
  webhookSecret,
  onWebhookSecretChange,
  events,
  onToggleEvent,
  agents,
  defaultAgentId,
  onDefaultAgentChange,
  isActive,
  onIsActiveChange,
}: GitHubSourceBodyProps) {
  const idPrefix = useId()
  const integrationNameId = `${idPrefix}-name`
  const connectionId = `${idPrefix}-conn`
  const repoOwnerId = `${idPrefix}-owner`
  const repoNameId = `${idPrefix}-repo`
  const webhookSecretId = `${idPrefix}-secret`
  const eventsLegendId = `${idPrefix}-events`
  const defaultAgentSelectId = `${idPrefix}-agent`
  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor={integrationNameId} className="block text-sm font-medium text-white">
            Trigger Name <span className="text-red-400">*</span>
          </label>
          <input
            id={integrationNameId}
            type="text"
            value={integrationName}
            onChange={(event) => onIntegrationNameChange(event.target.value)}
            placeholder="GitHub repository events"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={connectionId} className="block text-sm font-medium text-white">
            GitHub Connection <span className="text-red-400">*</span>
          </label>
          <select
            id={connectionId}
            value={selectedIntegrationId ?? ''}
            onChange={(event) => onIntegrationSelect(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          >
            <option value="">
              {integrationsLoading ? 'Loading GitHub connections…' : 'Pick a Hub GitHub integration…'}
            </option>
            {integrations.map((integration) => (
              <option key={integration.id} value={integration.id}>
                {integration.integration_name || integration.name || `GitHub connection #${integration.id}`}
                {integration.default_owner && integration.default_repo
                  ? ` — ${integration.default_owner}/${integration.default_repo}`
                  : ''}
              </option>
            ))}
          </select>
          <p className="text-xs text-tsushin-slate">
            Triggers reuse Hub-side GitHub integrations. Create one under{' '}
            <a href="/hub?tab=developer" target="_blank" rel="noopener" className="text-violet-300 hover:text-white">Hub → Developer Tools</a>{' '}
            if none exist yet.
          </p>
        </div>

        {!integrationsLoading && integrations.length === 0 && (
          <div className="rounded-2xl border border-violet-500/20 bg-violet-500/5 p-4 md:col-span-2">
            <div className="text-sm font-medium text-white">No GitHub connections yet</div>
            <p className="mt-1 text-xs text-tsushin-slate">
              GitHub triggers require a Hub GitHub connection. Create one in Developer Tools, then return here and select it before continuing.
            </p>
            <a
              href="/hub?tab=developer"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex rounded-lg border border-violet-400/40 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-100 hover:text-white"
            >
              Create GitHub connection
            </a>
          </div>
        )}

        <div className="space-y-2">
          <label htmlFor={repoOwnerId} className="block text-sm font-medium text-white">
            Repository Owner <span className="text-red-400">*</span>
          </label>
          <input
            id={repoOwnerId}
            type="text"
            value={repoOwner}
            onChange={(event) => onRepoOwnerChange(event.target.value)}
            placeholder="octo-org"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={repoNameId} className="block text-sm font-medium text-white">
            Repository Name <span className="text-red-400">*</span>
          </label>
          <input
            id={repoNameId}
            type="text"
            value={repoName}
            onChange={(event) => onRepoNameChange(event.target.value)}
            placeholder="platform"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>

        <div className="space-y-2 md:col-span-2" role="group" aria-labelledby={eventsLegendId}>
          <div id={eventsLegendId} className="block text-sm font-medium text-white">
            Events <span className="text-red-400">*</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {GITHUB_EVENT_OPTIONS.map((eventName) => {
              const isSelected = events.includes(eventName)
              return (
                <button
                  key={eventName}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onToggleEvent(eventName)}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    isSelected
                      ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                      : 'border-tsushin-border text-tsushin-slate hover:text-white'
                  }`}
                >
                  {eventName.replace('_', ' ')}
                </button>
              )
            })}
          </div>
        </div>

        <div className="space-y-2">
          <label htmlFor={webhookSecretId} className="block text-sm font-medium text-white">Webhook Secret</label>
          <input
            id={webhookSecretId}
            type="password"
            value={webhookSecret}
            onChange={(event) => onWebhookSecretChange(event.target.value)}
            placeholder="Leave blank to auto-generate"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor={defaultAgentSelectId} className="block text-sm font-medium text-white">Default agent</label>
          <select
            id={defaultAgentSelectId}
            value={defaultAgentId ?? ''}
            onChange={(event) => onDefaultAgentChange(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          >
            <option value="">No default agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.contact_name}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4 md:col-span-2">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(event) => onIsActiveChange(event.target.checked)}
            className="h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-violet-500 focus:ring-violet-500"
          />
          <div>
            <div className="text-sm font-medium text-white">{isActive ? 'Active on save' : 'Create paused'}</div>
            <p className="mt-1 text-xs text-tsushin-slate">Paused triggers reject inbound GitHub webhooks until resumed.</p>
          </div>
        </label>
      </div>

    </div>
  )
}

interface GitHubCriteriaBodyProps {
  prSelectedActions: PRSubmittedAction[]
  onTogglePRAction: (action: PRSubmittedAction) => void
  prDraftOnly: boolean
  onPrDraftOnlyChange: (value: boolean) => void
  prTitleContains: string
  onPrTitleContainsChange: (value: string) => void
  prBodyContains: string
  onPrBodyContainsChange: (value: string) => void
  prSamplePayloadText: string
  onPrSamplePayloadChange: (value: string) => void
  prCriteriaResult: { matched: boolean; message: string } | null
  prCriteriaTesting: boolean
  onTestPRSubmittedCriteria: () => void
  branchFilter: string
  onBranchFilterChange: (value: string) => void
  pathFiltersText: string
  onPathFiltersChange: (value: string) => void
  authorFilter: string
  onAuthorFilterChange: (value: string) => void
}

function GitHubCriteriaBody({
  prSelectedActions,
  onTogglePRAction,
  prDraftOnly,
  onPrDraftOnlyChange,
  prTitleContains,
  onPrTitleContainsChange,
  prBodyContains,
  onPrBodyContainsChange,
  prSamplePayloadText,
  onPrSamplePayloadChange,
  prCriteriaResult,
  prCriteriaTesting,
  onTestPRSubmittedCriteria,
  branchFilter,
  onBranchFilterChange,
  pathFiltersText,
  onPathFiltersChange,
  authorFilter,
  onAuthorFilterChange,
}: GitHubCriteriaBodyProps) {
  const idPrefix = useId()
  const eventInputId = `${idPrefix}-event`
  const actionsLegendId = `${idPrefix}-actions`
  const titleContainsId = `${idPrefix}-title`
  const bodyContainsId = `${idPrefix}-body`
  const samplePayloadId = `${idPrefix}-sample`
  const branchFilterId = `${idPrefix}-branch`
  const authorFilterId = `${idPrefix}-author`
  const pathFiltersId = `${idPrefix}-paths`
  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-xl border border-violet-500/20 bg-violet-500/5 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-white">PR Submitted criteria</div>
            <p className="mt-1 text-xs text-tsushin-slate">
              The structured envelope the dispatcher matches incoming GitHub webhooks against.
            </p>
          </div>
          <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-violet-200">
            v0.7.0
          </span>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor={eventInputId} className="block text-xs font-medium text-tsushin-slate">Event</label>
            <input
              id={eventInputId}
              type="text"
              value="Pull Request"
              readOnly
              disabled
              className="w-full cursor-not-allowed rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-tsushin-slate"
            />
            <p className="text-[11px] text-tsushin-slate">Locked — push criteria coming later.</p>
          </div>
          <div className="space-y-1">
            <label className="flex items-start gap-2 text-xs font-medium text-tsushin-slate">
              <input
                type="checkbox"
                checked={prDraftOnly}
                onChange={(event) => onPrDraftOnlyChange(event.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-violet-500 focus:ring-violet-500"
              />
              <span>
                Only non-draft PRs
                <br />
                <span className="font-normal text-[11px] text-tsushin-slate">
                  When checked, draft PRs are rejected even if the action matches.
                </span>
              </span>
            </label>
          </div>
        </div>

        <div className="space-y-1" role="group" aria-labelledby={actionsLegendId}>
          <div id={actionsLegendId} className="block text-xs font-medium text-tsushin-slate">Actions *</div>
          <div className="flex flex-wrap gap-2">
            {PR_SUBMITTED_ACTION_OPTIONS.map((option) => {
              const isSelected = prSelectedActions.includes(option.value)
              return (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onTogglePRAction(option.value)}
                  title={option.description}
                  className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
                    isSelected
                      ? 'border-violet-500/50 bg-violet-500/10 text-violet-200'
                      : 'border-tsushin-border text-tsushin-slate hover:text-white'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
          {prSelectedActions.length === 0 && (
            <p className="text-[11px] text-amber-300">Pick at least one PR action.</p>
          )}
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor={titleContainsId} className="block text-xs font-medium text-tsushin-slate">Title contains</label>
            <input
              id={titleContainsId}
              type="text"
              value={prTitleContains}
              onChange={(event) => onPrTitleContainsChange(event.target.value)}
              placeholder="[security]"
              className="w-full rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor={bodyContainsId} className="block text-xs font-medium text-tsushin-slate">Body contains</label>
            <input
              id={bodyContainsId}
              type="text"
              value={prBodyContains}
              onChange={(event) => onPrBodyContainsChange(event.target.value)}
              placeholder="closes #"
              className="w-full rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
            />
          </div>
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between gap-3">
            <label htmlFor={samplePayloadId} className="block text-xs font-medium text-tsushin-slate">Sample payload (optional)</label>
            <button
              type="button"
              onClick={() => onPrSamplePayloadChange(DEFAULT_PR_SAMPLE_PAYLOAD)}
              className="text-[11px] text-violet-300 hover:text-white"
            >
              Insert example
            </button>
          </div>
          <textarea
            id={samplePayloadId}
            value={prSamplePayloadText}
            onChange={(event) => onPrSamplePayloadChange(event.target.value)}
            rows={5}
            placeholder="Paste a real GitHub webhook payload here, or click Insert example."
            className="w-full rounded-lg border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onTestPRSubmittedCriteria}
            disabled={prCriteriaTesting || prSelectedActions.length === 0}
            className="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {prCriteriaTesting ? 'Testing…' : 'Test against sample payload'}
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

      <div className="grid gap-4 md:grid-cols-2 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
        <div className="space-y-2">
          <label htmlFor={branchFilterId} className="block text-sm font-medium text-white">Branch filter</label>
          <input
            id={branchFilterId}
            type="text"
            value={branchFilter}
            onChange={(event) => onBranchFilterChange(event.target.value)}
            placeholder="main"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>
        <div className="space-y-2">
          <label htmlFor={authorFilterId} className="block text-sm font-medium text-white">Author filter</label>
          <input
            id={authorFilterId}
            type="text"
            value={authorFilter}
            onChange={(event) => onAuthorFilterChange(event.target.value)}
            placeholder="octocat"
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>
        <div className="space-y-2 md:col-span-2">
          <label htmlFor={pathFiltersId} className="block text-sm font-medium text-white">Path filters (one per line)</label>
          <textarea
            id={pathFiltersId}
            value={pathFiltersText}
            onChange={(event) => onPathFiltersChange(event.target.value)}
            rows={3}
            placeholder={`frontend/**\nbackend/api/**`}
            className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Pre-save and post-save summaries
// ============================================================================

interface PreSaveSummaryProps {
  kind: TriggerId
  agents: Agent[]
  defaultAgentId: number | null
  isActive: boolean
  email: {
    integrationName: string
    account: string | null
    query: string
    pollSeconds: number
  }
  webhook: {
    integrationName: string
    callbackUrl: string
    callbackEnabled: boolean
    ipAllowlist: string
    rateLimit: string
  }
  jira: {
    integrationName: string
    connection: string | null
    projectKey: string
    jql: string
    pollSeconds: number
  }
  github: {
    integrationName: string
    integrationId: number | null
    repoOwner: string
    repoName: string
    events: string[]
    prActions: PRSubmittedAction[]
  }
}

function PreSaveSummary({
  kind,
  agents,
  defaultAgentId,
  isActive,
  email,
  webhook,
  jira,
  github,
}: PreSaveSummaryProps) {
  const agentLabel = agents.find((agent) => agent.id === defaultAgentId)?.contact_name || 'No default agent'
  const cells: Array<[string, string]> = []

  cells.push(['Kind', displayKind(kind)])
  cells.push(['Default agent', agentLabel])
  cells.push(['Status on save', isActive ? 'Active' : 'Paused'])

  if (kind === 'email') {
    cells.push(['Trigger name', email.integrationName || '—'])
    cells.push(['Gmail account', email.account || '—'])
    cells.push(['Search query', email.query.trim() || 'Whole inbox'])
    cells.push(['Poll interval', `${email.pollSeconds}s`])
  } else if (kind === 'webhook') {
    cells.push(['Integration name', webhook.integrationName || '—'])
    cells.push(['Callback URL', webhook.callbackUrl || '—'])
    cells.push(['Callback enabled', webhook.callbackEnabled ? 'Yes' : 'No'])
    cells.push(['Rate limit', `${webhook.rateLimit} rpm`])
    cells.push(['IP allowlist', webhook.ipAllowlist.trim() ? webhook.ipAllowlist.trim() : 'Any source'])
  } else if (kind === 'jira') {
    cells.push(['Trigger name', jira.integrationName || '—'])
    cells.push(['Connection', jira.connection || '—'])
    cells.push(['Project key', jira.projectKey || 'Any'])
    cells.push(['JQL', jira.jql.trim() || '—'])
    cells.push(['Poll interval', `${jira.pollSeconds}s`])
  } else if (kind === 'github') {
    cells.push(['Trigger name', github.integrationName || '—'])
    cells.push(['Repository', github.repoOwner && github.repoName ? `${github.repoOwner}/${github.repoName}` : '—'])
    cells.push(['Hub integration', github.integrationId ? `#${github.integrationId}` : '— (required)'])
    cells.push(['Events', github.events.length > 0 ? github.events.join(', ') : '—'])
    cells.push(['PR actions', github.prActions.length > 0 ? github.prActions.join(', ') : '—'])
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {cells.map(([label, value]) => (
        <div key={label} className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">{label}</div>
          <div className="mt-2 break-words text-sm text-white">{value}</div>
        </div>
      ))}
    </div>
  )
}

interface PostSaveSummaryProps {
  kind: TriggerId
  savedTrigger: SavedTriggerAny
  autoFlowId: number | null
  webhookSecret: string | null
  secretCopied: boolean
  onCopySecret: () => void
}

function PostSaveSummary({
  kind,
  savedTrigger,
  autoFlowId,
  webhookSecret,
  secretCopied,
  onCopySecret,
}: PostSaveSummaryProps) {
  const summaryRows: Array<[string, string]> = []
  summaryRows.push(['Trigger', triggerLabel(savedTrigger)])
  summaryRows.push(['Status', triggerActiveLabel(savedTrigger)])
  if (kind === 'email') {
    const email = savedTrigger as EmailTrigger
    summaryRows.push(['Account', email.gmail_account_email || '—'])
    summaryRows.push(['Query', email.search_query || 'Whole inbox'])
    summaryRows.push(['Poll interval', `${email.poll_interval_seconds}s`])
  } else if (kind === 'webhook') {
    const webhook = savedTrigger as WebhookIntegration
    summaryRows.push(['Inbound URL', webhook.inbound_url])
    summaryRows.push(['Callback', webhook.callback_enabled ? webhook.callback_url || '(enabled)' : 'Disabled'])
    summaryRows.push(['Rate limit', `${webhook.rate_limit_rpm} rpm`])
  } else if (kind === 'jira') {
    const jira = savedTrigger as JiraTrigger
    summaryRows.push(['Connection', jira.jira_integration_name || jira.site_url || '—'])
    summaryRows.push(['JQL', jira.jql || '—'])
    summaryRows.push(['Project key', jira.project_key || 'Any'])
    summaryRows.push(['Poll interval', `${jira.poll_interval_seconds}s`])
  } else if (kind === 'github') {
    const github = savedTrigger as GitHubTrigger
    summaryRows.push(['Repository', `${github.repo_owner}/${github.repo_name}`])
    summaryRows.push(['Hub integration', github.github_integration_name || `#${github.github_integration_id}`])
    summaryRows.push(['Events', (github.events || []).join(', ') || '—'])
    if (github.inbound_url) summaryRows.push(['Inbound URL', github.inbound_url])
  }
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
        <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Saved trigger</div>
        <div className="mt-3 grid gap-2 text-sm text-tsushin-slate">
          {summaryRows.map(([label, value]) => (
            <div key={label}>
              <span className="text-white">{label}:</span> {value}
            </div>
          ))}
        </div>
      </div>

      {kind === 'webhook' && webhookSecret && (
        <div className="rounded-2xl border border-cyan-500/30 bg-cyan-500/10 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-cyan-100">HMAC secret (shown once)</div>
              <p className="mt-1 text-xs text-cyan-100/80">
                Store this now — it will not be shown again. Use it to sign inbound webhook requests.
              </p>
            </div>
            <button
              type="button"
              onClick={onCopySecret}
              className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500"
            >
              {secretCopied ? 'Copied!' : 'Copy secret'}
            </button>
          </div>
          <div className="mt-3 break-all rounded-lg bg-black/40 px-3 py-2 font-mono text-xs text-cyan-100">
            {webhookSecret}
          </div>
        </div>
      )}

      {autoFlowId !== null ? (
        <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4">
          <div className="text-xs uppercase tracking-[0.18em] text-emerald-200">Wired flow</div>
          <p className="mt-2 text-sm text-emerald-50">
            An auto-generated flow (ID #{autoFlowId}) is wired to this trigger. Open the Flow editor to inspect or
            customize the matching and routing logic.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4 text-sm text-tsushin-slate">
          Wired flow not generated for this trigger (auto-flow generation may be disabled in Settings).
        </div>
      )}
    </div>
  )
}
