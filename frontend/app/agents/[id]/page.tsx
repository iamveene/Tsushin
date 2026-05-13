'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { api, Agent } from '@/lib/client'
import AgentMemoryManager from '@/components/AgentMemoryManager'
import AgentSkillsManager from '@/components/AgentSkillsManager'
import AgentCustomSkillsManager from '@/components/AgentCustomSkillsManager'
import AgentKnowledgeManager from '@/components/AgentKnowledgeManager'
// AgentSandboxedToolsManager is now embedded in the Skills > Sandboxed Tools config modal
import AgentConfigurationManager from '@/components/AgentConfigurationManager'
import AgentChannelsManager from '@/components/AgentChannelsManager'
import AgentAdvancedManager from '@/components/AgentAdvancedManager'
import SharedKnowledgeViewer from '@/components/SharedKnowledgeViewer'
import {
  SettingsIcon, RadioIcon, BrainIcon, SparklesIcon, BookOpenIcon,
  LinkIcon, TheaterIcon, BotIcon, LightningIcon, KeyIcon, StarIcon, WrenchIcon, UsersIcon
} from '@/components/ui/icons'
import DetailShellHeader from '@/components/ui/DetailShell'
import TabStrip from '@/components/ui/TabStrip'

type Tab = 'configuration' | 'channels' | 'memory' | 'skills' | 'custom-skills' | 'knowledge' | 'shared-knowledge' | 'advanced'

const VALID_TABS: Tab[] = ['configuration', 'channels', 'memory', 'skills', 'custom-skills', 'knowledge', 'shared-knowledge', 'advanced']

