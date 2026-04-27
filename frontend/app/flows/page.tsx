'use client'

/**
 * Unified Flows Page
 *
 * Phase 8.0: Consolidated flow management supporting:
 * - Notification, Message, Conversation, and Task flows
 * - One-shot and scheduled execution methods
 * - Multi-step flows with dynamic step builder
 * - Multi-turn conversation support within flow steps
 *
 * UI: List view with sortable columns for better organization
 */

import { useState, useEffect, useCallback, useMemo, useRef, type MouseEvent } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useToast } from '@/contexts/ToastContext'
import { useAuth } from '@/contexts/AuthContext'
import {
  api,
  type FlowDefinition,
  type FlowNode,
  type FlowRun,
  type Agent,
  type Contact,
  type Persona,
  type ConversationThread,
  type CreateFlowData,
  type CreateFlowStepData,
  type ExecutionMethod,
  type FlowType,
  type StepType,
  type CustomTool,
  type EditableStepData,
  type FlowStepConfig,
  type TriggerKind,
  flowNodeToEditable,
  editableToUpdatePayload,
  editableToCreatePayload
} from '@/lib/client'
import FlowsStatCards from '@/components/flows/FlowsStatCards'
import TemplateTextarea from '@/components/flows/TemplateTextarea'
import TemplateInput from '@/components/flows/TemplateInput'
import SourceStepConfig from '@/components/flows/SourceStepConfig'
import {
  MessageIcon,
  BellIcon,
  LightningIcon,
  ZapIcon,
  WrenchIcon,
  PlayIcon,
  CalendarIcon,
  RefreshIcon,
  HashIcon,
  EnvelopeIcon,
  BrainIcon,
  DocumentIcon,
  CommandIcon,
  PlaneIcon,
  SearchIcon,
  GlobeIcon,
  CalendarDaysIcon,
  MailIcon,
  BookOpenIcon,
  WhatsAppIcon,
  TelegramIcon,
  SlackIcon,
  DiscordIcon,
  WebhookIcon,
  LightbulbIcon,
  FileTextIcon,
  ClipboardIcon,
  ShieldCheckIcon,
  CodeIcon,
  GitHubIcon,
  type IconProps
} from '@/components/ui/icons'
import { parseUTCTimestamp, formatRelative as formatRelativeUtil } from '@/lib/dateUtils'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import CreateFromTemplateModal from '@/components/flows/CreateFromTemplateModal'

// ==================== CONSTANTS ====================

const FLOW_TYPES: { value: FlowType; label: string; Icon: React.FC<IconProps>; description: string; color: string }[] = [
  { value: 'conversation', label: 'Conversation', Icon: MessageIcon, description: 'Multi-turn dialogue with a recipient', color: 'emerald' },
  { value: 'notification', label: 'Notification', Icon: BellIcon, description: 'One-way message or reminder', color: 'amber' },
  { value: 'workflow', label: 'Workflow', Icon: LightningIcon, description: 'Multi-step automated process', color: 'violet' },
  { value: 'task', label: 'Task', Icon: WrenchIcon, description: 'Execute a specific tool or action', color: 'sky' },
]

const EXECUTION_METHODS: { value: ExecutionMethod; label: string; Icon: React.FC<IconProps> }[] = [
  { value: 'immediate', label: 'Immediate', Icon: PlayIcon },
  { value: 'scheduled', label: 'Scheduled', Icon: CalendarIcon },
  { value: 'recurring', label: 'Recurring', Icon: RefreshIcon },
  { value: 'keyword', label: 'Keyword', Icon: HashIcon },  // BUG-336
  { value: 'triggered', label: 'Triggered', Icon: ZapIcon },  // v0.7.0 Wave 2: Triggers \u2194 Flows unification
]

const STEP_TYPES: { value: StepType; label: string; Icon: React.FC<IconProps>; description: string }[] = [
  // v0.7.0 Wave 2: 'source' step is locked at position 0, max 1 per flow.
  // The dropdown filters this out when a source step already exists; the
  // step row hides Delete + reorder buttons when type === 'source'.
  { value: 'source', label: 'Source', Icon: ZapIcon, description: 'Trigger event that wakes this flow' },
  { value: 'conversation', label: 'Conversation', Icon: MessageIcon, description: 'Multi-turn dialogue step' },
  { value: 'message', label: 'Message', Icon: EnvelopeIcon, description: 'Send a single message' },
  { value: 'notification', label: 'Notification', Icon: BellIcon, description: 'Send a notification' },
  { value: 'tool', label: 'Tool', Icon: WrenchIcon, description: 'Execute a tool or action' },
  { value: 'skill', label: 'Skill', Icon: BrainIcon, description: 'Execute an agentic skill (flight search, web search, etc.)' },
  { value: 'summarization', label: 'Summarization', Icon: DocumentIcon, description: 'AI-powered summary of conversation' },
  { value: 'slash_command', label: 'Slash Command', Icon: CommandIcon, description: 'Execute a slash command (/scheduler, /memory, etc.)' },
  { value: 'gate', label: 'Gate', Icon: ShieldCheckIcon, description: 'Conditional check \u2014 block or pass' },
]

const CHANNEL_OPTIONS: { value: 'whatsapp' | 'telegram' | 'slack' | 'discord' | 'webhook'; label: string; Icon: React.FC<IconProps>; activeColor: string; enabled: boolean; badge?: string }[] = [
  { value: 'whatsapp', label: 'WhatsApp', Icon: WhatsAppIcon, activeColor: 'text-green-400', enabled: true },
  { value: 'telegram', label: 'Telegram', Icon: TelegramIcon, activeColor: 'text-blue-400', enabled: true },
  { value: 'slack', label: 'Slack', Icon: SlackIcon, activeColor: 'text-purple-400', enabled: true },
  { value: 'discord', label: 'Discord', Icon: DiscordIcon, activeColor: 'text-indigo-400', enabled: true },
  { value: 'webhook', label: 'Webhook', Icon: WebhookIcon, activeColor: 'text-cyan-400', enabled: true },
]

// Summarization output format options
const SUMMARIZATION_OUTPUT_FORMATS = [
  { value: 'brief', label: 'Brief', description: 'Concise 2-3 sentence summary' },
  { value: 'detailed', label: 'Detailed', description: 'Comprehensive with key points' },
  { value: 'structured', label: 'Structured', description: 'Sections: Objective, Key Points, Outcome' },
  { value: 'minimal', label: 'Minimal', description: 'Just essential data points, no analysis' },
]

// Summarization prompt modes
const SUMMARIZATION_PROMPT_MODES = [
  { value: 'append', label: 'Append', description: 'Add to default template' },
  { value: 'replace', label: 'Replace', description: 'Use as full prompt (complete control)' },
]

