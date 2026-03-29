'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { api, Agent } from '@/lib/client'
import AgentMemoryManager from '@/components/AgentMemoryManager'
import AgentSkillsManager from '@/components/AgentSkillsManager'
import AgentKnowledgeManager from '@/components/AgentKnowledgeManager'
// AgentSandboxedToolsManager is now embedded in the Skills > Sandboxed Tools config modal
import AgentConfigurationManager from '@/components/AgentConfigurationManager'
import AgentChannelsManager from '@/components/AgentChannelsManager'
import SharedKnowledgeViewer from '@/components/SharedKnowledgeViewer'
import {
  SettingsIcon, RadioIcon, BrainIcon, SparklesIcon, BookOpenIcon,
  LinkIcon, TheaterIcon, BotIcon, LightningIcon, KeyIcon, StarIcon, MicrophoneIcon
} from '@/components/ui/icons'

type Tab = 'configuration' | 'channels' | 'memory' | 'skills' | 'knowledge' | 'shared-knowledge'

const VALID_TABS: Tab[] = ['configuration', 'channels', 'memory', 'skills', 'knowledge', 'shared-knowledge']

export default function AgentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const agentId = parseInt(params.id as string)

  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)
  // BUG-011 Fix: Read initial tab from query params
  const initialTab = (searchParams.get('tab') as Tab) || 'configuration'
  const [activeTab, setActiveTab] = useState<Tab>(VALID_TABS.includes(initialTab) ? initialTab : 'configuration')
  const [skillsCount, setSkillsCount] = useState<number>(0)

  useEffect(() => {
    loadAgent()
  }, [agentId])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      loadAgent()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [agentId])

  const loadAgent = async () => {
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
    <div className="min-h-screen bg-tsushin-ink">
      {/* Header */}
      <div className="bg-tsushin-surface/80 backdrop-blur-md border-b border-tsushin-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-4 mb-4">
            <button
              onClick={() => router.push('/agents')}
              className="text-tsushin-slate hover:text-white"
            >
              ← Back
            </button>
            <div className="h-6 w-px bg-tsushin-border"></div>
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-white">{agent.contact_name}</h1>
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
              </div>
              <div className="mt-1 flex flex-wrap gap-4 text-sm text-tsushin-slate">
                <span className="inline-flex items-center gap-1"><TheaterIcon size={14} /> Tone: {agent.tone_preset_name || 'Custom'}</span>
                <span className="inline-flex items-center gap-1"><BotIcon size={14} /> Model: {agent.model_name}</span>
                <span className="inline-flex items-center gap-1"><LightningIcon size={14} /> Skills: {skillsCount}</span>
                <span className="inline-flex items-center gap-1"><KeyIcon size={14} /> Keywords: {agent.keywords.length || 0}</span>
              </div>
            </div>
            <button
              onClick={() => setActiveTab('configuration')}
              className="btn-primary px-4 py-2 rounded-lg"
            >
              <SettingsIcon size={16} /> Edit Configuration
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Tabs */}
        <div className="bg-tsushin-surface border border-tsushin-border rounded-xl mb-6">
          <nav className="flex border-b border-tsushin-border">
            <button
              onClick={() => setActiveTab('configuration')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'configuration'
                  ? 'border-teal-500 text-teal-400'
                  : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
            >
              <SettingsIcon size={16} /> Configuration
            </button>
            <button
              onClick={() => setActiveTab('channels')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'channels'
                  ? 'border-teal-500 text-teal-400'
                  : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
            >
              <RadioIcon size={16} /> Channels
            </button>
            <button
              onClick={() => setActiveTab('memory')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'memory'
                  ? 'border-teal-500 text-teal-400'
                  : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
            >
              <BrainIcon size={16} /> Memory Management
            </button>
            <button
              onClick={() => setActiveTab('skills')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'skills'
                  ? 'border-teal-500 text-teal-400'
                  : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
            >
              <SparklesIcon size={16} /> Skills
            </button>
            <button
              onClick={() => setActiveTab('knowledge')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'knowledge'
                  ? 'border-teal-500 text-teal-400'
                  : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
            >
              <BookOpenIcon size={16} /> Knowledge Base
            </button>
            <button
              onClick={() => setActiveTab('shared-knowledge')}
              className={`px-6 py-4 font-medium text-sm border-b-2 transition-colors inline-flex items-center gap-1.5 ${activeTab === 'shared-knowledge'
                  ? 'border-teal-500 text-teal-400'
                  : 'border-transparent text-tsushin-slate hover:text-white hover:border-tsushin-muted'
                }`}
            >
              <LinkIcon size={16} /> Shared Knowledge
            </button>
          </nav>
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

          {activeTab === 'knowledge' && (
            <AgentKnowledgeManager agentId={agentId} />
          )}

          {activeTab === 'shared-knowledge' && (
            <SharedKnowledgeViewer agentId={agentId} />
          )}

        </div>
      </div>
    </div>
  )
}