export default function AgentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const rawId = params.id as string
  const agentId = parseInt(rawId)
  // BUG-508: The dynamic [id] route also catches URLs like /agents/communication
  // where there is no matching sibling page. parseInt yields NaN, which used to
  // hit /api/agents/NaN, surface an error alert, and redirect. Bail early and
  // redirect cleanly for any non-numeric segment.
  const hasValidId = Number.isFinite(agentId)

  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)
  // BUG-011 Fix: Read initial tab from query params
  const initialTab = (searchParams.get('tab') as Tab) || 'configuration'
  const [activeTab, setActiveTab] = useState<Tab>(VALID_TABS.includes(initialTab) ? initialTab : 'configuration')
  const [skillsCount, setSkillsCount] = useState<number>(0)

  useEffect(() => {
    if (!hasValidId) {
      router.replace('/agents')
      return
    }
    loadAgent()
  }, [agentId, hasValidId])

  // Listen for global refresh events
  useEffect(() => {
    if (!hasValidId) return
    const handleRefresh = () => {
      loadAgent()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [agentId, hasValidId])

  const loadAgent = async () => {
    if (!hasValidId) return
    setLoading(true)
    try {
      const agentData = await api.getAgent(agentId)
      setAgent(agentData)

      // Load skills count
      try {
        const skills = await api.getAgentSkills(agentId)
        setSkillsCount(skills.filter(s => s.is_enabled).length)
      } catch (err) {
        console.error('Failed to load skills:', err)
        setSkillsCount(0)
      }
    } catch (err) {
      console.error('Failed to load agent:', err)
      alert('Failed to load agent details')
      router.push('/agents')
    } finally {
      setLoading(false)
    }
  }

  if (!hasValidId) {
    // Redirect effect is already scheduled; render nothing to avoid a doomed fetch.
    return null
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-tsushin-ink flex items-center justify-center">
        <div className="text-lg text-tsushin-slate">Loading agent...</div>
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="min-h-screen bg-tsushin-ink flex items-center justify-center">
        <div className="text-center">
          <p className="text-lg text-tsushin-slate mb-4">Agent not found</p>
          <button
            onClick={() => router.push('/agents')}
            className="btn-primary px-4 py-2 rounded-lg"
          >
            Back to Agents
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-tsushin-ink animate-fade-in">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <DetailShellHeader
          breadcrumb={[
            { label: 'Studio', href: '/agents' },
            { label: 'Agents', href: '/agents' },
            { label: agent.contact_name },
          ]}
          title={agent.contact_name}
          badges={
            <>
              {agent.is_default && (
                <span className="px-2 py-1 text-xs font-medium bg-tsushin-warning/20 text-yellow-200 rounded-full inline-flex items-center gap-1">
                  <StarIcon size={12} /> Default
                </span>
              )}
              {agent.is_active ? (
                <span className="px-2 py-1 text-xs font-medium bg-green-800/30 text-green-200 rounded-full">
                  ✓ Active
                </span>
              ) : (
                <span className="px-2 py-1 text-xs font-medium bg-tsushin-surface text-tsushin-slate rounded-full">
                  ○ Inactive
                </span>
              )}
              {agent.is_team_member && (
                <span className="badge badge-team flex items-center gap-1">
                  <UsersIcon size={12} /> Team
                </span>
              )}
            </>
          }
          meta={
            <>
              <span className="inline-flex items-center gap-1"><TheaterIcon size={14} /> Tone: {agent.tone_preset_name || 'Custom'}</span>
              <span className="inline-flex items-center gap-1"><BotIcon size={14} /> Model: {agent.model_name}</span>
              <span className="inline-flex items-center gap-1"><LightningIcon size={14} /> Skills: {skillsCount}</span>
              <span className="inline-flex items-center gap-1"><KeyIcon size={14} /> Keywords: {agent.keywords.length || 0}</span>
            </>
          }
          actions={
            <button
              onClick={() => setActiveTab('configuration')}
              className="btn-primary inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm"
            >
              <SettingsIcon size={16} /> Edit Configuration
            </button>
          }
        />

        {agent.is_team_member && (
          <div className="mb-6 rounded-xl border border-tsushin-indigo/25 bg-tsushin-indigo/10 px-4 py-3">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-3">
                <UsersIcon size={18} className="mt-0.5 flex-shrink-0 text-tsushin-indigo-glow" />
                <div>
                  <h2 className="text-sm font-semibold text-white">Team member agent</h2>
                  <p className="mt-1 text-sm text-tsushin-slate">
                    Direct conversations stay separate from team executions, but settings changes here may affect team behavior.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => router.push(agent.current_team_id ? `/studio/teams/${agent.current_team_id}` : '/studio/teams')}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-indigo/30 bg-tsushin-indigo/10 px-4 py-2 text-sm font-medium text-tsushin-indigo-glow transition-colors hover:bg-tsushin-indigo/20"
              >
                Open Teams
              </button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="bg-tsushin-surface border border-tsushin-border rounded-xl mb-6 overflow-hidden">
          <TabStrip
            className="border-b border-tsushin-border"
            ariaLabel="Agent configuration sections"
          >
            {([
              ['configuration', SettingsIcon, 'Configuration'],
              ['channels', RadioIcon, 'Channels'],
              ['memory', BrainIcon, 'Memory Management'],
              ['skills', SparklesIcon, 'Skills'],
              ['custom-skills', WrenchIcon, 'Custom Skills'],
              ['knowledge', BookOpenIcon, 'Knowledge Base'],
              ['shared-knowledge', LinkIcon, 'Shared Knowledge'],
              ['advanced', SettingsIcon, 'Advanced'],
            ] as const).map(([key, Icon, label]) => (
              <button
                key={key}
                onClick={() => setActiveTab(key as Tab)}
                className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 whitespace-nowrap flex-shrink-0 ${
                  activeTab === key
                    ? 'border-teal-500 text-teal-400'
                    : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
              >
                <Icon size={16} /> {label}
              </button>
            ))}
          </TabStrip>
        </div>

        {/* Tab Content */}
        <div className="bg-tsushin-surface border border-tsushin-border rounded-xl p-6">
          {activeTab === 'configuration' && (
            <AgentConfigurationManager agentId={agentId} />
          )}

          {activeTab === 'channels' && (
            <AgentChannelsManager agentId={agentId} />
          )}

          {activeTab === 'memory' && (
            <AgentMemoryManager agentId={agentId} agentName={agent.contact_name} />
          )}

          {activeTab === 'skills' && (
            <AgentSkillsManager agentId={agentId} />
          )}

          {activeTab === 'custom-skills' && (
            <AgentCustomSkillsManager agentId={agentId} />
          )}

          {activeTab === 'knowledge' && (
            <AgentKnowledgeManager agentId={agentId} />
          )}

          {activeTab === 'shared-knowledge' && (
            <SharedKnowledgeViewer agentId={agentId} />
          )}

          {activeTab === 'advanced' && (
            <AgentAdvancedManager agentId={agentId} />
          )}

        </div>
      </div>
    </div>
  )
}