// AI models for summarization
const SUMMARIZATION_MODELS = [
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash (fast)' },
  { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
  { value: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro (quality)' },
]

// Available agent skills for the skill step type
const AVAILABLE_SKILLS: { value: string; label: string; Icon: React.FC<IconProps>; description: string }[] = [
  { value: 'flight_search', label: 'Flight Search', Icon: PlaneIcon, description: 'Search for flights using natural language' },
  { value: 'web_search', label: 'Web Search', Icon: SearchIcon, description: 'Search the web for information' },
  { value: 'scheduler', label: 'Scheduler', Icon: CalendarIcon, description: 'Manage calendar events and reminders' },
  { value: 'scheduler_query', label: 'Scheduler Query', Icon: CalendarDaysIcon, description: 'Query calendar events' },
  { value: 'gmail', label: 'Gmail', Icon: MailIcon, description: 'Send and manage emails' },
  { value: 'knowledge_sharing', label: 'Knowledge Sharing', Icon: BookOpenIcon, description: 'Share knowledge base content' },
  { value: 'flows', label: 'Flows', Icon: RefreshIcon, description: 'Trigger and manage flows' },
  { value: 'automation', label: 'Automation', Icon: LightningIcon, description: 'Execute automation tasks' },
]

type SortField = 'id' | 'name' | 'flow_type' | 'is_active' | 'node_count' | 'execution_method' | 'updated_at' | 'last_executed_at'
type SortDirection = 'asc' | 'desc'

// ==================== MAIN PAGE ====================

export default function FlowsPage() {
  const toast = useToast()
  const router = useRouter()
  const searchParams = useSearchParams()
  // BUG-610 FIX: Gate every write control (Create, From Template, Edit,
  // Run, Delete, Bulk actions) on flows.write so a read-only user gets
  // a clean list view instead of buttons that 403 on click.
  const { hasPermission } = useAuth()
  const canWriteFlows = hasPermission('flows.write')
  const [allFlows, setAllFlows] = useState<FlowDefinition[]>([])
  const [runs, setRuns] = useState<FlowRun[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [customTools, setCustomTools] = useState<CustomTool[]>([])
  const [customSkills, setCustomSkills] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  // Filter & Search states
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<FlowType | ''>('')
  const [statusFilter, setStatusFilter] = useState<'enabled' | 'disabled' | ''>('')
  const [executionFilter, setExecutionFilter] = useState<ExecutionMethod | ''>('')

  // Sort states
  const [sortField, setSortField] = useState<SortField>('updated_at')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  // Modal states
  const [showCreateFlow, setShowCreateFlow] = useState(false)
  const [showCreateFromTemplate, setShowCreateFromTemplate] = useState(false)
  const [editingFlowId, setEditingFlowId] = useState<number | null>(null)
  const [viewingRunId, setViewingRunId] = useState<number | null>(null)
  const [executingFlowId, setExecutingFlowId] = useState<number | null>(null)
  const [activeThreads, setActiveThreads] = useState<ConversationThread[]>([])

  // Pagination
  const [currentPage, setCurrentPage] = useState(1)
  const [totalFlows, setTotalFlows] = useState(0)
  const [pageSize, setPageSize] = useState<number>(25)
  const PAGE_SIZE = pageSize
  const PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

  // Selected rows for bulk actions
  const [selectedFlows, setSelectedFlows] = useState<Set<number>>(new Set())
  const [bulkActionLoading, setBulkActionLoading] = useState(false)

  // v0.7.0 Wave 4: deep-link prefill for "Create flow from this trigger".
  // The trigger detail page lives at /hub/triggers/{kind}/{id} and CTAs link to
  //   /flows?source_trigger_kind={kind}&source_trigger_id={id}
  // When both params are present and valid we auto-open the Create modal,
  // pre-fill execution_method='triggered', and insert a Source step at
  // position 0 with the trigger binding baked into config_json.
  const prefillKindParam = searchParams?.get('source_trigger_kind') as TriggerKind | null
  const prefillTriggerIdParam = Number(searchParams?.get('source_trigger_id') || '')
  const prefillKind: TriggerKind | null =
    prefillKindParam && ['jira', 'email', 'github', 'schedule', 'webhook'].includes(prefillKindParam)
      ? prefillKindParam
      : null
  const prefillTriggerId =
    Number.isFinite(prefillTriggerIdParam) && prefillTriggerIdParam > 0 ? prefillTriggerIdParam : 0
  const prefillReady = Boolean(prefillKind && prefillTriggerId > 0)

  const [prefillTriggerName, setPrefillTriggerName] = useState<string>('')
  const [prefillTriggerLoaded, setPrefillTriggerLoaded] = useState(false)
  const prefillConsumedRef = useRef(false)

  // ?edit={flow_id} deep link from Wired Flows rows: open the EditFlowModal
  const editParamRaw = searchParams?.get('edit') || ''
  const editParam = Number(editParamRaw)
  const editParamValid = Number.isFinite(editParam) && editParam > 0
  const editConsumedRef = useRef(false)

  useEffect(() => {
    if (!editParamValid) return
    if (editConsumedRef.current) return
    editConsumedRef.current = true
    setEditingFlowId(editParam)
    // Strip ?edit= so back/forward + refresh don't re-trigger the modal.
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.delete('edit')
      window.history.replaceState(null, '', url.toString())
    }
  }, [editParamValid, editParam])

  useEffect(() => {
    let cancelled = false
    if (!prefillReady || !prefillKind) return
    setPrefillTriggerLoaded(false)
    api.getTriggerDetail(prefillKind, prefillTriggerId)
      .then((d) => {
        if (cancelled) return
        const name = (d as { integration_name?: string }).integration_name || ''
        setPrefillTriggerName(name)
        setPrefillTriggerLoaded(true)
      })
      .catch(() => {
        if (cancelled) return
        setPrefillTriggerName('')
        setPrefillTriggerLoaded(true)
      })
    return () => { cancelled = true }
  }, [prefillReady, prefillKind, prefillTriggerId])

  useEffect(() => {
    if (!prefillReady) return
    if (prefillConsumedRef.current) return
    if (!canWriteFlows) {
      // Read-only users can't create flows; surface a toast and clear the params.
      toast.warning('Insufficient permissions', 'You need flows.write to create flows from a trigger.')
      prefillConsumedRef.current = true
      return
    }
    // Wait for trigger name to resolve so the auto-filled flow name carries
    // the integration label rather than `${Kind} #${id}`.
    if (!prefillTriggerLoaded) return
    prefillConsumedRef.current = true
    setShowCreateFlow(true)
  }, [prefillReady, canWriteFlows, prefillTriggerLoaded, toast])

  function clearPrefillParams() {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    url.searchParams.delete('source_trigger_kind')
    url.searchParams.delete('source_trigger_id')
    window.history.replaceState(null, '', url.toString())
  }

  useEffect(() => {
    loadData()
  }, [currentPage, pageSize])

  useGlobalRefresh(() => loadData())

  async function loadData() {
    setLoading(true)
    try {
      const [flowsData, runsData, agentsData, contactsData, personasData, customToolsData, customSkillsData] = await Promise.allSettled([
        api.getFlows({ limit: PAGE_SIZE, offset: (currentPage - 1) * PAGE_SIZE }),
        api.getFlowRuns(undefined, 20),
        api.getAgents(true),
        api.getContacts(),
        api.getPersonas(),
        api.getSandboxedTools(),
        api.getCustomSkills()
      ])

      if (flowsData.status === 'fulfilled') {
        // Auto-correct pagination: if current page is now past the last page
        // (e.g., after deletion), snap back and let useEffect re-fetch the right
        // window — do not overwrite list with empty results in the meantime.
        const total = flowsData.value.total
        const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE))
        if (currentPage > lastPage) {
          setTotalFlows(total)
          setCurrentPage(lastPage)
        } else {
          setAllFlows(flowsData.value.items)
          setTotalFlows(total)
        }
      }
      if (runsData.status === 'fulfilled') setRuns(runsData.value)
      if (agentsData.status === 'fulfilled') setAgents(agentsData.value)
      if (contactsData.status === 'fulfilled') setContacts(contactsData.value)
      if (personasData.status === 'fulfilled') setPersonas(personasData.value.filter((p: Persona) => p.is_active))
      if (customToolsData.status === 'fulfilled') setCustomTools(customToolsData.value.filter((t: CustomTool) => t.is_enabled))
      if (customSkillsData.status === 'fulfilled') setCustomSkills(customSkillsData.value.filter((s: any) => s.is_enabled && s.scan_status === 'clean'))

      // Load active conversation threads (silent catch - non-critical data)
      const threads = await api.getActiveConversationThreads().catch(() => [])
      setActiveThreads(threads)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  // Filtered and sorted flows
  const flows = useMemo(() => {
    let result = [...allFlows]

    // Apply search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      result = result.filter(f =>
        f.name.toLowerCase().includes(query) ||
        f.description?.toLowerCase().includes(query)
      )
    }

    // Apply type filter
    if (typeFilter) {
      result = result.filter(f => f.flow_type === typeFilter)
    }

    // Apply status filter
    if (statusFilter) {
      result = result.filter(f => statusFilter === 'enabled' ? f.is_active : !f.is_active)
    }

    // Apply execution method filter
    if (executionFilter) {
      result = result.filter(f => f.execution_method === executionFilter)
    }

    // Apply sorting
    result.sort((a, b) => {
      let aVal: any, bVal: any

      switch (sortField) {
        case 'name':
          aVal = a.name.toLowerCase()
          bVal = b.name.toLowerCase()
          break
        case 'flow_type':
          aVal = a.flow_type || ''
          bVal = b.flow_type || ''
          break
        case 'is_active':
          aVal = a.is_active ? 1 : 0
          bVal = b.is_active ? 1 : 0
          break
        case 'node_count':
          aVal = a.node_count || 0
          bVal = b.node_count || 0
          break
        case 'execution_method':
          aVal = a.execution_method || ''
          bVal = b.execution_method || ''
          break
        case 'updated_at':
          aVal = new Date(a.updated_at).getTime()
          bVal = new Date(b.updated_at).getTime()
          break
        case 'last_executed_at':
          aVal = a.last_executed_at ? new Date(a.last_executed_at).getTime() : 0
          bVal = b.last_executed_at ? new Date(b.last_executed_at).getTime() : 0
          break
        default:
          aVal = 0
          bVal = 0
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1
      return 0
    })

    return result
  }, [allFlows, searchQuery, typeFilter, statusFilter, executionFilter, sortField, sortDirection])

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  function clearFilters() {
    setSearchQuery('')
    setTypeFilter('')
    setStatusFilter('')
    setExecutionFilter('')
  }

  const hasActiveFilters = searchQuery || typeFilter || statusFilter || executionFilter

  async function handleDeleteFlow(flowId: number) {
    if (!confirm('Delete this flow? This cannot be undone.')) return
    try {
      await api.deleteFlow(flowId, false)
      await loadData()
    } catch (error: any) {
      console.error('Failed to delete flow:', error)
      const errorMessage = error?.message || 'Failed to delete flow'

      // Check if error is about existing runs
      if (errorMessage.includes('existing run')) {
        const forceDelete = confirm(
          `${errorMessage}\n\nDo you want to force delete this flow? This will also delete all run history.`
        )
        if (forceDelete) {
          try {
            await api.deleteFlow(flowId, true)
            await loadData()
          } catch (forceError: any) {
            console.error('Failed to force delete flow:', forceError)
            toast.error('Delete Failed', `Failed to delete flow: ${forceError?.message || 'Unknown error'}`)
          }
        }
      } else {
        toast.error('Delete Failed', `Failed to delete flow: ${errorMessage}`)
      }
    }
  }

  async function handleRunFlow(flowId: number) {
    setExecutingFlowId(flowId)
    try {
      // BUG-636 FIX: When the user opens a flow in the editor, saves a
      // change, closes the modal, then immediately clicks Run — the row
      // in our local ``allFlows`` state can still reflect the PRE-save
      // is_active / node_count / step graph because ``loadData()`` is
      // async and races against the Run click. Previously that race
      // produced "no run" because executeFlow 400'd on the stale graph
      // but we toasted a generic error and never refreshed. Re-fetch the
      // freshest server-side copy BEFORE kicking off the run so the
      // backend sees the just-saved definition and executes against it.
      try {
        const latest = await api.getFlow(flowId)
        setAllFlows(prev => prev.map(f => (f.id === flowId ? { ...f, ...latest } : f)))
        if (latest.is_active === false) {
          toast.error('Execution Failed', 'This flow is disabled — enable it to run.')
          return
        }
      } catch (refreshErr) {
        // Non-fatal — if the refresh call itself fails we still try the
        // execute path; worst case the backend 4xxs on its own validation.
        console.warn('handleRunFlow: pre-execute refresh failed', refreshErr)
      }
      const run = await api.executeFlow(flowId)
      setViewingRunId(run.id)
      loadData()
    } catch (error) {
      console.error('Failed to run flow:', error)
      toast.error('Execution Failed', 'Failed to run flow')
    } finally {
      setExecutingFlowId(null)
    }
  }

  async function handleToggleActive(flow: FlowDefinition) {
    try {
      await api.patchFlow(flow.id, { is_active: !flow.is_active })
      await loadData()
    } catch (error) {
      console.error('Failed to toggle flow status:', error)
      toast.error('Toggle Failed', 'Failed to toggle flow status')
    }
  }

  async function handleBulkSetActive(active: boolean) {
    if (selectedFlows.size === 0) return
    setBulkActionLoading(true)
    const ids = Array.from(selectedFlows)
    let success = 0
    let failed = 0
    for (const id of ids) {
      try {
        await api.patchFlow(id, { is_active: active })
        success++
      } catch (error) {
        console.error(`Failed to ${active ? 'enable' : 'disable'} flow ${id}:`, error)
        failed++
      }
    }
    setBulkActionLoading(false)
    setSelectedFlows(new Set())
    if (failed === 0) {
      toast.success(
        active ? 'Flows Enabled' : 'Flows Disabled',
        `${success} flow${success === 1 ? '' : 's'} ${active ? 'enabled' : 'disabled'}`
      )
    } else {
      toast.error('Bulk Action Partial', `${success} succeeded, ${failed} failed`)
    }
    await loadData()
  }

  async function handleBulkDelete() {
    if (selectedFlows.size === 0) return
    const count = selectedFlows.size
    if (!confirm(`Delete ${count} flow${count === 1 ? '' : 's'}? This cannot be undone.`)) return
    setBulkActionLoading(true)
    const ids = Array.from(selectedFlows)
    let success = 0
    let failed = 0
    let needsForce: number[] = []
    for (const id of ids) {
      try {
        await api.deleteFlow(id, false)
        success++
      } catch (error: any) {
        const errorMessage = error?.message || ''
        if (errorMessage.includes('existing run')) {
          needsForce.push(id)
        } else {
          console.error(`Failed to delete flow ${id}:`, error)
          failed++
        }
      }
    }
    if (needsForce.length > 0) {
      const forceDelete = confirm(
        `${needsForce.length} flow${needsForce.length === 1 ? ' has' : 's have'} existing runs.\n\nForce delete ${needsForce.length === 1 ? 'it' : 'them'}? This will also delete all run history.`
      )
      if (forceDelete) {
        for (const id of needsForce) {
          try {
            await api.deleteFlow(id, true)
            success++
          } catch (forceError) {
            console.error(`Failed to force delete flow ${id}:`, forceError)
            failed++
          }
        }
      }
    }
    setBulkActionLoading(false)
    setSelectedFlows(new Set())
    if (failed === 0) {
      toast.success('Flows Deleted', `${success} flow${success === 1 ? '' : 's'} deleted`)
    } else {
      toast.error('Bulk Delete Partial', `${success} deleted, ${failed} failed`)
    }
    await loadData()
  }

  async function handleCancelRun(runId: number) {
    if (!confirm('Cancel this flow run?')) return
    try {
      await api.cancelFlowRun(runId)
      await loadData()
    } catch (error) {
      console.error('Failed to cancel run:', error)
      toast.error('Cancel Failed', 'Failed to cancel run')
    }
  }

  const totalPages = Math.ceil(totalFlows / PAGE_SIZE)

  // Stats calculation (based on all flows, not filtered)
  const stats = {
    totalFlows: totalFlows,
    activeFlows: allFlows.filter(f => f.is_active).length, // Enabled flows (current page)
    inactiveFlows: allFlows.filter(f => !f.is_active).length, // Disabled flows (current page)
    totalRuns: runs.length,
    runningRuns: runs.filter(r => r.status === 'running').length,
    activeThreads: activeThreads.length,
    byType: FLOW_TYPES.reduce((acc, type) => {
      acc[type.value] = allFlows.filter(f => f.flow_type === type.value).length
      return acc
    }, {} as Record<string, number>),
    filteredCount: flows.length
  }

  if (loading && allFlows.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold text-white mb-4">Flows</h1>
          <div className="flex items-center gap-3 text-slate-400">
            <div className="animate-spin h-5 w-5 border-2 border-teal-500 border-t-transparent rounded-full"></div>
            Loading flows...
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      <div className="max-w-[1600px] mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-teal-400 to-cyan-300 bg-clip-text text-transparent tracking-tight">
              Flows
            </h1>
            <p className="text-slate-500 mt-1 text-sm">Manage automated workflows, conversations, and notifications</p>
          </div>
          {canWriteFlows && (
            <div className="flex items-center gap-3">
              {/* From Template Button */}
              <button
                onClick={() => setShowCreateFromTemplate(true)}
                className="px-4 py-2.5 bg-teal-500/10 text-teal-300 border border-teal-500/30 font-medium rounded-lg
                           hover:bg-teal-500/15 hover:border-teal-500/50 transition-all
                           flex items-center gap-2"
                title="Create a flow from a pre-built hybrid automation template"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                From Template
              </button>
              {/* New Flow Button */}
              <button
                onClick={() => setShowCreateFlow(true)}
                className="px-5 py-2.5 bg-gradient-to-r from-teal-500 to-cyan-500 text-white font-medium rounded-lg
                           hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/20
                           flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                New Flow
              </button>
            </div>
          )}
        </div>

        {/* Enterprise Stat Cards */}
        <FlowsStatCards
          stats={stats}
          typeFilter={typeFilter}
          statusFilter={statusFilter}
          onTypeFilterChange={setTypeFilter}
          onStatusFilterChange={setStatusFilter}
          loading={loading}
        />

        {/* Search and Filters Bar */}
        <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl border border-slate-800 p-4">
          <div className="flex flex-wrap gap-4 items-center">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Search flows..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-white text-sm
                           placeholder-slate-500 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none"
              />
            </div>

            {/* Type Filter */}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as FlowType | '')}
              className="px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-300 text-sm
                         focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none min-w-[140px]"
            >
              <option value="">All Types</option>
              {FLOW_TYPES.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>

            {/* Execution Filter */}
            <select
              value={executionFilter}
              onChange={(e) => setExecutionFilter(e.target.value as ExecutionMethod | '')}
              className="px-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-300 text-sm
                         focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none min-w-[140px]"
            >
              <option value="">All Execution</option>
              {EXECUTION_METHODS.map(method => (
                <option key={method.value} value={method.value}>{method.label}</option>
              ))}
            </select>

            {/* Clear Filters */}
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="px-3 py-2 text-sm text-slate-400 hover:text-white transition-colors flex items-center gap-1"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                Clear
              </button>
            )}

            {/* Spacer to push filters left when no refresh button */}
            <div className="ml-auto" />
          </div>

          {/* Results count */}
          {hasActiveFilters && (
            <div className="mt-3 text-sm text-slate-500">
              Showing {flows.length} of {stats.totalFlows} flows
            </div>
          )}
        </div>

        {/* Flows List Table */}
        <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl border border-slate-800 overflow-hidden">
          {flows.length === 0 ? (
            <div className="p-16 text-center">
              {allFlows.length === 0 ? (
                <>
                  <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-teal-500/20 to-cyan-500/20 flex items-center justify-center">
                    <svg className="w-10 h-10 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  </div>
                  <h3 className="text-xl font-semibold text-white mb-2">No flows yet</h3>
                  <p className="text-slate-500 mb-6 max-w-md mx-auto">
                    Create your first automated workflow to start managing conversations and tasks
                  </p>
                  {canWriteFlows && (
                    <button
                      onClick={() => setShowCreateFlow(true)}
                      className="px-5 py-2.5 bg-gradient-to-r from-teal-500 to-cyan-500 text-white font-medium rounded-lg
                                 hover:from-teal-400 hover:to-cyan-400 transition-all"
                    >
                      Create Your First Flow
                    </button>
                  )}
                </>
              ) : (
                <>
                  <div className="mb-4"><SearchIcon size={40} className="text-slate-500 mx-auto" /></div>
                  <h3 className="text-lg font-semibold text-white mb-2">No flows match your filters</h3>
                  <p className="text-slate-500 mb-4">Try adjusting your search or filter criteria</p>
                  <button
                    onClick={clearFilters}
                    className="px-4 py-2 text-teal-400 hover:text-teal-300 transition-colors"
                  >
                    Clear all filters
                  </button>
                </>
              )}
            </div>
          ) : (
            <>
            {/* Bulk Actions Bar */}
            {selectedFlows.size > 0 && (
              <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/50 bg-teal-500/5">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-teal-300 font-medium">
                    {selectedFlows.size} selected
                  </span>
                  <button
                    onClick={() => setSelectedFlows(new Set())}
                    className="text-xs text-slate-400 hover:text-white transition-colors"
                  >
                    Clear selection
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleBulkSetActive(true)}
                    disabled={bulkActionLoading}
                    className="px-3 py-1.5 text-sm rounded-lg border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Enable
                  </button>
                  <button
                    onClick={() => handleBulkSetActive(false)}
                    disabled={bulkActionLoading}
                    className="px-3 py-1.5 text-sm rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Disable
                  </button>
                  <button
                    onClick={handleBulkDelete}
                    disabled={bulkActionLoading}
                    className="px-3 py-1.5 text-sm rounded-lg border border-red-500/30 text-red-300 hover:bg-red-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/50">
                    <th className="w-12 px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedFlows.size === flows.length && flows.length > 0}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedFlows(new Set(flows.map(f => f.id)))
                          } else {
                            setSelectedFlows(new Set())
                          }
                        }}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-teal-500 focus:ring-teal-500"
                      />
                    </th>
                    <SortableHeader field="id" label="ID" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="name" label="Flow" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="flow_type" label="Type" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="is_active" label="Flow Status" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="node_count" label="Steps" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="execution_method" label="Execution" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="last_executed_at" label="Last Run" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <SortableHeader field="updated_at" label="Updated" currentField={sortField} direction={sortDirection} onSort={handleSort} />
                    <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {flows.map(flow => {
                    const typeInfo = FLOW_TYPES.find(t => t.value === flow.flow_type) || FLOW_TYPES[0]
                    const threadCount = activeThreads.filter(t => t.flow_definition_id === flow.id).length

                    return (
                      <tr
                        key={flow.id}
                        className={`group hover:bg-slate-800/30 transition-colors ${selectedFlows.has(flow.id) ? 'bg-teal-500/5' : ''
                          }`}
                      >
                        <td className="px-4 py-4">
                          <input
                            type="checkbox"
                            checked={selectedFlows.has(flow.id)}
                            onChange={(e) => {
                              const newSelected = new Set(selectedFlows)
                              if (e.target.checked) {
                                newSelected.add(flow.id)
                              } else {
                                newSelected.delete(flow.id)
                              }
                              setSelectedFlows(newSelected)
                            }}
                            className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-teal-500 focus:ring-teal-500"
                          />
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-slate-400 font-mono">{flow.id}</span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-medium text-white group-hover:text-teal-400 transition-colors">
                                  {flow.name}
                                </span>
                                <TriggerOriginBadge flow={flow} />
                                {threadCount > 0 && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                                    <span className="relative flex h-1.5 w-1.5">
                                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                                    </span>
                                    {threadCount}
                                  </span>
                                )}
                              </div>
                              {flow.description && (
                                <p className="text-sm text-slate-500 truncate max-w-md">{flow.description}</p>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <TypeBadge type={flow.flow_type || 'workflow'} />
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => canWriteFlows && handleToggleActive(flow)}
                              disabled={!canWriteFlows}
                              title={canWriteFlows ? (flow.is_active ? 'Click to disable' : 'Click to enable') : 'Requires flows.write permission'}
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-all ${flow.is_active
                                  ? 'bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25'
                                  : 'bg-slate-700/50 text-slate-400 hover:bg-slate-700'
                                } ${!canWriteFlows ? 'opacity-60 cursor-not-allowed' : ''}`}
                            >
                              <span className={`w-1.5 h-1.5 rounded-full ${flow.is_active ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                              {flow.is_active ? 'Enabled' : 'Disabled'}
                            </button>
                            {(() => {
                              const threadCount = activeThreads.filter(t => t.flow_definition_id === flow.id).length
                              return threadCount > 0 ? (
                                <span className="px-2 py-0.5 bg-green-500/20 text-green-400 text-xs rounded-full flex items-center gap-1" title={`${threadCount} active conversation(s)`}>
                                  <span className="relative flex h-1.5 w-1.5">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500"></span>
                                  </span>
                                  {threadCount}
                                </span>
                              ) : null
                            })()}
                          </div>
                        </td>
                        <td className="px-4 py-4 text-center">
                          <span className="text-sm text-slate-400">{flow.node_count || 0}</span>
                        </td>
                        <td className="px-4 py-4">
                          <ExecutionBadge method={flow.execution_method || 'immediate'} />
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-slate-500">
                            {flow.last_executed_at ? formatRelativeDate(flow.last_executed_at) : '—'}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-slate-500">{formatRelativeDate(flow.updated_at)}</span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            {canWriteFlows && (
                              <>
                                <button
                                  onClick={() => setEditingFlowId(flow.id)}
                                  className="p-2 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
                                  title="Edit"
                                >
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                  </svg>
                                </button>
                                <button
                                  onClick={() => handleRunFlow(flow.id)}
                                  disabled={!flow.is_active || (flow.node_count || 0) === 0 || executingFlowId === flow.id}
                                  className="p-2 text-teal-400 hover:text-teal-300 hover:bg-teal-500/10 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                                  title="Run"
                                >
                                  {executingFlowId === flow.id ? (
                                    <div className="w-4 h-4 border-2 border-teal-400 border-t-transparent rounded-full animate-spin" />
                                  ) : (
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                    </svg>
                                  )}
                                </button>
                                {(() => {
                                  const canDelete = flow.deletable_by_tenant !== false
                                  return (
                                    <button
                                      onClick={() => canDelete && handleDeleteFlow(flow.id)}
                                      disabled={!canDelete}
                                      className={`p-2 rounded-lg transition-colors ${
                                        canDelete
                                          ? 'text-red-400 hover:text-red-300 hover:bg-red-500/10'
                                          : 'text-red-400/30 cursor-not-allowed'
                                      }`}
                                      title={
                                        canDelete
                                          ? 'Delete'
                                          : 'Auto-generated from a trigger — delete the trigger to remove this flow.'
                                      }
                                    >
                                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                      </svg>
                                    </button>
                                  )
                                })()}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-800/50 flex-wrap gap-3">
              <div className="flex items-center gap-4 flex-wrap">
                <div className="text-sm text-slate-400">
                  Showing {totalFlows === 0 ? 0 : ((currentPage - 1) * PAGE_SIZE) + 1}–{Math.min(currentPage * PAGE_SIZE, totalFlows)} of {totalFlows} flows
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-sm text-slate-500">Per page:</label>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value))
                      setCurrentPage(1)
                      setSelectedFlows(new Set())
                    }}
                    className="px-2 py-1 bg-slate-800/50 border border-slate-700 rounded-lg text-slate-300 text-sm focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none"
                  >
                    {PAGE_SIZE_OPTIONS.map(opt => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                </div>
              </div>
              {totalPages > 1 && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="px-3 py-1.5 text-sm rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Previous
                  </button>
                  {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                    let page: number
                    if (totalPages <= 7) {
                      page = i + 1
                    } else if (currentPage <= 4) {
                      page = i + 1
                    } else if (currentPage >= totalPages - 3) {
                      page = totalPages - 6 + i
                    } else {
                      page = currentPage - 3 + i
                    }
                    return (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                          currentPage === page
                            ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30'
                            : 'border border-slate-700 text-slate-400 hover:bg-slate-800'
                        }`}
                      >
                        {page}
                      </button>
                    )
                  })}
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-1.5 text-sm rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </>
          )}
        </div>

        {/* Recent Runs */}
        {runs.length > 0 && (
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white">Recent Runs</h2>
              <span className="text-sm text-slate-400">{runs.length} runs</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-900/50">
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Run</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Flow</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Started</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {runs.slice(0, 10).map(run => (
                    <tr key={run.id} className="hover:bg-slate-700/20 transition-colors">
                      <td className="px-4 py-3 text-sm text-slate-200">#{run.id}</td>
                      <td className="px-4 py-3 text-sm text-slate-300">
                        Flow #{run.flow_definition_id}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-slate-400">
                        {formatDate(run.started_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setViewingRunId(run.id)}
                            className="text-cyan-400 hover:text-cyan-300 text-sm transition-colors"
                          >
                            View Details
                          </button>
                          {(run.status === 'pending' || run.status === 'running') && (
                            <button
                              onClick={() => handleCancelRun(run.id)}
                              className="text-red-400 hover:text-red-300 text-sm transition-colors"
                              title="Cancel run"
                            >
                              Cancel
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Active Conversation Threads */}
        {activeThreads.length > 0 && (
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
                Active Conversations
              </h2>
              <span className="text-sm text-slate-400">{activeThreads.length} active</span>
            </div>
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {activeThreads.slice(0, 6).map(thread => (
                <div key={thread.id} className="bg-slate-700/30 rounded-lg p-4 border border-slate-600/50">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="text-sm font-medium text-white">{thread.recipient}</div>
                      {thread.flow_name && (
                        <div className="text-xs text-cyan-400">Flow: {thread.flow_name}</div>
                      )}
                    </div>
                    <span className="text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full">
                      Turn {thread.current_turn}/{thread.max_turns}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 truncate">{thread.objective || 'No objective specified'}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Create Flow Modal */}
      {showCreateFlow && (
        <CreateFlowModal
          agents={agents}
          contacts={contacts}
          personas={personas}
          customTools={customTools}
          customSkills={customSkills}
          // v0.7.0 Wave 4: Trigger prefill from deep link
          prefillTriggerKind={prefillReady ? prefillKind : null}
          prefillTriggerId={prefillReady ? prefillTriggerId : 0}
          prefillTriggerName={prefillTriggerName}
          onClose={() => {
            setShowCreateFlow(false)
            clearPrefillParams()
          }}
          onSuccess={() => {
            setShowCreateFlow(false)
            clearPrefillParams()
            loadData()
          }}
        />
      )}

      {/* Create from Template Modal */}
      {showCreateFromTemplate && (
        <CreateFromTemplateModal
          agents={agents}
          contacts={contacts}
          personas={personas}
          customTools={customTools}
          onClose={() => setShowCreateFromTemplate(false)}
          onSuccess={(flowId, flowName) => {
            setShowCreateFromTemplate(false)
            toast.success('Flow Created', `${flowName} is ready. Configure and enable it when you're set.`)
            loadData()
          }}
        />
      )}

      {/* Edit Flow Modal */}
      {editingFlowId && (
        <EditFlowModal
          flowId={editingFlowId}
          agents={agents}
          contacts={contacts}
          personas={personas}
          customTools={customTools}
          customSkills={customSkills}
          onClose={() => setEditingFlowId(null)}
          onSuccess={async () => {
            // BUG-636 FIX: await the refresh BEFORE closing the modal so
            // the row in ``allFlows`` reflects the just-saved version by
            // the time the user can click Run on it.
            await loadData()
            setEditingFlowId(null)
          }}
        />
      )}

      {/* View Run Modal */}
      {viewingRunId && (
        <ViewRunModal
          runId={viewingRunId}
          onClose={() => setViewingRunId(null)}
        />
      )}
    </div>
  )
}

// ==================== COMPONENTS ====================

function SortableHeader({ field, label, currentField, direction, onSort }: {
  field: SortField
  label: string
  currentField: SortField
  direction: SortDirection
  onSort: (field: SortField) => void
}) {
  const isActive = currentField === field

  return (
    <th
      className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-300 transition-colors select-none"
      onClick={() => onSort(field)}
    >
      <div className="flex items-center gap-1">
        {label}
        <span className={`transition-opacity ${isActive ? 'opacity-100' : 'opacity-0'}`}>
          {direction === 'asc' ? '↑' : '↓'}
        </span>
      </div>
    </th>
  )
}

function TypeBadge({ type }: { type: FlowType }) {
  const typeInfo = FLOW_TYPES.find(t => t.value === type) || FLOW_TYPES[0]
  const colorMap: Record<string, string> = {
    emerald: 'text-emerald-400',
    amber: 'text-amber-400',
    violet: 'text-violet-400',
    sky: 'text-sky-400',
  }

  return (
    <span className={`text-xs font-medium ${colorMap[typeInfo.color] || colorMap.sky}`}>
      {typeInfo.label}
    </span>
  )
}

// v0.7.0 release-finishing — system-managed (auto-generated from a trigger)
// flow badge. Trigger wizards mint a flow with `is_system_owned=true`; this
// chip surfaces the origin so operators don't mistake it for a hand-built
// flow. Renders nothing for user-authored flows.
const TRIGGER_KIND_BADGE: Record<
  'jira' | 'email' | 'github' | 'schedule' | 'webhook',
  { label: string; classes: string; Icon: React.FC<IconProps> }
> = {
  jira:     { label: 'Jira Trigger',     classes: 'bg-blue-500/10 border-blue-500/30 text-blue-300',         Icon: CodeIcon },
  email:    { label: 'Email Trigger',    classes: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300', Icon: EnvelopeIcon },
  github:   { label: 'GitHub Trigger',   classes: 'bg-violet-500/10 border-violet-500/30 text-violet-300',   Icon: GitHubIcon },
  schedule: { label: 'Schedule Trigger', classes: 'bg-amber-500/10 border-amber-500/30 text-amber-300',     Icon: CalendarDaysIcon },
  webhook:  { label: 'Webhook Trigger',  classes: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-300',         Icon: WebhookIcon },
}

function TriggerOriginBadge({ flow }: { flow: FlowDefinition }) {
  if (!flow.is_system_owned) return null
  const kind = (flow.system_trigger_kind || 'webhook') as keyof typeof TRIGGER_KIND_BADGE
  const cfg = TRIGGER_KIND_BADGE[kind] || TRIGGER_KIND_BADGE.webhook
  const Icon = cfg.Icon
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full border ${cfg.classes}`}
      title={`Auto-generated from ${kind} trigger — editable, but not deletable. Delete the trigger to remove this flow.`}
    >
      <Icon size={12} />
      {cfg.label}
    </span>
  )
}

function ExecutionBadge({ method }: { method: ExecutionMethod }) {
  const config: Record<string, { label: string; color: string; icon: JSX.Element }> = {
    immediate: {
      label: 'Immediate',
      color: 'text-slate-500',
      icon: <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
    },
    scheduled: {
      label: 'Scheduled',
      color: 'text-amber-400',
      icon: <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
    },
    recurring: {
      label: 'Recurring',
      color: 'text-violet-400',
      icon: <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
    },
    keyword: {
      label: 'Keyword',
      color: 'text-cyan-400',
      icon: <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" /></svg>
    },
  }

  const { label, color, icon } = config[method] || config.immediate

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${color}`}>
      {icon}
      {label}
    </span>
  )
}

function FlowTypeIcon({ type }: { type: FlowType }) {
  const typeInfo = FLOW_TYPES.find(t => t.value === type) || FLOW_TYPES[0]
  const IconComponent = typeInfo.Icon

  // Static Tailwind classes for each color (required for JIT compiler)
  const bgClasses: Record<string, string> = {
    emerald: 'bg-gradient-to-br from-emerald-500/20 to-emerald-500/5 border-emerald-500/20 text-emerald-400',
    amber: 'bg-gradient-to-br from-amber-500/20 to-amber-500/5 border-amber-500/20 text-amber-400',
    violet: 'bg-gradient-to-br from-violet-500/20 to-violet-500/5 border-violet-500/20 text-violet-400',
    sky: 'bg-gradient-to-br from-sky-500/20 to-sky-500/5 border-sky-500/20 text-sky-400',
  }

  return (
    <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${bgClasses[typeInfo.color] || bgClasses.sky}`}>
      <IconComponent size={20} />
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    running: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    completed: 'bg-green-500/20 text-green-400 border-green-500/30',
    failed: 'bg-red-500/20 text-red-400 border-red-500/30',
    cancelled: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
  }

  return (
    <span className={`px-2 py-0.5 text-xs rounded-full border ${styles[status] || styles.pending}`}>
      {status}
    </span>
  )
}

// ==================== RECURRENCE CONFIG PANEL ====================

function RecurrenceConfigPanel({ value, onChange }: {
  value?: {
    frequency: 'daily' | 'weekly' | 'monthly'
    interval?: number
    days_of_week?: number[]
    timezone?: string
    start_time?: string
  }
  onChange: (value: {
    frequency: 'daily' | 'weekly' | 'monthly'
    interval?: number
    days_of_week?: number[]
    timezone?: string
    start_time?: string
  }) => void
}) {
  const frequency = value?.frequency || 'daily'
  const interval = value?.interval || 1
  const daysOfWeek = value?.days_of_week || []
  const startTime = value?.start_time || '09:00'
  const timezone = value?.timezone || 'America/Sao_Paulo'

  const weekDays = [
    { value: 1, label: 'Mon' },
    { value: 2, label: 'Tue' },
    { value: 3, label: 'Wed' },
    { value: 4, label: 'Thu' },
    { value: 5, label: 'Fri' },
    { value: 6, label: 'Sat' },
    { value: 7, label: 'Sun' },
  ]

  function updateValue(updates: Partial<typeof value>) {
    onChange({
      frequency,
      interval,
      days_of_week: daysOfWeek,
      timezone,
      start_time: startTime,
      ...updates
    })
  }

  function toggleDayOfWeek(day: number) {
    const newDays = daysOfWeek.includes(day)
      ? daysOfWeek.filter(d => d !== day)
      : [...daysOfWeek, day].sort()
    updateValue({ days_of_week: newDays })
  }

  return (
    <div className="space-y-4 bg-slate-700/30 rounded-lg p-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">Frequency</label>
        <div className="grid grid-cols-3 gap-2">
          {(['daily', 'weekly', 'monthly'] as const).map(freq => (
            <button
              key={freq}
              onClick={() => updateValue({ frequency: freq })}
              className={`px-3 py-2 rounded-lg border text-sm capitalize transition-all ${frequency === freq
                  ? 'border-cyan-500 bg-cyan-500/10 text-white'
                  : 'border-slate-600 hover:border-slate-500 text-slate-300'
                }`}
            >
              {freq}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">
          Repeat every {frequency === 'daily' ? 'day(s)' : frequency === 'weekly' ? 'week(s)' : 'month(s)'}
        </label>
        <input
          type="number"
          min="1"
          max="30"
          value={interval}
          onChange={(e) => updateValue({ interval: parseInt(e.target.value) || 1 })}
          className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
        />
      </div>

      {frequency === 'weekly' && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">On these days</label>
          <div className="flex gap-2">
            {weekDays.map(day => (
              <button
                key={day.value}
                onClick={() => toggleDayOfWeek(day.value)}
                className={`px-3 py-2 rounded-lg border text-sm transition-all ${daysOfWeek.includes(day.value)
                    ? 'border-cyan-500 bg-cyan-500/10 text-white'
                    : 'border-slate-600 hover:border-slate-500 text-slate-400'
                  }`}
              >
                {day.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">Start Time</label>
        <input
          type="time"
          value={startTime}
          onChange={(e) => updateValue({ start_time: e.target.value })}
          className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
        />
      </div>

      <div className="text-xs text-slate-400">
        Timezone: {timezone}
      </div>
    </div>
  )
}

// ==================== CREATE FLOW MODAL ====================

function CreateFlowModal({ agents, contacts, personas, customTools, customSkills, onClose, onSuccess, prefillTriggerKind = null, prefillTriggerId = 0, prefillTriggerName = '' }: {
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  customSkills?: any[]
  onClose: () => void
  onSuccess: () => void
  // v0.7.0 Wave 4: when invoked from a trigger detail page, pre-build a
  // Source-only flow draft and auto-bind on success.
  prefillTriggerKind?: TriggerKind | null
  prefillTriggerId?: number
  prefillTriggerName?: string
}) {
  const toast = useToast()
  const [step, setStep] = useState<'config' | 'steps'>('config')
  const initialFlowData: CreateFlowData = useMemo(() => {
    if (prefillTriggerKind && prefillTriggerId > 0) {
      const kindLabel = prefillTriggerKind.charAt(0).toUpperCase() + prefillTriggerKind.slice(1)
      const namePart = prefillTriggerName ? `: ${prefillTriggerName}` : ` #${prefillTriggerId}`
      const sourceStep: CreateFlowStepData = {
        name: 'Source',
        type: 'source',
        // v0.7.0 Wave 2 invariant: positions are 1-based and source must
        // sit at position 1. Wave 4 prefill originally used position 0 and
        // POST /api/flows/create silently 422'd because the backend
        // validator rejects positions < 1 (helper at routes_flows.py:280)
        // — modal stayed open with no toast (caught by Wave 4 QA).
        position: 1,
        config: {
          trigger_kind: prefillTriggerKind,
          trigger_instance_id: prefillTriggerId,
        } as FlowStepConfig,
      }
      return {
        name: `${kindLabel}${namePart}`,
        description: `Auto-prefilled from ${kindLabel} trigger ${prefillTriggerId}.`,
        flow_type: 'workflow',
        execution_method: 'triggered',
        steps: [sourceStep],
      }
    }
    return {
      name: '',
      description: '',
      flow_type: 'workflow',
      execution_method: 'immediate',
      steps: [],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const [flowData, setFlowData] = useState<CreateFlowData>(initialFlowData)
  const [submitting, setSubmitting] = useState(false)
  const flowDataRef = useRef(flowData)
  flowDataRef.current = flowData
  // Flush callbacks registered by each StepConfigForm
  const createFlushRef = useRef<Map<number, () => void>>(new Map())

  async function handleSubmit() {
    if (!flowData.name.trim()) {
      toast.warning('Validation', 'Please provide a flow name')
      return
    }
    if ((flowData.steps?.length || 0) === 0) {
      toast.warning('Validation', 'Please add at least one step to your flow')
      return
    }

    // BUG-686 fix: flush callbacks may call setFlowData() which is async; the
    // single setTimeout(0) await wasn't enough for the React reconciler to
    // commit, leading to stale ref reads and "Create Flow" appearing to do
    // nothing. Flush, await two microtasks, then read the ref freshly.
    createFlushRef.current.forEach(flush => flush())
    await Promise.resolve()
    await new Promise(r => setTimeout(r, 0))

    setSubmitting(true)
    try {
      const payload = flowDataRef.current
      const created = await api.createFlowV2(payload)
      // v0.7.0 Wave 4: when the modal was opened from a trigger deep-link,
      // also create the flow_trigger_binding row so the new flow is wired
      // immediately. If binding fails, surface a toast but still close —
      // the user can retry from the trigger page's WiredFlowsCard.
      if (prefillTriggerKind && prefillTriggerId > 0 && created?.id) {
        try {
          await api.createFlowTriggerBinding({
            flow_definition_id: created.id,
            trigger_kind: prefillTriggerKind,
            trigger_instance_id: prefillTriggerId,
            suppress_default_agent: true,
          })
          toast.success('Flow created', 'Flow is wired to the trigger and will run when it fires.')
        } catch (bindErr: unknown) {
          const msg = bindErr instanceof Error ? bindErr.message : 'Could not create binding'
          toast.warning('Flow created — binding failed', `${msg}. You can wire it from the trigger page.`)
        }
      }
      onSuccess()
    } catch (error) {
      // BUG-686 fix: surface the real error message instead of a generic one.
      console.error('Failed to create flow:', error)
      const message = error instanceof Error && error.message
        ? error.message
        : 'Failed to create flow'
      toast.error('Creation Failed', message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div
        className="bg-slate-800 rounded-2xl max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-slate-700"
        onClick={(event) => event.stopPropagation()}
        onMouseDown={(event) => event.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Create New Flow</h2>
            <p className="text-sm text-slate-400">
              {step === 'config' && 'Configure your flow settings'}
              {step === 'steps' && 'Add steps to your flow'}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress Steps */}
        <div className="px-6 py-3 bg-slate-900/50 border-b border-slate-700">
          <div className="flex items-center gap-4">
            {['config', 'steps'].map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                  ${step === s ? 'bg-cyan-500 text-white' :
                    ['config', 'steps'].indexOf(step) > i ? 'bg-green-500 text-white' :
                      'bg-slate-700 text-slate-400'}`}
                >
                  {i + 1}
                </div>
                <span className={`text-sm ${step === s ? 'text-white' : 'text-slate-400'}`}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </span>
                {i < 1 && <div className="w-8 h-px bg-slate-700" />}
              </div>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {step === 'config' && (
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Flow Name *</label>
                <input
                  type="text"
                  value={flowData.name}
                  onChange={(e) => setFlowData(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="e.g. Customer Onboarding"
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             placeholder-slate-500 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Description</label>
                <textarea
                  value={flowData.description || ''}
                  onChange={(e) => setFlowData(prev => ({ ...prev, description: e.target.value }))}
                  rows={3}
                  placeholder="What does this flow do?"
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             placeholder-slate-500 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Category</label>
                <select
                  value={flowData.flow_type || 'workflow'}
                  onChange={(e) => setFlowData(prev => ({ ...prev, flow_type: e.target.value as FlowType }))}
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                >
                  {FLOW_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
                <p className="text-xs text-slate-500 mt-1">Used for filtering and organization</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Execution Method</label>
                <div className="grid grid-cols-3 gap-3">
                  {EXECUTION_METHODS.map(method => {
                    const MethodIcon = method.Icon
                    return (
                      <button
                        key={method.value}
                        type="button"
                        onClick={() => setFlowData(prev => ({ ...prev, execution_method: method.value }))}
                        className={`p-3 rounded-lg border text-center transition-all ${flowData.execution_method === method.value
                            ? 'border-cyan-500 bg-cyan-500/10 text-white'
                            : 'border-slate-700 hover:border-slate-600 text-slate-300'
                          }`}
                      >
                        <div className="flex justify-center">
                          <MethodIcon size={24} />
                        </div>
                        <div className="text-sm mt-1">{method.label}</div>
                      </button>
                    )
                  })}
                </div>
              </div>

              {flowData.execution_method === 'scheduled' && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Schedule Time</label>
                  <input
                    type="datetime-local"
                    value={flowData.scheduled_at || ''}
                    onChange={(e) => setFlowData(prev => ({ ...prev, scheduled_at: new Date(e.target.value).toISOString() }))}
                    className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                               focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                  />
                </div>
              )}

              {flowData.execution_method === 'recurring' && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Recurrence Settings</label>
                  <RecurrenceConfigPanel
                    value={flowData.recurrence_rule}
                    onChange={(rule) => setFlowData(prev => ({ ...prev, recurrence_rule: rule }))}
                  />
                </div>
              )}

              {/* BUG-336: Keyword trigger configuration */}
              {flowData.execution_method === 'keyword' && (
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Trigger Keywords</label>
                  <p className="text-xs text-slate-500 mb-2">
                    Enter one keyword or command per line. Messages matching any of these trigger this flow (e.g. <code className="bg-slate-800 px-1 rounded">/testflow</code> or <code className="bg-slate-800 px-1 rounded">start report</code>).
                  </p>
                  <textarea
                    value={(flowData.trigger_keywords || []).join('\n')}
                    onChange={(e) => setFlowData(prev => ({
                      ...prev,
                      trigger_keywords: e.target.value.split('\n').map(k => k.trim()).filter(Boolean)
                    }))}
                    rows={4}
                    placeholder="/testflow&#10;run report&#10;start workflow"
                    className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white font-mono text-sm
                               focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Default Agent</label>
                <select
                  value={flowData.default_agent_id || ''}
                  onChange={(e) => setFlowData(prev => ({ ...prev, default_agent_id: e.target.value ? parseInt(e.target.value) : undefined }))}
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                >
                  <option value="">Select an agent...</option>
                  {agents.map(agent => (
                    <option key={agent.id} value={agent.id}>{agent.contact_name}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {step === 'steps' && (
            <StepBuilder
              steps={flowData.steps || []}
              agents={agents}
              contacts={contacts}
              personas={personas}
              customTools={customTools}
              customSkills={customSkills}
              onChange={(steps) => setFlowData(prev => ({ ...prev, steps }))}
              flushCallbacksRef={createFlushRef}
            />
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              if (step === 'steps') setStep('config')
              else onClose()
            }}
            className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
          >
            {step === 'config' ? 'Cancel' : 'Back'}
          </button>
          <button
            type="button"
            onClick={() => {
              if (step === 'config') setStep('steps')
              else handleSubmit()
            }}
            disabled={submitting || (step === 'steps' && (flowData.steps?.length || 0) === 0)}
            className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-medium rounded-lg
                       hover:from-cyan-400 hover:to-blue-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Creating...' : step === 'steps' ? 'Create Flow' : 'Continue'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ==================== STEP BUILDER ====================

function StepBuilder({ steps, agents, contacts, personas, customTools, customSkills, onChange, flushCallbacksRef }: {
  steps: CreateFlowStepData[]
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  customSkills?: any[]
  onChange: (steps: CreateFlowStepData[]) => void
  flushCallbacksRef?: React.MutableRefObject<Map<number, () => void>>
}) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [showAddStep, setShowAddStep] = useState(steps.length === 0)

  function handleStepTypeClick(
    event: MouseEvent<HTMLButtonElement>,
    stepType: StepType
  ) {
    event.preventDefault()
    event.stopPropagation()
    addStep(stepType)
  }

  function addStep(stepType: StepType) {
    // v0.7.0 Wave 2: source step is locked at position 0 and capped at 1 per flow.
    if (stepType === 'source') {
      if (steps.some((s) => s.type === 'source')) return
      const newStep: CreateFlowStepData = {
        name: 'Source',
        type: 'source',
        position: 1,
        config: {},
        allow_multi_turn: false,
        max_turns: undefined,
      }
      // Insert at the front and renumber.
      const next = [newStep, ...steps].map((s, i) => ({ ...s, position: i + 1 }))
      onChange(next)
      setEditingIndex(0)
      setShowAddStep(false)
      return
    }
    const newStep: CreateFlowStepData = {
      name: `Step ${steps.length + 1}`,
      type: stepType,
      position: steps.length + 1,
      config: ['message', 'notification', 'conversation'].includes(stepType) ? { channel: 'whatsapp' } : {},
      allow_multi_turn: stepType === 'conversation',
      max_turns: stepType === 'conversation' ? 20 : undefined,
    }
    onChange([...steps, newStep])
    setEditingIndex(steps.length)
    setShowAddStep(false)
  }

  function updateStep(index: number, update: Partial<CreateFlowStepData>) {
    const newSteps = [...steps]
    newSteps[index] = { ...newSteps[index], ...update }
    onChange(newSteps)
  }

  function removeStep(index: number) {
    // v0.7.0 Wave 2: source step is non-removable while present.
    if (steps[index]?.type === 'source') return
    const newSteps = steps.filter((_, i) => i !== index)
    // Update positions
    newSteps.forEach((step, i) => step.position = i + 1)
    onChange(newSteps)
    setEditingIndex(null)
  }

  function moveStep(index: number, direction: 'up' | 'down') {
    if ((direction === 'up' && index === 0) || (direction === 'down' && index === steps.length - 1)) return
    // v0.7.0 Wave 2: source step is locked at position 0; never move it,
    // and never allow another step to slide above it.
    const movingStep = steps[index]
    if (movingStep?.type === 'source') return
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (steps[targetIndex]?.type === 'source') return

    const newSteps = [...steps]
      ;[newSteps[index], newSteps[targetIndex]] = [newSteps[targetIndex], newSteps[index]]
    // Update positions and auto-rename "Step N" names to match new position
    newSteps.forEach((step, i) => {
      step.position = i + 1
      if (/^Step \d+$/.test(step.name)) {
        step.name = `Step ${i + 1}`
      }
    })
    onChange(newSteps)
  }

  return (
    <div className="space-y-4">
      {/* Steps List */}
      {steps.length > 0 && (
        <div className="space-y-3">
          {steps.map((step, index) => (
            <div
              key={index}
              className={`rounded-xl border transition-all ${editingIndex === index
                  ? 'border-cyan-500 bg-cyan-500/5'
                  : 'border-slate-700 bg-slate-700/30 hover:border-slate-600'
                }`}
            >
              {/* Step Header */}
              <div
                className="p-4 flex items-center gap-4 cursor-pointer"
                onClick={() => setEditingIndex(editingIndex === index ? null : index)}
              >
                <div className="flex flex-col gap-1">
                  {/* v0.7.0 Wave 2: source step is locked at position 0; hide reorder buttons. */}
                  {step.type !== 'source' && (
                    <>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); moveStep(index, 'up') }}
                        disabled={index === 0 || steps[index - 1]?.type === 'source'}
                        className="text-slate-500 hover:text-white disabled:opacity-30"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); moveStep(index, 'down') }}
                        disabled={index === steps.length - 1}
                        className="text-slate-500 hover:text-white disabled:opacity-30"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </>
                  )}
                </div>

                <div className="w-10 h-10 rounded-lg bg-slate-600 flex items-center justify-center text-slate-300">
                  {(() => {
                    const stepType = STEP_TYPES.find(t => t.value === step.type)
                    if (stepType) {
                      const StepIcon = stepType.Icon
                      return <StepIcon size={20} />
                    }
                    return <span className="text-xl">❓</span>
                  })()}
                </div>

                <div className="flex-1">
                  <div className="font-medium text-white flex items-center gap-2">
                    {step.name}
                    {step.type === 'source' && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                        Locked at top
                      </span>
                    )}
                    {step.type === 'gate' && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        (step.config?.gate_mode || 'programmatic') === 'programmatic'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                      }`}>
                        {(step.config?.gate_mode || 'programmatic') === 'programmatic' ? 'Programmatic' : 'Agentic'}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-slate-400">
                    {STEP_TYPES.find(t => t.value === step.type)?.label}
                    {step.allow_multi_turn && ' • Multi-turn'}
                    {step.type === 'gate' && step.config?.gate_conditions && step.config.gate_conditions.length > 0 && (
                      <span className="text-xs text-slate-500 ml-1">
                        • {step.config.gate_conditions.length} condition{step.config.gate_conditions.length !== 1 ? 's' : ''} ({step.config?.gate_logic || 'all'})
                      </span>
                    )}
                    {step.type === 'gate' && step.config?.gate_mode === 'agentic' && step.config?.gate_prompt && (
                      <span className="text-xs text-slate-500 ml-1">
                        • AI prompt set
                      </span>
                    )}
                  </div>
                </div>

                {/* v0.7.0 Wave 2: source step is non-removable while present; hide Delete. */}
                {step.type !== 'source' && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); removeStep(index) }}
                    className="text-red-400 hover:text-red-300 p-2"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}

                <svg className={`w-5 h-5 text-slate-400 transition-transform ${editingIndex === index ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>

              {/* Step Config (Expanded) */}
              {editingIndex === index && (
                <div className="px-4 pb-4 pt-2 border-t border-slate-700/50 space-y-4">
                  <StepConfigForm
                    step={step}
                    agents={agents}
                    contacts={contacts}
                    personas={personas}
                    customTools={customTools}
                    customSkills={customSkills}
                    onChange={(update) => updateStep(index, update)}
                    allSteps={steps}
                    flushCallbacksRef={flushCallbacksRef}
                    stepIndex={index}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add Step Button/Section */}
      {showAddStep ? (
        <div className="rounded-xl border border-dashed border-slate-600 p-6">
          <h4 className="text-sm font-medium text-slate-300 mb-4">Add a Step</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {/* v0.7.0 Wave 2: hide 'source' if a source step already exists (max 1 per flow). */}
            {STEP_TYPES.filter((type) => type.value !== 'source' || !steps.some((s) => s.type === 'source')).map(type => {
              const StepIcon = type.Icon
              return (
                <button
                  key={type.value}
                  type="button"
                  onClick={(event) => handleStepTypeClick(event, type.value)}
                  className="p-4 rounded-lg border border-slate-700 hover:border-cyan-500/50 hover:bg-cyan-500/5
                             text-center transition-all text-slate-300 hover:text-cyan-400"
                >
                  <div className="flex justify-center">
                    <StepIcon size={28} />
                  </div>
                  <div className="text-sm text-white mt-2">{type.label}</div>
                  <div className="text-xs text-slate-500 mt-1">{type.description}</div>
                </button>
              )
            })}
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowAddStep(true)}
          className="w-full py-3 rounded-xl border border-dashed border-slate-600 text-slate-400
                     hover:border-cyan-500/50 hover:text-cyan-400 transition-all flex items-center justify-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Step
        </button>
      )}
    </div>
  )
}

// ==================== CURSOR-SAFE INPUT HELPERS ====================
// These components hold their own local state so that the cursor position
// is never lost when the parent re-renders and passes a new value prop.

function CursorSafeInput({
  value: externalValue,
  onValueChange,
  onFocus: externalOnFocus,
  onBlur: externalOnBlur,
  ...restProps
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> & {
  value: string
  onValueChange: (value: string) => void
}) {
  const [localValue, setLocalValue] = useState(externalValue)
  const isFocusedRef = useRef(false)

  useEffect(() => {
    if (!isFocusedRef.current) {
      setLocalValue(externalValue)
    }
  }, [externalValue])

  return (
    <input
      {...restProps}
      value={localValue}
      onFocus={(e) => {
        isFocusedRef.current = true
        externalOnFocus?.(e)
      }}
      onBlur={(e) => {
        isFocusedRef.current = false
        externalOnBlur?.(e)
      }}
      onChange={(e) => {
        setLocalValue(e.target.value)
        onValueChange(e.target.value)
      }}
    />
  )
}

function CursorSafeTextarea({
  value: externalValue,
  onValueChange,
  onFocus: externalOnFocus,
  onBlur: externalOnBlur,
  ...restProps
}: Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange' | 'value'> & {
  value: string
  onValueChange: (value: string) => void
}) {
  const [localValue, setLocalValue] = useState(externalValue)
  const isFocusedRef = useRef(false)

  useEffect(() => {
    if (!isFocusedRef.current) {
      setLocalValue(externalValue)
    }
  }, [externalValue])

  return (
    <textarea
      {...restProps}
      value={localValue}
      onFocus={(e) => {
        isFocusedRef.current = true
        externalOnFocus?.(e)
      }}
      onBlur={(e) => {
        isFocusedRef.current = false
        onValueChange(localValue)
        externalOnBlur?.(e)
      }}
      onChange={(e) => {
        setLocalValue(e.target.value)
        onValueChange(e.target.value)
      }}
    />
  )
}

// ==================== TOOL PARAMETER FORM ====================

function ToolParameterForm({
  toolType,
  toolId,
  commandId,
  parameters,
  onChange,
  onCommandChange
}: {
  toolType: 'built_in' | 'custom'
  toolId: string | undefined
  commandId?: string | number
  parameters: Record<string, any>
  onChange: (params: Record<string, any>) => void
  onCommandChange?: (commandId: string | number) => void
}) {
  const [toolMetadata, setToolMetadata] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [showJsonMode, setShowJsonMode] = useState(false)  // MOVED HERE - before any early returns!

  // Fetch tool metadata when tool is selected
  useEffect(() => {
    if (!toolId) {
      setToolMetadata(null)
      setLoadError(false)
      return
    }

    const fetchMetadata = async () => {
      setLoading(true)
      setLoadError(false)
      try {
        const metadata = await api.getFlowToolMetadata(toolType, toolId)
        setToolMetadata(metadata)

        // If there's only one command, auto-select it
        if (metadata.commands.length === 1 && onCommandChange) {
          onCommandChange(metadata.commands[0].id)
        }
      } catch (error) {
        console.error('Failed to fetch tool metadata:', error)
        setLoadError(true)
      } finally {
        setLoading(false)
      }
    }

    fetchMetadata()
  }, [toolType, toolId])

  // Find the selected command
  const selectedCommand = useMemo(() => {
    if (!toolMetadata || !commandId) return null
    return toolMetadata.commands.find((cmd: any) => cmd.id === commandId || cmd.id.toString() === commandId.toString())
  }, [toolMetadata, commandId])

  if (loading) {
    return <div className="text-sm text-slate-400">Loading parameters...</div>
  }

  // Fallback: Show JSON textarea if metadata failed to load or no tool selected
  if (!toolMetadata || loadError) {
    return (
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">
          Tool Parameters (JSON)
          {loadError && <span className="text-amber-400 text-xs ml-2">Using manual entry (auto-detection failed)</span>}
        </label>
        <textarea
          value={JSON.stringify(parameters || {}, null, 2)}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value))
            } catch { }
          }}
          rows={3}
          placeholder='{"target": "host.docker.internal", "ports": "1-1000"}'
          className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                     font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
        />
        <p className="text-xs text-slate-500 mt-1">
          Enter parameters as JSON. Example: {`{"target": "192.168.1.1"}`}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Command Selector (for custom tools with multiple commands) */}
      {toolType === 'custom' && toolMetadata.commands.length > 1 && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Command</label>
          <select
            value={commandId || ''}
            onChange={(e) => onCommandChange && onCommandChange(e.target.value)}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          >
            <option value="">Select a command...</option>
            {toolMetadata.commands.map((cmd: any) => (
              <option key={cmd.id} value={cmd.id}>
                {cmd.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Toggle between form and JSON */}
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-slate-300">Parameters</label>
        <button
          type="button"
          onClick={() => setShowJsonMode(!showJsonMode)}
          className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          {showJsonMode ? <span className="inline-flex items-center gap-1"><FileTextIcon size={12} /> Use Form</span> : '{ } Edit JSON'}
        </button>
      </div>

      {showJsonMode ? (
        /* JSON Editor Mode */
        <div>
          <textarea
            value={JSON.stringify(parameters || {}, null, 2)}
            onChange={(e) => {
              try {
                onChange(JSON.parse(e.target.value))
              } catch { }
            }}
            rows={5}
            placeholder='{"target": "host.docker.internal", "ports": "1-1000"}'
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
          />
          <p className="text-xs text-slate-500 mt-1">
            Enter parameters as JSON. Example: {`{"target": "192.168.1.1"}`}
          </p>
        </div>
      ) : (
        <>
          {/* Dynamic Parameter Fields */}
          {selectedCommand && selectedCommand.parameters && selectedCommand.parameters.length > 0 && (
            <div className="space-y-3 p-3 bg-slate-800/50 border border-slate-700 rounded-lg">
              {selectedCommand.parameters.map((param: any) => (
                <div key={param.name}>
                  <label className="block text-sm text-slate-300 mb-1">
                    {param.name}
                    {param.required && <span className="text-red-400 ml-1">*</span>}
                  </label>
                  <CursorSafeInput
                    type="text"
                    value={parameters[param.name] || ''}
                    onValueChange={(v) => onChange({ ...parameters, [param.name]: v })}
                    placeholder={param.description || `Enter ${param.name}`}
                    className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                               focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                  />
                  {param.description && (
                    <p className="text-xs text-slate-500 mt-1">{param.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Show message if no command selected or no parameters */}
          {toolMetadata.commands.length > 0 && !selectedCommand && (
            <p className="text-sm text-slate-400 italic">Select a command to configure parameters</p>
          )}

          {selectedCommand && selectedCommand.parameters.length === 0 && (
            <p className="text-sm text-slate-400 italic">This command has no parameters</p>
          )}
        </>
      )}
    </div>
  )
}

// ==================== STEP CONFIG FORM ====================

function StepConfigForm({ step, agents, contacts, personas, customTools, customSkills, onChange, allSteps, flushCallbacksRef, stepIndex }: {
  step: CreateFlowStepData
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  customSkills?: any[]
  onChange: (update: Partial<CreateFlowStepData>) => void
  allSteps: CreateFlowStepData[]
  flushCallbacksRef?: React.MutableRefObject<Map<number, () => void>>
  stepIndex?: number
}) {
  const [recipientInput, setRecipientInput] = useState(step.config?.recipient || '')
  const [showContactSuggestions, setShowContactSuggestions] = useState(false)
  const [localChanges, setLocalChanges] = useState<Partial<CreateFlowStepData>>({})
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const pendingChangesRef = useRef<Partial<CreateFlowStepData>>({})
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    setRecipientInput(step.config?.recipient || '')
    setLocalChanges({})
    pendingChangesRef.current = {}
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current)
      saveTimeoutRef.current = null
    }
  }, [step.position])

  // Register flush callback so Create Flow can force-flush pending changes
  useEffect(() => {
    if (!flushCallbacksRef || stepIndex === undefined) return
    const flush = () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
        saveTimeoutRef.current = null
      }
      const pending = pendingChangesRef.current
      if (Object.keys(pending).length > 0) {
        onChangeRef.current(pending)
        pendingChangesRef.current = {}
      }
    }
    flushCallbacksRef.current.set(stepIndex, flush)
    return () => { flushCallbacksRef.current.delete(stepIndex) }
  }, [stepIndex, flushCallbacksRef])

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      // Flush any pending changes on unmount so edits are not lost
      const pending = pendingChangesRef.current
      if (Object.keys(pending).length > 0) {
        onChangeRef.current(pending)
        pendingChangesRef.current = {}
      }
    }
  }, [])

  function debouncedSave(
    update: Partial<CreateFlowStepData> | ((prev: Partial<CreateFlowStepData>) => Partial<CreateFlowStepData>)
  ) {
    setLocalChanges(prev => {
      const nextUpdate = typeof update === 'function' ? update(prev) : update
      const merged = { ...prev, ...nextUpdate }
      pendingChangesRef.current = merged
      return merged
    })

    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current)
    saveTimeoutRef.current = setTimeout(() => {
      const pending = pendingChangesRef.current
      if (Object.keys(pending).length > 0) {
        onChange(pending)
        pendingChangesRef.current = {}
      }
    }, 500)
  }

  const filteredContacts = contacts.filter(c => {
    // Show all contacts when input is empty
    if (!recipientInput) return true
    const search = recipientInput.startsWith('@') ? recipientInput.slice(1).toLowerCase() : recipientInput.toLowerCase()
    return c.friendly_name.toLowerCase().includes(search) ||
      c.phone_number?.toLowerCase().includes(search)
  })

  function updateConfig(key: string, value: any) {
    debouncedSave(prev => ({
      config: { ...step.config, ...prev.config, [key]: value }
    }))
  }

  const currentStep = { ...step, ...localChanges }
  const currentConfig = { ...step.config, ...localChanges.config }

  // Variable Reference panel input — shared across all templatable fields.
  const stepInfoList = allSteps.map(s => ({
    name: s.name,
    type: s.type,
    position: s.position,
    config: s.config,
  }))

  return (
    <div className="space-y-4">
      {/* Step Name */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">Step Name</label>
        <CursorSafeInput
          type="text"
          value={currentStep.name || ''}
          onValueChange={(v) => debouncedSave({ name: v })}
          className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
        />
      </div>

      {/* v0.7.0 Wave 4: Source step renders trigger summary + sample payload + variable hint. */}
      {step.type === 'source' && (
        <SourceStepConfig config={(step.config as Record<string, any>) || {}} />
      )}

      {/* Channel Selector - for message/notification/conversation */}
      {['message', 'notification', 'conversation'].includes(step.type) && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Channel</label>
          <div className="grid grid-cols-2 gap-2">
            {CHANNEL_OPTIONS.map(ch => {
              const ChIcon = ch.Icon
              const isSelected = (currentConfig?.channel || 'whatsapp') === ch.value
              return (
                <button
                  key={ch.value}
                  type="button"
                  disabled={!ch.enabled}
                  onClick={() => ch.enabled && updateConfig('channel', ch.value)}
                  className={`relative flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-all
                    ${isSelected && ch.enabled
                      ? 'border-cyan-500 bg-cyan-500/10 text-white'
                      : !ch.enabled
                        ? 'border-slate-700 bg-slate-800/50 text-slate-500 cursor-not-allowed opacity-60'
                        : 'border-slate-600 hover:border-slate-500 text-slate-300'
                    }`}
                >
                  <ChIcon size={18} className={isSelected && ch.enabled ? ch.activeColor : ''} />
                  <span>{ch.label}</span>
                  {ch.badge && (
                    <span className="absolute -top-2 -right-1 px-1.5 py-0.5 text-[10px] font-medium
                                   bg-slate-700 text-slate-400 rounded-full border border-slate-600">
                      {ch.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Recipient - for message/notification/conversation */}
      {['message', 'notification', 'conversation'].includes(step.type) && (
        <div className="relative">
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Recipient</label>
          <input
            type="text"
            value={recipientInput}
            onChange={(e) => {
              setRecipientInput(e.target.value)
              updateConfig('recipient', e.target.value)
            }}
            onFocus={() => setShowContactSuggestions(true)}
            onBlur={() => setTimeout(() => setShowContactSuggestions(false), 200)}
            placeholder="Select contact or enter phone number (e.g., +5527999999999)"
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          />
          {showContactSuggestions && contacts.length > 0 && (
            <div className="absolute z-10 w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl max-h-60 overflow-y-auto">
              {filteredContacts.length > 0 ? (
                filteredContacts.map(contact => (
                  <div
                    key={contact.id}
                    onClick={() => {
                      setRecipientInput(`@${contact.friendly_name}`)
                      updateConfig('recipient', `@${contact.friendly_name}`)
                      setShowContactSuggestions(false)
                    }}
                    className="px-3 py-2 hover:bg-slate-700 cursor-pointer transition-colors"
                  >
                    <div className="text-sm font-medium text-white">@{contact.friendly_name}</div>
                    {contact.phone_number && (
                      <div className="text-xs text-slate-400">{contact.phone_number}</div>
                    )}
                  </div>
                ))
              ) : (
                <div className="px-3 py-2 text-sm text-slate-400">
                  No contacts found. Type a phone number to continue.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Message Template - for message/notification */}
      {['message', 'notification'].includes(step.type) && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">
            {step.type === 'notification' ? 'Notification Text' : 'Message Template'}
          </label>
          <TemplateTextarea
            value={step.type === 'notification'
              ? (currentConfig?.content || '')
              : (currentConfig?.message_template || '')}
            onValueChange={(v) => updateConfig(step.type === 'notification' ? 'content' : 'message_template', v)}
            rows={3}
            placeholder={step.type === 'notification'
              ? 'What to notify about? Use {{step_1.field}} to inject previous step outputs'
              : 'Enter your message... Use {{step_1.field}} to inject previous step outputs'}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
            allSteps={stepInfoList}
            currentStepPosition={step.position}
          />
        </div>
      )}

      {/* Conversation Settings */}
      {step.type === 'conversation' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Conversation Objective</label>
            <TemplateTextarea
              value={currentStep.conversation_objective || currentConfig?.objective || ''}
              onValueChange={(v) => {
                debouncedSave(prev => ({
                  conversation_objective: v,
                  config: { ...step.config, ...prev.config, objective: v }
                }))
              }}
              rows={2}
              placeholder="What should this conversation achieve? Use {{step_N.field}} to inject previous step outputs."
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Initial Prompt</label>
            <TemplateTextarea
              value={currentConfig?.initial_prompt || ''}
              onValueChange={(v) => updateConfig('initial_prompt', v)}
              rows={2}
              placeholder="First message to send... Use {{step_N.field}} to inject previous step outputs."
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Max Turns</label>
              <input
                type="number"
                value={currentStep.max_turns || 20}
                onChange={(e) => debouncedSave({ max_turns: parseInt(e.target.value) })}
                min={1}
                max={100}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Timeout (seconds)</label>
              <input
                type="number"
                value={currentStep.timeout_seconds || 3600}
                onChange={(e) => debouncedSave({ timeout_seconds: parseInt(e.target.value) })}
                min={60}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              />
            </div>
          </div>
          {/* Output Alias for Step Output Injection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Output Alias (optional)
              <span className="text-slate-500 text-xs ml-2">For referencing in later steps</span>
            </label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.output_alias || ''}
              onValueChange={(v) => updateConfig('output_alias', v)}
              placeholder="e.g. conversation_result"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">
              Use in subsequent steps as: {'{{'}output_alias.summary{'}}'} or {'{{'}output_alias.messages{'}}'}
            </p>
          </div>
        </>
      )}

      {/* Tool Settings */}
      {step.type === 'tool' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Tool Type</label>
            <select
              value={currentConfig?.tool_type || 'built_in'}
              onChange={(e) => {
                // Combine both updates into a single atomic operation to prevent race condition
                debouncedSave(prev => ({
                  config: { ...step.config, ...prev.config, tool_type: e.target.value, tool_name: '' }
                }))
              }}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="built_in">Built-in Tools</option>
              <option value="custom">Sandboxed Tools</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Tool Name</label>
            <select
              value={currentConfig?.tool_name || ''}
              onChange={(e) => updateConfig('tool_name', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="">Select a tool...</option>
              {(currentConfig?.tool_type || 'built_in') === 'built_in' ? (
                <>
                  <option value="google_search">Google Search</option>
                  <option value="send_message">Send Message</option>
                </>
              ) : (
                <>
                  {customTools.length === 0 ? (
                    <option value="" disabled>No sandboxed tools available</option>
                  ) : (
                    customTools.map(tool => (
                      <option key={tool.id} value={tool.id.toString()}>
                        {tool.name} ({tool.tool_type})
                      </option>
                    ))
                  )}
                </>
              )}
            </select>
            {(currentConfig?.tool_type || 'built_in') === 'custom' && customTools.length === 0 && (
              <p className="text-xs text-amber-400 mt-1.5">
                <span className="inline-flex items-center gap-1"><LightbulbIcon size={12} /> Sandboxed tools must be created and enabled in the Agents &gt; Sandboxed Tools section first.</span>
              </p>
            )}
          </div>

          {/* Tool Parameters Dynamic Form */}
          <ToolParameterForm
            toolType={(currentConfig?.tool_type || 'built_in') as 'built_in' | 'custom'}
            toolId={currentConfig?.tool_name || currentConfig?.tool_id}
            commandId={currentConfig?.command_id}
            parameters={currentConfig?.tool_parameters || {}}
            onChange={(params) => updateConfig('tool_parameters', params)}
            onCommandChange={(cmdId) => updateConfig('command_id', cmdId)}
          />

          {/* Output Alias for Step Output Injection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Output Alias (optional)
              <span className="text-slate-500 text-xs ml-2">For referencing in later steps</span>
            </label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.output_alias || ''}
              onValueChange={(v) => updateConfig('output_alias', v)}
              placeholder="e.g. scan_results"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">
              Use in subsequent steps as: {'{{'}output_alias.field{'}}'}
            </p>
          </div>
        </>
      )}

      {/* Skill Settings */}
      {step.type === 'skill' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Skill Type</label>
            <select
              value={currentConfig?.skill_type || ''}
              onChange={(e) => updateConfig('skill_type', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="">Select a skill...</option>
              <optgroup label="Built-in Skills">
                {AVAILABLE_SKILLS.map(skill => (
                  <option key={skill.value} value={skill.value}>
                    {skill.label}
                  </option>
                ))}
              </optgroup>
              {customSkills && customSkills.length > 0 && (
                <optgroup label="Custom Skills">
                  {customSkills.map((s: any) => (
                    <option key={`custom:${s.slug}`} value={`custom:${s.slug}`}>
                      {s.icon || '\uD83E\uDDE9'} {s.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            {currentConfig?.skill_type && (
              <p className="text-xs text-slate-500 mt-1">
                {AVAILABLE_SKILLS.find(s => s.value === currentConfig?.skill_type)?.description
                  || customSkills?.find((s: any) => `custom:${s.slug}` === currentConfig?.skill_type)?.description
                  || ''}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Prompt
              <span className="text-slate-500 text-xs ml-2">Natural language instruction for the skill</span>
            </label>
            <TemplateTextarea
              value={currentConfig?.prompt || ''}
              onValueChange={(v) => updateConfig('prompt', v)}
              rows={3}
              placeholder="e.g., busque voos de VIX para CGH dia 16 de Março de 2026 em BRL"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
            <p className="text-xs text-slate-500 mt-1">
              <span className="inline-flex items-center gap-1"><LightbulbIcon size={12} /> Write as if you were asking the agent directly. Use {'{{'}step_N.field{'}}'} to inject data from previous steps.</span>
            </p>
          </div>

          {/* Skill-specific configuration hints */}
          {currentConfig?.skill_type === 'flight_search' && (
            <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
              <p className="text-xs text-slate-400">
                <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><PlaneIcon size={12} /> Flight Search Tips:</span> Include origin, destination, date, and currency.
                <br />Example: "busque voos de VIX para GRU dia 20 de Janeiro de 2026 em BRL"
              </p>
            </div>
          )}
          {currentConfig?.skill_type === 'scheduler' && (
            <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
              <p className="text-xs text-slate-400">
                <span className="text-cyan-400 font-medium">📅 Scheduler Tips:</span> Be specific about date, time, and event details.
                <br />Example: "agende uma reunião para amanhã às 14h com título Sync Semanal"
              </p>
            </div>
          )}

          {/* Output Alias for Step Output Injection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Output Alias (optional)
              <span className="text-slate-500 text-xs ml-2">For referencing in later steps</span>
            </label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.output_alias || ''}
              onValueChange={(v) => updateConfig('output_alias', v)}
              placeholder="e.g. flight_results"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">
              Use in subsequent steps as: {'{{'}output_alias.output{'}}'} or {'{{'}step_N.output{'}}'}
            </p>
          </div>
        </>
      )}

      {/* Summarization Settings */}
      {step.type === 'summarization' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Source Step</label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.source_step || ''}
              onValueChange={(v) => updateConfig('source_step', v)}
              placeholder="step_1 or step name"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">
              Reference the conversation step to summarize (e.g., step_1)
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Output Format</label>
              <select
                value={currentConfig?.output_format || 'brief'}
                onChange={(e) => updateConfig('output_format', e.target.value)}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              >
                {SUMMARIZATION_OUTPUT_FORMATS.map(fmt => (
                  <option key={fmt.value} value={fmt.value}>{fmt.label}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-1">
                {SUMMARIZATION_OUTPUT_FORMATS.find(f => f.value === (currentConfig?.output_format || 'brief'))?.description}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Prompt Mode</label>
              <select
                value={currentConfig?.prompt_mode || 'append'}
                onChange={(e) => updateConfig('prompt_mode', e.target.value)}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              >
                {SUMMARIZATION_PROMPT_MODES.map(mode => (
                  <option key={mode.value} value={mode.value}>{mode.label}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-1">
                {SUMMARIZATION_PROMPT_MODES.find(m => m.value === (currentConfig?.prompt_mode || 'append'))?.description}
              </p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Custom Prompt
              <span className="text-slate-500 text-xs ml-2">
                {step.config?.prompt_mode === 'replace' ? '(Full prompt)' : '(Added to default)'}
              </span>
            </label>
            <TemplateTextarea
              value={currentConfig?.summary_prompt || ''}
              onValueChange={(v) => updateConfig('summary_prompt', v)}
              rows={4}
              placeholder={currentConfig?.prompt_mode === 'replace'
                ? 'Enter your complete summarization instructions...\n\nExample:\nExtract only:\n📍 Status: [value]\n📅 Date: [value]'
                : 'Additional instructions to add to the default summary template...'}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none font-mono"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">AI Model</label>
            <select
              value={currentConfig?.model || 'gemini-2.5-flash'}
              onChange={(e) => updateConfig('model', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              {SUMMARIZATION_MODELS.map(model => (
                <option key={model.value} value={model.value}>{model.label}</option>
              ))}
            </select>
          </div>

          {/* Tips for summarization */}
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-xs text-slate-400">
              <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><DocumentIcon size={12} /> Summarization Tips:</span>
              <br />• Use <strong>minimal</strong> format + <strong>replace</strong> mode for concise notifications
              <br />• Use <strong>structured</strong> format for detailed reports
              <br />• Reference with {'{{'}step_N.summary{'}}'} in subsequent steps
            </p>
          </div>
        </>
      )}

      {/* Slash Command Settings */}
      {step.type === 'slash_command' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Command *</label>
            <TemplateInput
              value={currentConfig?.command || ''}
              onValueChange={(v) => updateConfig('command', v)}
              placeholder="/scheduler list week"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none font-mono"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
            <p className="text-xs text-slate-500 mt-1">
              Enter the slash command to execute (e.g., /scheduler list week, /memory search &lt;query&gt;)
            </p>
          </div>

          {/* Note: Agent override for slash_command uses the step's agent_id field,
              which is handled in the Agent & Persona Selection section below */}

          {/* Available slash commands reference */}
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-xs text-slate-400">
              <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><CommandIcon size={12} /> Available Commands:</span>
              <br />• <code className="text-amber-400">/scheduler</code> - Manage scheduled events (list, add, remove)
              <br />• <code className="text-amber-400">/memory</code> - Search and manage agent memory
              <br />• <code className="text-amber-400">/flows</code> - List and manage flows
              <br />• <code className="text-amber-400">/personas</code> - List and switch personas
              <br />• <code className="text-amber-400">/help</code> - Show available commands
            </p>
            <p className="text-xs text-slate-500 mt-2">
              Output available as {'{{'}step_N.output{'}}'} in subsequent steps
            </p>
          </div>
        </>
      )}

      {/* Gate Settings */}
      {step.type === 'gate' && (
        <>
          {/* Mode Toggle */}
          <div>
            <label className="block text-sm font-semibold text-slate-200 mb-2">Gate Mode</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => updateConfig('gate_mode', 'programmatic')}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-all ${
                  (currentConfig?.gate_mode || 'programmatic') === 'programmatic'
                    ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400'
                    : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                }`}
              >
                Programmatic
              </button>
              <button
                type="button"
                onClick={() => updateConfig('gate_mode', 'agentic')}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-all ${
                  currentConfig?.gate_mode === 'agentic'
                    ? 'bg-amber-500/10 border-amber-500/50 text-amber-400'
                    : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                }`}
              >
                Agentic (AI)
              </button>
            </div>
          </div>

          {/* Programmatic Mode Panel */}
          {(currentConfig?.gate_mode || 'programmatic') === 'programmatic' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Source Step</label>
                <CursorSafeInput
                  type="text"
                  value={currentConfig?.gate_source_step || ''}
                  onValueChange={(v) => updateConfig('gate_source_step', v)}
                  placeholder="e.g. inbox, step_1"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                />
                <p className="text-xs text-slate-500 mt-1">Step whose output the gate evaluates</p>
              </div>

              {/* Logic Toggle */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Condition Logic</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => updateConfig('gate_logic', 'all')}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                      (currentConfig?.gate_logic || 'all') === 'all'
                        ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400'
                        : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    ALL (AND)
                  </button>
                  <button
                    type="button"
                    onClick={() => updateConfig('gate_logic', 'any')}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                      currentConfig?.gate_logic === 'any'
                        ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400'
                        : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    ANY (OR)
                  </button>
                </div>
              </div>

              {/* Conditions List */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Conditions</label>
                <div className="space-y-2">
                  {(currentConfig?.gate_conditions || []).map((cond: any, ci: number) => (
                    <div key={ci} className="flex gap-2 items-start p-2 bg-slate-800/50 rounded-lg border border-slate-700">
                      <div className="flex-1 grid grid-cols-4 gap-2">
                        <CursorSafeInput
                          type="text"
                          value={cond.field || ''}
                          onValueChange={(v) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], field: v }
                            updateConfig('gate_conditions', updated)
                          }}
                          placeholder="e.g. count"
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        />
                        <select
                          value={cond.operator || '=='}
                          onChange={(e) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], operator: e.target.value }
                            updateConfig('gate_conditions', updated)
                          }}
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        >
                          <optgroup label="Numeric">
                            <option value="==">==</option>
                            <option value="!=">!=</option>
                            <option value=">">&gt;</option>
                            <option value=">=">&gt;=</option>
                            <option value="<">&lt;</option>
                            <option value="<=">&lt;=</option>
                          </optgroup>
                          <optgroup label="String">
                            <option value="contains">contains</option>
                            <option value="not_contains">not_contains</option>
                            <option value="starts_with">starts_with</option>
                            <option value="ends_with">ends_with</option>
                          </optgroup>
                          <optgroup label="Regex">
                            <option value="matches">matches</option>
                          </optgroup>
                          <optgroup label="Existence">
                            <option value="is_empty">is_empty</option>
                            <option value="is_not_empty">is_not_empty</option>
                          </optgroup>
                          <optgroup label="Collection">
                            <option value="count_gte">count_gte</option>
                            <option value="count_lte">count_lte</option>
                          </optgroup>
                        </select>
                        <CursorSafeInput
                          type="text"
                          value={cond.value ?? ''}
                          onValueChange={(v) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], value: v }
                            updateConfig('gate_conditions', updated)
                          }}
                          placeholder="value"
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        />
                        <select
                          value={cond.type || 'string'}
                          onChange={(e) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], type: e.target.value }
                            updateConfig('gate_conditions', updated)
                          }}
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        >
                          <option value="number">number</option>
                          <option value="string">string</option>
                          <option value="boolean">boolean</option>
                          <option value="regex">regex</option>
                          <option value="count">count</option>
                        </select>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          const updated = (currentConfig?.gate_conditions || []).filter((_: any, i: number) => i !== ci)
                          updateConfig('gate_conditions', updated)
                        }}
                        className="p-1.5 text-slate-500 hover:text-red-400 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const updated = [...(currentConfig?.gate_conditions || []), { field: '', operator: '==', value: '', type: 'string' }]
                    updateConfig('gate_conditions', updated)
                  }}
                  className="mt-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-dashed border-slate-600
                             text-slate-400 hover:border-cyan-500/50 hover:text-cyan-400 transition-colors"
                >
                  + Add Condition
                </button>
              </div>
            </>
          )}

          {/* Agentic Mode Panel */}
          {currentConfig?.gate_mode === 'agentic' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Source Step</label>
                <CursorSafeInput
                  type="text"
                  value={currentConfig?.gate_source_step || ''}
                  onValueChange={(v) => updateConfig('gate_source_step', v)}
                  placeholder="e.g. inbox, step_1"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                />
                <p className="text-xs text-slate-500 mt-1">Step whose output the AI evaluates</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Gate Prompt</label>
                <TemplateTextarea
                  value={currentConfig?.gate_prompt || ''}
                  onValueChange={(v) => updateConfig('gate_prompt', v)}
                  rows={4}
                  placeholder="Describe when the gate should PASS... Use {{step_N.field}} to reference previous step outputs."
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                  allSteps={stepInfoList}
                  currentStepPosition={step.position}
                />
              </div>

              <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/5 border border-amber-500/20 rounded-lg">
                <svg className="w-4 h-4 text-amber-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
                </svg>
                <span className="text-xs text-amber-400">Uses AI tokens &mdash; will incur LLM cost</span>
              </div>
            </>
          )}

          {/* Common: On Fail Action */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">On Fail Action</label>
            <select
              value={currentConfig?.gate_on_fail || 'skip'}
              onChange={(e) => updateConfig('gate_on_fail', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="skip">Skip remaining steps (silent)</option>
              <option value="notify">Send notification, then stop</option>
            </select>
          </div>

          {/* Notify sub-fields */}
          {currentConfig?.gate_on_fail === 'notify' && (
            <div className="space-y-3 pl-4 border-l-2 border-amber-500/30">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Channel</label>
                <select
                  value={currentConfig?.gate_fail_notification?.channel || 'whatsapp'}
                  onChange={(e) => updateConfig('gate_fail_notification', {
                    ...currentConfig?.gate_fail_notification,
                    channel: e.target.value
                  })}
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                >
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                  <option value="slack">Slack</option>
                  <option value="discord">Discord</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Recipient</label>
                <TemplateInput
                  value={currentConfig?.gate_fail_notification?.recipient || ''}
                  onValueChange={(v) => updateConfig('gate_fail_notification', {
                    ...currentConfig?.gate_fail_notification,
                    recipient: v
                  })}
                  placeholder="e.g. +5527999999999 or {{step_N.field}}"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                  allSteps={stepInfoList}
                  currentStepPosition={step.position}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Message Template</label>
                <TemplateTextarea
                  value={currentConfig?.gate_fail_notification?.message_template || ''}
                  onValueChange={(v) => updateConfig('gate_fail_notification', {
                    ...currentConfig?.gate_fail_notification,
                    message_template: v
                  })}
                  rows={3}
                  placeholder="Gate blocked: {{gate.reasoning}}"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                  allSteps={stepInfoList}
                  currentStepPosition={step.position}
                />
              </div>
            </div>
          )}

          {/* Tips */}
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-xs text-slate-400">
              <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><ShieldCheckIcon size={12} /> Gate Tips:</span>
              <br />{'•'} <strong>Programmatic</strong> mode is zero-cost {'—'} no AI tokens used
              <br />{'•'} <strong>Agentic</strong> mode uses LLM for complex decisions
              <br />{'•'} Reference gate output with {'{{'}step_N.gate_result{'}}'} in subsequent steps
            </p>
          </div>
        </>
      )}

      {/* Agent & Persona Selection */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Agent</label>
          <select
            value={currentStep.agent_id || ''}
            onChange={(e) => debouncedSave({ agent_id: e.target.value ? parseInt(e.target.value) : undefined })}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          >
            <option value="">Use default</option>
            {agents.map(agent => (
              <option key={agent.id} value={agent.id}>{agent.contact_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Persona</label>
          <select
            value={currentStep.persona_id || ''}
            onChange={(e) => debouncedSave({ persona_id: e.target.value ? parseInt(e.target.value) : undefined })}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          >
            <option value="">Use default</option>
            {personas.map(persona => (
              <option key={persona.id} value={persona.id}>{persona.name}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

// ==================== EDITABLE STEP BUILDER ====================

function EditableStepBuilder({
  flowId,
  steps,
  agents,
  contacts,
  personas,
  customTools,
  customSkills,
  onStepsChange,
  flushCallbacksRef
}: {
  flowId: number
  steps: EditableStepData[]
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  customSkills?: any[]
  onStepsChange: (steps: EditableStepData[]) => void
  flushCallbacksRef?: React.MutableRefObject<Map<number, () => void>>
}) {
  const toast = useToast()
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [showAddStep, setShowAddStep] = useState(steps.length === 0)
  const [savingSteps, setSavingSteps] = useState<Set<number>>(new Set())

  // Add a new step
  async function addStep(stepType: StepType) {
    // v0.7.0 Wave 2: source step is locked at position 0 and capped at 1 per flow.
    if (stepType === 'source') {
      if (steps.some((s) => s.type === 'source')) return
      const newStep: EditableStepData = {
        name: 'Source',
        type: 'source',
        position: 1,
        config: {},
        allow_multi_turn: false,
        max_turns: undefined,
        _saving: true,
      }
      const tempSteps = [newStep, ...steps].map((s, i) => ({ ...s, position: i + 1 }))
      onStepsChange(tempSteps)
      setShowAddStep(false)
      try {
        const created = await api.createFlowStep(flowId, editableToCreatePayload(newStep) as any)
        // Replace temp source step (now at index 0) with the real one and
        // re-emit the rest with bumped positions.
        const finalSteps = tempSteps.map((s, i) =>
          i === 0 ? flowNodeToEditable(created) : s
        )
        onStepsChange(finalSteps)
        setEditingIndex(0)
      } catch (error) {
        console.error('Failed to create source step:', error)
        onStepsChange(steps)
        toast.error('Step Error', 'Failed to create source step')
      }
      return
    }

    const newPosition = steps.length + 1
    const newStep: EditableStepData = {
      name: `Step ${newPosition}`,
      type: stepType,
      position: newPosition,
      config: ['message', 'notification', 'conversation'].includes(stepType) ? { channel: 'whatsapp' } : {},
      allow_multi_turn: stepType === 'conversation',
      max_turns: stepType === 'conversation' ? 20 : undefined,
      _saving: true,
    }

    // Optimistically add to UI
    const tempSteps = [...steps, newStep]
    onStepsChange(tempSteps)
    setShowAddStep(false)

    try {
      const created = await api.createFlowStep(flowId, editableToCreatePayload(newStep) as any)
      // Replace temp step with real one
      const finalSteps = tempSteps.map((s, i) =>
        i === tempSteps.length - 1 ? flowNodeToEditable(created) : s
      )
      onStepsChange(finalSteps)
      setEditingIndex(finalSteps.length - 1)
    } catch (error) {
      console.error('Failed to create step:', error)
      // Remove the temp step on error
      onStepsChange(steps)
      toast.error('Step Error', 'Failed to create step')
    }
  }

  // Update an existing step
  async function updateStep(index: number, update: Partial<EditableStepData>) {
    const step = steps[index]
    if (!step.id) return // Can't update unsaved step

    const updatedStep = { ...step, ...update, _saving: true }
    const newSteps = [...steps]
    newSteps[index] = updatedStep
    onStepsChange(newSteps)

    setSavingSteps(prev => new Set(prev).add(step.id!))

    try {
      const payload = editableToUpdatePayload(updatedStep)
      await api.updateFlowStep(flowId, step.id, payload)

      // Mark as saved
      const savedSteps = [...newSteps]
      savedSteps[index] = { ...savedSteps[index], _saving: false, _error: null }
      onStepsChange(savedSteps)
    } catch (error) {
      console.error('Failed to update step:', error)
      // Mark error but keep changes
      const errorSteps = [...newSteps]
      errorSteps[index] = { ...errorSteps[index], _saving: false, _error: 'Failed to save' }
      onStepsChange(errorSteps)
    } finally {
      setSavingSteps(prev => {
        const next = new Set(prev)
        next.delete(step.id!)
        return next
      })
    }
  }

  // Delete a step
  async function deleteStep(index: number) {
    const step = steps[index]
    // v0.7.0 Wave 2: source step is non-removable while present.
    if (step?.type === 'source') return
    if (!step.id) {
      // Just remove unsaved step
      const newSteps = steps.filter((_, i) => i !== index)
      newSteps.forEach((s, i) => s.position = i + 1)
      onStepsChange(newSteps)
      setEditingIndex(null)
      return
    }

    if (!confirm('Delete this step? This cannot be undone.')) return

    // Optimistically remove
    const newSteps = steps.filter((_, i) => i !== index)
    newSteps.forEach((s, i) => s.position = i + 1)
    onStepsChange(newSteps)
    setEditingIndex(null)

    try {
      await api.deleteFlowStep(flowId, step.id)

      // Update positions of remaining steps
      for (const s of newSteps) {
        if (s.id && s.position !== steps.find(orig => orig.id === s.id)?.position) {
          await api.updateFlowStep(flowId, s.id, { position: s.position })
        }
      }
    } catch (error) {
      console.error('Failed to delete step:', error)
      // Restore on error
      onStepsChange(steps)
      toast.error('Step Error', 'Failed to delete step')
    }
  }

  // Move step up or down
  async function moveStep(index: number, direction: 'up' | 'down') {
    if ((direction === 'up' && index === 0) || (direction === 'down' && index === steps.length - 1)) return

    // v0.7.0 Wave 2: source step is locked at position 0; never move it,
    // and never allow another step to slide above it.
    const movingStep = steps[index]
    if (movingStep?.type === 'source') return
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (steps[targetIndex]?.type === 'source') return

    const newSteps = [...steps]
      ;[newSteps[index], newSteps[targetIndex]] = [newSteps[targetIndex], newSteps[index]]

    // Update positions and auto-rename "Step N" names to match new position
    newSteps.forEach((step, i) => {
      step.position = i + 1
      if (/^Step \d+$/.test(step.name)) {
        step.name = `Step ${i + 1}`
      }
    })
    onStepsChange(newSteps)

    // Use atomic reorder endpoint to avoid unique constraint issues
    const reorderPayload = newSteps
      .filter(s => s.id)
      .map(s => ({ step_id: s.id!, position: s.position, name: s.name }))

    if (reorderPayload.length > 0) {
      try {
        await api.reorderFlowSteps(flowId, reorderPayload)
      } catch (error) {
        console.error('Failed to reorder steps:', error)
        // Restore original order on error
        const restored = [...newSteps]
          ;[restored[index], restored[targetIndex]] = [restored[targetIndex], restored[index]]
        restored.forEach((step, i) => {
          step.position = i + 1
          if (/^Step \d+$/.test(step.name)) {
            step.name = `Step ${i + 1}`
          }
        })
        onStepsChange(restored)
      }
    }
  }

  return (
    <div className="space-y-4">
      {/* Steps List */}
      {steps.length > 0 && (
        <div className="space-y-3">
          {steps.map((step, index) => (
            <div
              key={step.id || `new-${index}`}
              className={`rounded-xl border transition-all ${editingIndex === index
                  ? 'border-cyan-500 bg-cyan-500/5'
                  : step._error
                    ? 'border-red-500/50 bg-red-500/5'
                    : 'border-slate-700 bg-slate-700/30 hover:border-slate-600'
                }`}
            >
              {/* Step Header */}
              <div
                className="p-4 flex items-center gap-4 cursor-pointer"
                onClick={() => setEditingIndex(editingIndex === index ? null : index)}
              >
                {/* Reorder buttons */}
                <div className="flex flex-col gap-1">
                  {/* v0.7.0 Wave 2: source step is locked at position 0; hide reorder buttons. */}
                  {step.type !== 'source' && (
                    <>
                      <button
                        onClick={(e) => { e.stopPropagation(); moveStep(index, 'up') }}
                        disabled={index === 0 || steps[index - 1]?.type === 'source'}
                        className="text-slate-500 hover:text-white disabled:opacity-30"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); moveStep(index, 'down') }}
                        disabled={index === steps.length - 1}
                        className="text-slate-500 hover:text-white disabled:opacity-30"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </>
                  )}
                </div>

                {/* Step icon */}
                <div className="w-10 h-10 rounded-lg bg-slate-600 flex items-center justify-center text-slate-300">
                  {(() => {
                    const stepType = STEP_TYPES.find(t => t.value === step.type)
                    if (stepType) {
                      const StepIcon = stepType.Icon
                      return <StepIcon size={20} />
                    }
                    return <span className="text-xl">❓</span>
                  })()}
                </div>

                {/* Step info */}
                <div className="flex-1">
                  <div className="font-medium text-white flex items-center gap-2">
                    {step.name}
                    {step.type === 'source' && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30">
                        Locked at top
                      </span>
                    )}
                    {step.type === 'gate' && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        (step.config?.gate_mode || 'programmatic') === 'programmatic'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                      }`}>
                        {(step.config?.gate_mode || 'programmatic') === 'programmatic' ? 'Programmatic' : 'Agentic'}
                      </span>
                    )}
                    {step._saving && (
                      <span className="text-xs text-cyan-400">Saving...</span>
                    )}
                    {step._error && (
                      <span className="text-xs text-red-400">{step._error}</span>
                    )}
                  </div>
                  <div className="text-sm text-slate-400">
                    {STEP_TYPES.find(t => t.value === step.type)?.label}
                    {step.allow_multi_turn && ' • Multi-turn'}
                    {step.type === 'gate' && step.config?.gate_conditions && step.config.gate_conditions.length > 0 && (
                      <span className="text-xs text-slate-500 ml-1">
                        • {step.config.gate_conditions.length} condition{step.config.gate_conditions.length !== 1 ? 's' : ''} ({step.config?.gate_logic || 'all'})
                      </span>
                    )}
                    {step.type === 'gate' && step.config?.gate_mode === 'agentic' && step.config?.gate_prompt && (
                      <span className="text-xs text-slate-500 ml-1">
                        • AI prompt set
                      </span>
                    )}
                  </div>
                </div>

                {/* Delete button (v0.7.0 Wave 2: hide for source step) */}
                {step.type !== 'source' && (
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteStep(index) }}
                    className="text-red-400 hover:text-red-300 p-2"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                )}

                {/* Expand/collapse indicator */}
                <svg className={`w-5 h-5 text-slate-400 transition-transform ${editingIndex === index ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>

              {/* Step Config (Expanded) */}
              {editingIndex === index && (
                <div className="px-4 pb-4 pt-2 border-t border-slate-700/50 space-y-4">
                  <EditableStepConfigForm
                    step={step}
                    agents={agents}
                    contacts={contacts}
                    personas={personas}
                    customTools={customTools}
                    customSkills={customSkills}
                    onChange={(update) => updateStep(index, update)}
                    flushCallbacksRef={flushCallbacksRef}
                    allSteps={steps}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add Step Section */}
      {showAddStep ? (
        <div className="rounded-xl border border-dashed border-slate-600 p-6">
          <h4 className="text-sm font-medium text-slate-300 mb-4">Add a Step</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {/* v0.7.0 Wave 2: hide 'source' if a source step already exists (max 1 per flow). */}
            {STEP_TYPES.filter((type) => type.value !== 'source' || !steps.some((s) => s.type === 'source')).map(type => {
              const StepIcon = type.Icon
              return (
                <button
                  key={type.value}
                  onClick={() => addStep(type.value)}
                  className="p-4 rounded-lg border border-slate-700 hover:border-cyan-500/50 hover:bg-cyan-500/5
                             text-center transition-all text-slate-300 hover:text-cyan-400"
                >
                  <div className="flex justify-center">
                    <StepIcon size={28} />
                  </div>
                  <div className="text-sm text-white mt-2">{type.label}</div>
                  <div className="text-xs text-slate-500 mt-1">{type.description}</div>
                </button>
              )
            })}
          </div>
          {steps.length > 0 && (
            <button
              onClick={() => setShowAddStep(false)}
              className="mt-4 text-sm text-slate-400 hover:text-white"
            >
              Cancel
            </button>
          )}
        </div>
      ) : (
        <button
          onClick={() => setShowAddStep(true)}
          className="w-full py-3 rounded-xl border border-dashed border-slate-600 text-slate-400
                     hover:border-cyan-500/50 hover:text-cyan-400 transition-all flex items-center justify-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Step
        </button>
      )}
    </div>
  )
}

// ==================== EDITABLE STEP CONFIG FORM ====================

function EditableStepConfigForm({ step, agents, contacts, personas, customTools, customSkills, onChange, flushCallbacksRef, allSteps }: {
  step: EditableStepData
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  customSkills?: any[]
  onChange: (update: Partial<EditableStepData>) => void
  flushCallbacksRef?: React.MutableRefObject<Map<number, () => void>>
  allSteps: EditableStepData[]
}) {
  const [recipientInput, setRecipientInput] = useState(step.config?.recipient || '')
  const [showContactSuggestions, setShowContactSuggestions] = useState(false)
  const [localChanges, setLocalChanges] = useState<Partial<EditableStepData>>({})
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const pendingChangesRef = useRef<Partial<EditableStepData>>({})
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  useEffect(() => {
    setRecipientInput(step.config?.recipient || '')
    setLocalChanges({})
    pendingChangesRef.current = {}
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current)
      saveTimeoutRef.current = null
    }
  }, [step.id])

  // Register flush callback so handleSave can force-flush pending changes before closing
  useEffect(() => {
    if (!flushCallbacksRef || !step.id) return
    const flush = () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
        saveTimeoutRef.current = null
      }
      const pending = pendingChangesRef.current
      if (Object.keys(pending).length > 0) {
        onChangeRef.current(pending)
        pendingChangesRef.current = {}
      }
    }
    flushCallbacksRef.current.set(step.id, flush)
    return () => { flushCallbacksRef.current.delete(step.id) }
  }, [step.id, flushCallbacksRef])

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      // Flush any pending changes on unmount so edits are not lost
      const pending = pendingChangesRef.current
      if (Object.keys(pending).length > 0) {
        onChangeRef.current(pending)
        pendingChangesRef.current = {}
      }
    }
  }, [])

  // Debounced save
  function debouncedSave(
    update: Partial<EditableStepData> | ((prev: Partial<EditableStepData>) => Partial<EditableStepData>)
  ) {
    setLocalChanges(prev => {
      const nextUpdate = typeof update === 'function' ? update(prev) : update
      const merged = { ...prev, ...nextUpdate }
      pendingChangesRef.current = merged
      return merged
    })

    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current)
    saveTimeoutRef.current = setTimeout(() => {
      const pending = pendingChangesRef.current
      if (Object.keys(pending).length > 0) {
        onChange(pending)
        pendingChangesRef.current = {}
      }
    }, 500)
  }

  const filteredContacts = contacts.filter(c => {
    // Show all contacts when input is empty
    if (!recipientInput) return true
    const search = recipientInput.startsWith('@') ? recipientInput.slice(1).toLowerCase() : recipientInput.toLowerCase()
    return c.friendly_name.toLowerCase().includes(search) ||
      c.phone_number?.toLowerCase().includes(search)
  })

  function updateConfig(key: string, value: any) {
    debouncedSave(prev => ({
      config: { ...step.config, ...prev.config, [key]: value }
    }))
  }

  // Get current value considering local changes
  const currentStep = { ...step, ...localChanges }
  const currentConfig = { ...step.config, ...localChanges.config }

  // Variable Reference panel input — shared across all templatable fields.
  const stepInfoList = allSteps.map(s => ({
    name: s.name,
    type: s.type,
    position: s.position,
    config: s.config,
  }))

  return (
    <div className="space-y-4">
      {/* Step Name */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">Step Name</label>
        <CursorSafeInput
          type="text"
          value={currentStep.name || ''}
          onValueChange={(v) => debouncedSave({ name: v })}
          className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
        />
      </div>

      {/* v0.7.0 Wave 4: Source step renders trigger summary + sample payload + variable hint. */}
      {step.type === 'source' && (
        <SourceStepConfig config={(step.config as Record<string, any>) || {}} />
      )}

      {/* Channel Selector - for message/notification/conversation */}
      {['message', 'notification', 'conversation'].includes(step.type) && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Channel</label>
          <div className="grid grid-cols-2 gap-2">
            {CHANNEL_OPTIONS.map(ch => {
              const ChIcon = ch.Icon
              const isSelected = (currentConfig?.channel || 'whatsapp') === ch.value
              return (
                <button
                  key={ch.value}
                  type="button"
                  disabled={!ch.enabled}
                  onClick={() => ch.enabled && updateConfig('channel', ch.value)}
                  className={`relative flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-all
                    ${isSelected && ch.enabled
                      ? 'border-cyan-500 bg-cyan-500/10 text-white'
                      : !ch.enabled
                        ? 'border-slate-700 bg-slate-800/50 text-slate-500 cursor-not-allowed opacity-60'
                        : 'border-slate-600 hover:border-slate-500 text-slate-300'
                    }`}
                >
                  <ChIcon size={18} className={isSelected && ch.enabled ? ch.activeColor : ''} />
                  <span>{ch.label}</span>
                  {ch.badge && (
                    <span className="absolute -top-2 -right-1 px-1.5 py-0.5 text-[10px] font-medium
                                   bg-slate-700 text-slate-400 rounded-full border border-slate-600">
                      {ch.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Recipient - for message/notification/conversation */}
      {['message', 'notification', 'conversation'].includes(step.type) && (
        <div className="relative">
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Recipient</label>
          <input
            type="text"
            value={recipientInput}
            onChange={(e) => {
              setRecipientInput(e.target.value)
              updateConfig('recipient', e.target.value)
            }}
            onFocus={() => setShowContactSuggestions(true)}
            onBlur={() => setTimeout(() => setShowContactSuggestions(false), 200)}
            placeholder="Select contact or enter phone number (e.g., +5527999999999)"
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          />
          {showContactSuggestions && contacts.length > 0 && (
            <div className="absolute z-10 w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl max-h-60 overflow-y-auto">
              {filteredContacts.length > 0 ? (
                filteredContacts.map(contact => (
                  <div
                    key={contact.id}
                    onClick={() => {
                      setRecipientInput(`@${contact.friendly_name}`)
                      updateConfig('recipient', `@${contact.friendly_name}`)
                      setShowContactSuggestions(false)
                    }}
                    className="px-3 py-2 hover:bg-slate-700 cursor-pointer transition-colors"
                  >
                    <div className="text-sm font-medium text-white">@{contact.friendly_name}</div>
                    {contact.phone_number && (
                      <div className="text-xs text-slate-400">{contact.phone_number}</div>
                    )}
                  </div>
                ))
              ) : (
                <div className="px-3 py-2 text-sm text-slate-400">
                  No contacts found. Type a phone number to continue.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Message Template - for message/notification */}
      {['message', 'notification'].includes(step.type) && (
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">
            {step.type === 'notification' ? 'Notification Text' : 'Message Template'}
          </label>
          <TemplateTextarea
            value={step.type === 'notification'
              ? (currentConfig?.content || '')
              : (currentConfig?.message_template || '')}
            onValueChange={(v) => updateConfig(step.type === 'notification' ? 'content' : 'message_template', v)}
            rows={3}
            placeholder={step.type === 'notification'
              ? 'What to notify about? Use {{step_1.field}} to inject previous step outputs'
              : 'Enter your message... Use {{step_1.field}} to inject previous step outputs'}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
            allSteps={stepInfoList}
            currentStepPosition={step.position}
          />
        </div>
      )}

      {/* Conversation Settings */}
      {step.type === 'conversation' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Conversation Objective</label>
            <TemplateTextarea
              value={currentStep.conversation_objective || currentConfig?.objective || ''}
              onValueChange={(v) => {
                debouncedSave(prev => ({
                  conversation_objective: v,
                  config: { ...step.config, ...prev.config, objective: v }
                }))
              }}
              rows={2}
              placeholder="What should this conversation achieve? Use {{step_N.field}} to inject previous step outputs."
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Initial Prompt</label>
            <TemplateTextarea
              value={currentConfig?.initial_prompt || ''}
              onValueChange={(v) => updateConfig('initial_prompt', v)}
              rows={2}
              placeholder="First message to send... Use {{step_N.field}} to inject previous step outputs."
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Max Turns</label>
              <input
                type="number"
                value={currentStep.max_turns || 20}
                onChange={(e) => debouncedSave({ max_turns: parseInt(e.target.value) })}
                min={1}
                max={100}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Timeout (seconds)</label>
              <input
                type="number"
                value={currentStep.timeout_seconds || 3600}
                onChange={(e) => debouncedSave({ timeout_seconds: parseInt(e.target.value) })}
                min={60}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Output Alias (optional)
              <span className="text-slate-500 text-xs ml-2">For referencing in later steps</span>
            </label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.output_alias || ''}
              onValueChange={(v) => updateConfig('output_alias', v)}
              placeholder="e.g. conversation_result"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
          </div>
        </>
      )}

      {/* Tool Settings */}
      {step.type === 'tool' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Tool Type</label>
            <select
              value={currentConfig?.tool_type || 'built_in'}
              onChange={(e) => {
                // Combine both updates into a single atomic operation to prevent race condition
                debouncedSave({ config: { ...step.config, ...localChanges.config, tool_type: e.target.value, tool_name: '' } })
              }}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="built_in">Built-in Tools</option>
              <option value="custom">Sandboxed Tools</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Tool Name</label>
            <select
              value={currentConfig?.tool_name || ''}
              onChange={(e) => updateConfig('tool_name', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="">Select a tool...</option>
              {(currentConfig?.tool_type || 'built_in') === 'built_in' ? (
                <>
                  <option value="google_search">Google Search</option>
                  <option value="send_message">Send Message</option>
                </>
              ) : (
                customTools.length === 0 ? (
                  <option value="" disabled>No sandboxed tools available</option>
                ) : (
                  customTools.map(tool => (
                    <option key={tool.id} value={tool.id.toString()}>
                      {tool.name} ({tool.tool_type})
                    </option>
                  ))
                )
              )}
            </select>
          </div>

          {/* Tool Parameters Dynamic Form */}
          <ToolParameterForm
            toolType={(currentConfig?.tool_type || 'built_in') as 'built_in' | 'custom'}
            toolId={currentConfig?.tool_name || currentConfig?.tool_id}
            commandId={currentConfig?.command_id}
            parameters={currentConfig?.tool_parameters || {}}
            onChange={(params) => updateConfig('tool_parameters', params)}
            onCommandChange={(cmdId) => updateConfig('command_id', cmdId)}
          />

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Output Alias (optional)
              <span className="text-slate-500 text-xs ml-2">For referencing in later steps</span>
            </label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.output_alias || ''}
              onValueChange={(v) => updateConfig('output_alias', v)}
              placeholder="e.g. scan_results"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
          </div>
        </>
      )}

      {/* Skill Settings */}
      {step.type === 'skill' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Skill Type</label>
            <select
              value={currentConfig?.skill_type || ''}
              onChange={(e) => updateConfig('skill_type', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="">Select a skill...</option>
              <optgroup label="Built-in Skills">
                {AVAILABLE_SKILLS.map(skill => (
                  <option key={skill.value} value={skill.value}>
                    {skill.label}
                  </option>
                ))}
              </optgroup>
              {customSkills && customSkills.length > 0 && (
                <optgroup label="Custom Skills">
                  {customSkills.map((s: any) => (
                    <option key={`custom:${s.slug}`} value={`custom:${s.slug}`}>
                      {s.icon || '\uD83E\uDDE9'} {s.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            {currentConfig?.skill_type && (
              <p className="text-xs text-slate-500 mt-1">
                {AVAILABLE_SKILLS.find(s => s.value === currentConfig?.skill_type)?.description
                  || customSkills?.find((s: any) => `custom:${s.slug}` === currentConfig?.skill_type)?.description
                  || ''}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Prompt
              <span className="text-slate-500 text-xs ml-2">Natural language instruction for the skill</span>
            </label>
            <TemplateTextarea
              value={currentConfig?.prompt || ''}
              onValueChange={(v) => updateConfig('prompt', v)}
              rows={3}
              placeholder="e.g., busque voos de VIX para CGH dia 16 de Março de 2026 em BRL"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
            <p className="text-xs text-slate-500 mt-1">
              <span className="inline-flex items-center gap-1"><LightbulbIcon size={12} /> Write as if you were asking the agent directly. Use {'{{'}step_N.field{'}}'} to inject data from previous steps.</span>
            </p>
          </div>

          {/* Skill-specific configuration hints */}
          {currentConfig?.skill_type === 'flight_search' && (
            <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
              <p className="text-xs text-slate-400">
                <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><PlaneIcon size={12} /> Flight Search Tips:</span> Include origin, destination, date, and currency.
                <br />Example: "busque voos de VIX para GRU dia 20 de Janeiro de 2026 em BRL"
              </p>
            </div>
          )}
          {currentConfig?.skill_type === 'scheduler' && (
            <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
              <p className="text-xs text-slate-400">
                <span className="text-cyan-400 font-medium">📅 Scheduler Tips:</span> Be specific about date, time, and event details.
                <br />Example: "agende uma reunião para amanhã às 14h com título Sync Semanal"
              </p>
            </div>
          )}

          {/* Output Alias for Step Output Injection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Output Alias (optional)
              <span className="text-slate-500 text-xs ml-2">For referencing in later steps</span>
            </label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.output_alias || ''}
              onValueChange={(v) => updateConfig('output_alias', v)}
              placeholder="e.g. flight_results"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">
              Use in subsequent steps as: {'{{'}output_alias.output{'}}'} or {'{{'}step_N.output{'}}'}
            </p>
          </div>
        </>
      )}

      {/* Summarization Settings */}
      {step.type === 'summarization' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Source Step</label>
            <CursorSafeInput
              type="text"
              value={currentConfig?.source_step || ''}
              onValueChange={(v) => updateConfig('source_step', v)}
              placeholder="step_1 or step name"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            <p className="text-xs text-slate-500 mt-1">
              Reference the conversation step to summarize (e.g., step_1)
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Output Format</label>
              <select
                value={currentConfig?.output_format || 'brief'}
                onChange={(e) => updateConfig('output_format', e.target.value)}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              >
                {SUMMARIZATION_OUTPUT_FORMATS.map(fmt => (
                  <option key={fmt.value} value={fmt.value}>{fmt.label}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-1">
                {SUMMARIZATION_OUTPUT_FORMATS.find(f => f.value === (currentConfig?.output_format || 'brief'))?.description}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Prompt Mode</label>
              <select
                value={currentConfig?.prompt_mode || 'append'}
                onChange={(e) => updateConfig('prompt_mode', e.target.value)}
                className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                           focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
              >
                {SUMMARIZATION_PROMPT_MODES.map(mode => (
                  <option key={mode.value} value={mode.value}>{mode.label}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-1">
                {SUMMARIZATION_PROMPT_MODES.find(m => m.value === (currentConfig?.prompt_mode || 'append'))?.description}
              </p>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Custom Prompt
              <span className="text-slate-500 text-xs ml-2">
                {currentConfig?.prompt_mode === 'replace' ? '(Full prompt)' : '(Added to default)'}
              </span>
            </label>
            <TemplateTextarea
              value={currentConfig?.summary_prompt || ''}
              onValueChange={(v) => updateConfig('summary_prompt', v)}
              rows={4}
              placeholder={currentConfig?.prompt_mode === 'replace'
                ? 'Enter your complete summarization instructions...\n\nExample:\nExtract only:\n📍 Status: [value]\n📅 Date: [value]'
                : 'Additional instructions to add to the default summary template...'}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none font-mono"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">AI Model</label>
            <select
              value={currentConfig?.model || 'gemini-2.5-flash'}
              onChange={(e) => updateConfig('model', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              {SUMMARIZATION_MODELS.map(model => (
                <option key={model.value} value={model.value}>{model.label}</option>
              ))}
            </select>
          </div>

          {/* Tips for summarization */}
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-xs text-slate-400">
              <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><DocumentIcon size={12} /> Summarization Tips:</span>
              <br />• Use <strong>minimal</strong> format + <strong>replace</strong> mode for concise notifications
              <br />• Use <strong>structured</strong> format for detailed reports
              <br />• Reference with {'{{'}step_N.summary{'}}'} in subsequent steps
            </p>
          </div>
        </>
      )}

      {/* Slash Command Settings */}
      {step.type === 'slash_command' && (
        <>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Command *</label>
            <TemplateInput
              value={currentConfig?.command || ''}
              onValueChange={(v) => updateConfig('command', v)}
              placeholder="/scheduler list week"
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none font-mono"
              allSteps={stepInfoList}
              currentStepPosition={step.position}
            />
            <p className="text-xs text-slate-500 mt-1">
              Enter the slash command to execute (e.g., /scheduler list week, /memory search &lt;query&gt;)
            </p>
          </div>

          {/* Note: Agent override for slash_command uses the step's agent_id field,
              which is handled in the Agent & Persona Selection section below */}

          {/* Available slash commands reference */}
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-xs text-slate-400">
              <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><CommandIcon size={12} /> Available Commands:</span>
              <br />• <code className="text-amber-400">/scheduler</code> - Manage scheduled events (list, add, remove)
              <br />• <code className="text-amber-400">/memory</code> - Search and manage agent memory
              <br />• <code className="text-amber-400">/flows</code> - List and manage flows
              <br />• <code className="text-amber-400">/personas</code> - List and switch personas
              <br />• <code className="text-amber-400">/help</code> - Show available commands
            </p>
            <p className="text-xs text-slate-500 mt-2">
              Output available as {'{{'}step_N.output{'}}'} in subsequent steps
            </p>
          </div>
        </>
      )}

      {/* Gate Settings */}
      {step.type === 'gate' && (
        <>
          {/* Mode Toggle */}
          <div>
            <label className="block text-sm font-semibold text-slate-200 mb-2">Gate Mode</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => updateConfig('gate_mode', 'programmatic')}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-all ${
                  (currentConfig?.gate_mode || 'programmatic') === 'programmatic'
                    ? 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400'
                    : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                }`}
              >
                Programmatic
              </button>
              <button
                type="button"
                onClick={() => updateConfig('gate_mode', 'agentic')}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-all ${
                  currentConfig?.gate_mode === 'agentic'
                    ? 'bg-amber-500/10 border-amber-500/50 text-amber-400'
                    : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                }`}
              >
                Agentic (AI)
              </button>
            </div>
          </div>

          {/* Programmatic Mode Panel */}
          {(currentConfig?.gate_mode || 'programmatic') === 'programmatic' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Source Step</label>
                <CursorSafeInput
                  type="text"
                  value={currentConfig?.gate_source_step || ''}
                  onValueChange={(v) => updateConfig('gate_source_step', v)}
                  placeholder="e.g. inbox, step_1"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                />
                <p className="text-xs text-slate-500 mt-1">Step whose output the gate evaluates</p>
              </div>

              {/* Logic Toggle */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Condition Logic</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => updateConfig('gate_logic', 'all')}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                      (currentConfig?.gate_logic || 'all') === 'all'
                        ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400'
                        : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    ALL (AND)
                  </button>
                  <button
                    type="button"
                    onClick={() => updateConfig('gate_logic', 'any')}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
                      currentConfig?.gate_logic === 'any'
                        ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400'
                        : 'bg-slate-700/30 border-slate-600 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    ANY (OR)
                  </button>
                </div>
              </div>

              {/* Conditions List */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Conditions</label>
                <div className="space-y-2">
                  {(currentConfig?.gate_conditions || []).map((cond: any, ci: number) => (
                    <div key={ci} className="flex gap-2 items-start p-2 bg-slate-800/50 rounded-lg border border-slate-700">
                      <div className="flex-1 grid grid-cols-4 gap-2">
                        <CursorSafeInput
                          type="text"
                          value={cond.field || ''}
                          onValueChange={(v) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], field: v }
                            updateConfig('gate_conditions', updated)
                          }}
                          placeholder="e.g. count"
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        />
                        <select
                          value={cond.operator || '=='}
                          onChange={(e) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], operator: e.target.value }
                            updateConfig('gate_conditions', updated)
                          }}
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        >
                          <optgroup label="Numeric">
                            <option value="==">==</option>
                            <option value="!=">!=</option>
                            <option value=">">&gt;</option>
                            <option value=">=">&gt;=</option>
                            <option value="<">&lt;</option>
                            <option value="<=">&lt;=</option>
                          </optgroup>
                          <optgroup label="String">
                            <option value="contains">contains</option>
                            <option value="not_contains">not_contains</option>
                            <option value="starts_with">starts_with</option>
                            <option value="ends_with">ends_with</option>
                          </optgroup>
                          <optgroup label="Regex">
                            <option value="matches">matches</option>
                          </optgroup>
                          <optgroup label="Existence">
                            <option value="is_empty">is_empty</option>
                            <option value="is_not_empty">is_not_empty</option>
                          </optgroup>
                          <optgroup label="Collection">
                            <option value="count_gte">count_gte</option>
                            <option value="count_lte">count_lte</option>
                          </optgroup>
                        </select>
                        <CursorSafeInput
                          type="text"
                          value={cond.value ?? ''}
                          onValueChange={(v) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], value: v }
                            updateConfig('gate_conditions', updated)
                          }}
                          placeholder="value"
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        />
                        <select
                          value={cond.type || 'string'}
                          onChange={(e) => {
                            const updated = [...(currentConfig?.gate_conditions || [])]
                            updated[ci] = { ...updated[ci], type: e.target.value }
                            updateConfig('gate_conditions', updated)
                          }}
                          className="px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs
                                     focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                        >
                          <option value="number">number</option>
                          <option value="string">string</option>
                          <option value="boolean">boolean</option>
                          <option value="regex">regex</option>
                          <option value="count">count</option>
                        </select>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          const updated = (currentConfig?.gate_conditions || []).filter((_: any, i: number) => i !== ci)
                          updateConfig('gate_conditions', updated)
                        }}
                        className="p-1.5 text-slate-500 hover:text-red-400 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const updated = [...(currentConfig?.gate_conditions || []), { field: '', operator: '==', value: '', type: 'string' }]
                    updateConfig('gate_conditions', updated)
                  }}
                  className="mt-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-dashed border-slate-600
                             text-slate-400 hover:border-cyan-500/50 hover:text-cyan-400 transition-colors"
                >
                  + Add Condition
                </button>
              </div>
            </>
          )}

          {/* Agentic Mode Panel */}
          {currentConfig?.gate_mode === 'agentic' && (
            <>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Source Step</label>
                <CursorSafeInput
                  type="text"
                  value={currentConfig?.gate_source_step || ''}
                  onValueChange={(v) => updateConfig('gate_source_step', v)}
                  placeholder="e.g. inbox, step_1"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                />
                <p className="text-xs text-slate-500 mt-1">Step whose output the AI evaluates</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Gate Prompt</label>
                <TemplateTextarea
                  value={currentConfig?.gate_prompt || ''}
                  onValueChange={(v) => updateConfig('gate_prompt', v)}
                  rows={4}
                  placeholder="Describe when the gate should PASS... Use {{step_N.field}} to reference previous step outputs."
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                  allSteps={stepInfoList}
                  currentStepPosition={step.position}
                />
              </div>

              <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/5 border border-amber-500/20 rounded-lg">
                <svg className="w-4 h-4 text-amber-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
                </svg>
                <span className="text-xs text-amber-400">Uses AI tokens &mdash; will incur LLM cost</span>
              </div>
            </>
          )}

          {/* Common: On Fail Action */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">On Fail Action</label>
            <select
              value={currentConfig?.gate_on_fail || 'skip'}
              onChange={(e) => updateConfig('gate_on_fail', e.target.value)}
              className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                         focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            >
              <option value="skip">Skip remaining steps (silent)</option>
              <option value="notify">Send notification, then stop</option>
            </select>
          </div>

          {/* Notify sub-fields */}
          {currentConfig?.gate_on_fail === 'notify' && (
            <div className="space-y-3 pl-4 border-l-2 border-amber-500/30">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Channel</label>
                <select
                  value={currentConfig?.gate_fail_notification?.channel || 'whatsapp'}
                  onChange={(e) => updateConfig('gate_fail_notification', {
                    ...currentConfig?.gate_fail_notification,
                    channel: e.target.value
                  })}
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                >
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                  <option value="slack">Slack</option>
                  <option value="discord">Discord</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Recipient</label>
                <TemplateInput
                  value={currentConfig?.gate_fail_notification?.recipient || ''}
                  onValueChange={(v) => updateConfig('gate_fail_notification', {
                    ...currentConfig?.gate_fail_notification,
                    recipient: v
                  })}
                  placeholder="e.g. +5527999999999 or {{step_N.field}}"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                  allSteps={stepInfoList}
                  currentStepPosition={step.position}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Message Template</label>
                <TemplateTextarea
                  value={currentConfig?.gate_fail_notification?.message_template || ''}
                  onValueChange={(v) => updateConfig('gate_fail_notification', {
                    ...currentConfig?.gate_fail_notification,
                    message_template: v
                  })}
                  rows={3}
                  placeholder="Gate blocked: {{gate.reasoning}}"
                  className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                  allSteps={stepInfoList}
                  currentStepPosition={step.position}
                />
              </div>
            </div>
          )}

          {/* Tips */}
          <div className="p-3 bg-slate-800/50 rounded-lg border border-slate-700">
            <p className="text-xs text-slate-400">
              <span className="text-cyan-400 font-medium inline-flex items-center gap-1"><ShieldCheckIcon size={12} /> Gate Tips:</span>
              <br />{'•'} <strong>Programmatic</strong> mode is zero-cost {'—'} no AI tokens used
              <br />{'•'} <strong>Agentic</strong> mode uses LLM for complex decisions
              <br />{'•'} Reference gate output with {'{{'}step_N.gate_result{'}}'} in subsequent steps
            </p>
          </div>
        </>
      )}

      {/* Agent & Persona Selection */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Agent</label>
          <select
            value={currentStep.agent_id || ''}
            onChange={(e) => debouncedSave({ agent_id: e.target.value ? parseInt(e.target.value) : null })}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          >
            <option value="">Use default</option>
            {agents.map(agent => (
              <option key={agent.id} value={agent.id}>{agent.contact_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">Persona</label>
          <select
            value={currentStep.persona_id || ''}
            onChange={(e) => debouncedSave({ persona_id: e.target.value ? parseInt(e.target.value) : null })}
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
                       focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          >
            <option value="">Use default</option>
            {personas.map(persona => (
              <option key={persona.id} value={persona.id}>{persona.name}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

// ==================== EDIT FLOW MODAL ====================

function EditFlowModal({ flowId, agents, contacts, personas, customTools, customSkills, onClose, onSuccess }: {
  flowId: number
  agents: Agent[]
  contacts: Contact[]
  personas: Persona[]
  customTools: CustomTool[]
  customSkills?: any[]
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  // v0.7.0 Wave 3 — derive canWriteFlows locally. The variable existed only in
  // FlowsPage scope, so the existing references at lines 4690-4696 inside
  // this modal threw `ReferenceError: canWriteFlows is not defined` whenever
  // a user opened a flow for editing. Caught by Wave 3 QA. Self-contained
  // useAuth() avoids prop-drilling through every place EditFlowModal is rendered.
  const { hasPermission } = useAuth()
  const canWriteFlows = hasPermission('flows.write')
  const [flow, setFlow] = useState<FlowDefinition | null>(null)
  const [steps, setSteps] = useState<EditableStepData[]>([])
  const stepsRef = useRef<EditableStepData[]>([])
  const [loading, setLoading] = useState(true)
  // Flush callbacks registered by each EditableStepConfigForm to force-save pending edits
  const flushCallbacksRef = useRef<Map<number, () => void>>(new Map())
  const [saving, setSaving] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])

  // Keep stepsRef in sync for use inside handleSave after flush
  useEffect(() => { stepsRef.current = steps }, [steps])

  useEffect(() => {
    loadFlow()
  }, [flowId])

  async function loadFlow() {
    setLoading(true)
    try {
      const [flowData, stepsData] = await Promise.all([
        api.getFlow(flowId),
        api.getFlowSteps(flowId)
      ])
      setFlow(flowData)
      // Convert FlowNode[] to EditableStepData[]
      const editableSteps = stepsData
        .sort((a, b) => a.position - b.position)
        .map(flowNodeToEditable)
      setSteps(editableSteps)
    } catch (error) {
      console.error('Failed to load flow:', error)
      toast.error('Load Failed', 'Failed to load flow')
      onClose()
    } finally {
      setLoading(false)
    }
  }

  async function handleValidate() {
    try {
      const result = await api.validateFlow(flowId)
      if (result.valid) {
        setValidationErrors([])
        toast.success('Validation', 'Flow is valid!')
      } else {
        setValidationErrors(result.errors || ['Validation failed'])
      }
    } catch (error) {
      console.error('Failed to validate:', error)
      setValidationErrors(['Validation error'])
    }
  }

  async function handleSave() {
    if (!flow) return
    setSaving(true)
    try {
      // 1. Flush all pending form edits into the steps state synchronously.
      //    This ensures text field changes that are still in the 500ms debounce window
      //    are propagated to the steps array before we save.
      flushCallbacksRef.current.forEach(flush => flush())

      // 2. Wait one microtask for React to process the flushed state updates
      await new Promise(r => setTimeout(r, 0))

      // 3. Save flow-level data
      await api.patchFlow(flowId, {
        name: flow.name,
        description: flow.description || undefined,
        is_active: flow.is_active,
        execution_method: flow.execution_method as any,
        scheduled_at: flow.scheduled_at,
        recurrence_rule: flow.recurrence_rule as any,
        default_agent_id: flow.default_agent_id ?? 0,
        trigger_keywords: flow.trigger_keywords ?? [],  // BUG-336
      })

      // 4. Explicitly save all steps using the latest ref (updated after flush)
      const latestSteps = stepsRef.current
      await Promise.all(
        latestSteps.filter(s => s.id).map(s =>
          api.updateFlowStep(flowId, s.id!, editableToUpdatePayload(s))
        )
      )

      onSuccess()
    } catch (error) {
      console.error('Failed to save flow:', error)
      toast.error('Save Failed', 'Failed to save flow')
    } finally {
      setSaving(false)
    }
  }

  if (loading || !flow) {
    return (
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-slate-800 rounded-2xl p-8">
          <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto" />
          <p className="text-slate-400 mt-4">Loading flow...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-slate-700">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Edit Flow</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-sm text-slate-400">Flow #{flowId}</p>
              {flow && <TriggerOriginBadge flow={flow} />}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Validation Errors */}
          {validationErrors.length > 0 && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-red-400 mb-2">Validation Errors</h4>
              <ul className="list-disc list-inside text-sm text-red-300 space-y-1">
                {validationErrors.map((err, i) => <li key={i}>{err}</li>)}
              </ul>
            </div>
          )}

          {/* Flow Settings */}
          <div className="bg-slate-700/30 rounded-xl p-5 space-y-4">
            <h3 className="text-lg font-semibold text-white mb-4">Flow Settings</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Name</label>
                <input
                  type="text"
                  value={flow.name}
                  onChange={(e) => setFlow(prev => prev ? { ...prev, name: e.target.value } : null)}
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Description</label>
                <textarea
                  value={flow.description || ''}
                  onChange={(e) => setFlow(prev => prev ? { ...prev, description: e.target.value } : null)}
                  rows={2}
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Type</label>
                <div className="px-4 py-2.5 bg-slate-700/30 border border-slate-600 rounded-lg text-slate-400">
                  {FLOW_TYPES.find(t => t.value === flow.flow_type)?.label || flow.flow_type}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Status</label>
                <button
                  onClick={() => canWriteFlows && setFlow(prev => prev ? { ...prev, is_active: !prev.is_active } : null)}
                  disabled={!canWriteFlows}
                  title={canWriteFlows ? undefined : 'Requires flows.write permission'}
                  className={`px-4 py-2.5 rounded-lg font-medium transition-colors ${flow.is_active
                      ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                      : 'bg-slate-700/50 text-slate-400 border border-slate-600'
                    } ${!canWriteFlows ? 'opacity-60 cursor-not-allowed' : ''}`}
                >
                  {flow.is_active ? 'Enabled' : 'Disabled'}
                </button>
              </div>

              <div className="col-span-2">
                <label className="block text-sm font-medium text-slate-300 mb-2">Execution Method</label>
                <div className="grid grid-cols-3 gap-3">
                  {EXECUTION_METHODS.map(method => {
                    const MethodIcon = method.Icon
                    return (
                      <button
                        key={method.value}
                        onClick={() => setFlow(prev => prev ? { ...prev, execution_method: method.value } : null)}
                        className={`p-3 rounded-lg border text-center transition-all ${flow.execution_method === method.value
                            ? 'border-cyan-500 bg-cyan-500/10 text-white'
                            : 'border-slate-700 hover:border-slate-600 text-slate-300'
                          }`}
                      >
                        <div className="flex justify-center">
                          <MethodIcon size={24} />
                        </div>
                        <div className="text-sm mt-1">{method.label}</div>
                      </button>
                    )
                  })}
                </div>
              </div>

              {flow.execution_method === 'scheduled' && (
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Schedule Time</label>
                  <input
                    type="datetime-local"
                    value={flow.scheduled_at ? new Date(flow.scheduled_at).toISOString().slice(0, 16) : ''}
                    onChange={(e) => setFlow(prev => prev ? { ...prev, scheduled_at: new Date(e.target.value).toISOString() } : null)}
                    className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                               focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                  />
                </div>
              )}

              {flow.execution_method === 'recurring' && (
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Recurrence Settings</label>
                  <RecurrenceConfigPanel
                    value={flow.recurrence_rule as any}
                    onChange={(rule) => setFlow(prev => prev ? { ...prev, recurrence_rule: rule as any } : null)}
                  />
                </div>
              )}

              {/* BUG-336: Keyword trigger configuration in edit mode */}
              {flow.execution_method === 'keyword' && (
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-slate-300 mb-1.5">Trigger Keywords</label>
                  <p className="text-xs text-slate-500 mb-2">
                    One keyword or command per line. Matching messages in Playground or channels will trigger this flow instead of the AI (e.g. <code className="bg-slate-800 px-1 rounded">/testflow</code>).
                  </p>
                  <textarea
                    value={(flow.trigger_keywords || []).join('\n')}
                    onChange={(e) => setFlow(prev => prev ? {
                      ...prev,
                      trigger_keywords: e.target.value.split('\n').map(k => k.trim()).filter(Boolean)
                    } : null)}
                    rows={4}
                    placeholder="/testflow&#10;run report&#10;start workflow"
                    className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white font-mono text-sm
                               focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
                  />
                </div>
              )}

              <div className="col-span-2">
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Default Agent</label>
                <select
                  value={flow.default_agent_id || ''}
                  onChange={(e) => setFlow(prev => prev ? { ...prev, default_agent_id: e.target.value ? parseInt(e.target.value) : null } : null)}
                  className="w-full px-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white
                             focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
                >
                  <option value="">Select an agent...</option>
                  {agents.map(agent => (
                    <option key={agent.id} value={agent.id}>{agent.contact_name}</option>
                  ))}
                </select>
                <p className="text-xs text-slate-500 mt-1">Used for steps that don&apos;t have a specific agent assigned</p>
              </div>
            </div>
          </div>

          {/* Steps */}
          <div className="bg-slate-700/30 rounded-xl p-5">
            <h3 className="text-lg font-semibold text-white mb-4">Steps ({steps.length})</h3>
            <EditableStepBuilder
              flowId={flowId}
              steps={steps}
              agents={agents}
              contacts={contacts}
              personas={personas}
              customTools={customTools}
              customSkills={customSkills}
              onStepsChange={setSteps}
              flushCallbacksRef={flushCallbacksRef}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 flex items-center justify-between">
          <button
            onClick={handleValidate}
            className="px-4 py-2 text-yellow-400 hover:text-yellow-300 transition-colors"
          >
            Validate
          </button>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-6 py-2 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-medium rounded-lg
                         hover:from-cyan-400 hover:to-blue-500 transition-all disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ==================== VIEW RUN MODAL ====================

function ViewRunModal({ runId, onClose }: {
  runId: number
  onClose: () => void
}) {
  const [run, setRun] = useState<FlowRun | null>(null)
  const [nodeRuns, setNodeRuns] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const statusRef = useRef<string>('')

  const isActive = statusRef.current === 'pending' || statusRef.current === 'running'

  useEffect(() => {
    loadRun()
    return () => stopPolling()
  }, [runId])

  // Start/stop polling based on run status
  useEffect(() => {
    if (isActive && !pollingRef.current) {
      pollingRef.current = setInterval(pollRun, 2000)
    } else if (!isActive && pollingRef.current) {
      stopPolling()
    }
  }, [run?.status])

  function stopPolling() {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  async function loadRun() {
    setLoading(true)
    try {
      const [runData, nodeRunsData] = await Promise.all([
        api.getFlowRun(runId),
        api.getFlowNodeRuns(runId)
      ])
      setRun(runData)
      statusRef.current = runData.status
      setNodeRuns(nodeRunsData)
    } catch (error) {
      console.error('Failed to load run:', error)
    } finally {
      setLoading(false)
    }
  }

  async function pollRun() {
    try {
      const [runData, nodeRunsData] = await Promise.all([
        api.getFlowRun(runId),
        api.getFlowNodeRuns(runId)
      ])
      setRun(runData)
      statusRef.current = runData.status
      setNodeRuns(nodeRunsData)
    } catch (error) {
      console.error('Failed to poll run:', error)
    }
  }

  if (loading && !run) {
    return (
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-slate-800 rounded-2xl p-8 text-center">
          <div className="animate-spin h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto" />
          <p className="text-slate-400 mt-4">Loading run details...</p>
        </div>
      </div>
    )
  }

  const totalSteps = run?.total_steps || 0
  const completedSteps = (run?.completed_steps || 0) + (run?.failed_steps || 0)
  const progressPct = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0
  const runIsActive = run && ['pending', 'running'].includes(run.status)

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl max-w-3xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-slate-700">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {runIsActive && (
              <div className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500" />
              </div>
            )}
            <div>
              <h2 className="text-xl font-bold text-white">
                Run #{run?.id || '...'}
                {runIsActive && <span className="ml-2 text-sm font-normal text-cyan-400">Live</span>}
              </h2>
              <p className="text-sm text-slate-400">Flow #{run?.flow_definition_id}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress bar (visible while active) */}
        {runIsActive && totalSteps > 0 && (
          <div className="px-6 pt-4">
            <div className="flex items-center justify-between text-sm mb-2">
              <span className="text-slate-400">
                {run?.status === 'pending' ? 'Preparing...' : `Executing step ${completedSteps + 1} of ${totalSteps}`}
              </span>
              <span className="text-cyan-400 font-medium">{progressPct}%</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-teal-400 transition-all duration-500 ease-out"
                style={{ width: `${Math.max(progressPct, run?.status === 'pending' ? 0 : 3)}%` }}
              />
              {run?.status === 'running' && progressPct < 100 && (
                <div className="h-full w-full -mt-2 bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent animate-pulse" />
              )}
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Run Info */}
          {run && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-700/30 rounded-lg p-4">
                <div className="text-sm text-slate-400">Status</div>
                <StatusBadge status={run.status} />
              </div>
              <div className="bg-slate-700/30 rounded-lg p-4">
                <div className="text-sm text-slate-400">Started</div>
                <div className="text-white">{run.started_at ? formatDate(run.started_at) : '-'}</div>
              </div>
              <div className="bg-slate-700/30 rounded-lg p-4">
                <div className="text-sm text-slate-400">Completed</div>
                <div className="text-white">{run.completed_at ? formatDate(run.completed_at) : '-'}</div>
              </div>
              <div className="bg-slate-700/30 rounded-lg p-4">
                <div className="text-sm text-slate-400">Steps</div>
                <div className="text-white">{completedSteps}/{totalSteps}</div>
              </div>
            </div>
          )}

          {/* Error */}
          {run?.error_text && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
              <h4 className="text-sm font-semibold text-red-400 mb-2">Error</h4>
              <p className="text-sm text-red-300">{run.error_text}</p>
            </div>
          )}

          {/* Step Runs */}
          <div>
            <h3 className="text-lg font-semibold text-white mb-4">Step Execution</h3>
            {nodeRuns.length === 0 && !runIsActive ? (
              <p className="text-slate-400">No step execution data available</p>
            ) : nodeRuns.length === 0 && runIsActive ? (
              <div className="flex items-center gap-3 text-slate-400 py-4">
                <div className="w-4 h-4 border-2 border-slate-500 border-t-transparent rounded-full animate-spin" />
                <span>{run?.status === 'pending' ? 'Preparing execution...' : 'Waiting for first step...'}</span>
              </div>
            ) : (
              <div className="space-y-3">
                {nodeRuns.map((nodeRun, index) => (
                  <div
                    key={nodeRun.id}
                    className={`bg-slate-700/30 rounded-lg p-4 border transition-all duration-300 ${
                      nodeRun.status === 'running'
                        ? 'border-cyan-500/50 shadow-lg shadow-cyan-500/5'
                        : nodeRun.status === 'completed'
                          ? 'border-green-500/30'
                          : nodeRun.status === 'failed'
                            ? 'border-red-500/30'
                            : 'border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {nodeRun.status === 'running' && (
                          <div className="w-3 h-3 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin" />
                        )}
                        <div className="font-medium text-white">Step {index + 1}</div>
                      </div>
                      <StatusBadge status={nodeRun.status} />
                    </div>
                    {nodeRun.execution_time_ms != null && (
                      <div className="text-sm text-slate-400">
                        Execution time: {nodeRun.execution_time_ms}ms
                      </div>
                    )}
                    {nodeRun.error_text && (
                      <div className="mt-2 text-sm text-red-400">{nodeRun.error_text}</div>
                    )}
                  </div>
                ))}
                {/* Pending steps placeholder */}
                {runIsActive && nodeRuns.length < totalSteps && (
                  <div className="flex items-center gap-2 text-slate-500 text-sm px-4 py-2">
                    <div className="w-3 h-3 border-2 border-slate-600 border-t-transparent rounded-full animate-spin" />
                    {totalSteps - nodeRuns.length} step{totalSteps - nodeRuns.length > 1 ? 's' : ''} remaining...
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg hover:bg-slate-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

// ==================== UTILITIES ====================

function formatDate(dateString: string) {
  return parseUTCTimestamp(dateString).toLocaleString('pt-BR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatRelativeDate(dateString: string) {
  return formatRelativeUtil(dateString)
}
