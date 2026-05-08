'use client'

/**
 * Studio → Continuous Agents
 *
 * Studio entry point for creating + managing Continuous Agents (the
 * always-on wrapper that wakes a single agent on a trigger event with
 * daily budget caps).
 *
 * Renders the canonical Continuous Agents component under Studio so
 * creation lives next to Agents and Teams, while Watcher keeps the
 * embedded run-history view under Watcher → Agents.
 *
 * Header parity with /agents — the centralized Create SplitButton
 * (chooser modal as the primary click + power-user direct routes on
 * the chevron) is the canonical entry point for creating any of the
 * three kinds. The embedded ContinuousAgentsPage hides its own
 * page-level "+ New" button when it detects this Studio mount, so
 * there is exactly ONE create surface visible.
 *
 * If you find yourself wanting to fork behaviour for the Studio mount,
 * push the difference into the underlying component as a prop instead.
 */

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import StudioTabs from '@/components/studio/StudioTabs'
import SplitButton from '@/components/ui/SplitButton'
import CreateChooserModal, { type ChosenKind } from '@/components/studio/CreateChooserModal'
import ContinuousAgentsPage from '@/app/continuous-agents/page'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { BotIcon, LightningIcon, PlusIcon, UsersIcon } from '@/components/ui/icons'

export default function StudioContinuousAgentsPage() {
  const router = useRouter()
  const { hasPermission } = useAuth()
  const canWriteAgents = hasPermission('agents.write')
  const agentWizard = useAgentWizard()

  const [showKindChooser, setShowKindChooser] = useState(false)

  const openAgentWizard = () => {
    if (!canWriteAgents) return
    const mode = agentWizard.getMode()
    if (mode === 'advanced') {
      router.push('/agents?new=1')
    } else {
      agentWizard.openWizard()
    }
  }
  const openContinuousAgentUI = () => router.push('/studio/continuous-agents?new=1')
  const openTeamsUI = () => router.push('/studio/teams?new=1')

  const handleKindChosen = (kind: ChosenKind) => {
    if (kind === 'agent') openAgentWizard()
    if (kind === 'continuous-agent') openContinuousAgentUI()
    if (kind === 'team') openTeamsUI()
  }

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-display font-bold text-white mb-2">Continuous Agents</h1>
          <p className="text-tsushin-slate">Always-on wrappers around Studio agents that wake on trigger events with daily budget caps.</p>
        </div>
        {canWriteAgents && (
          <SplitButton
            primaryLabel="Create"
            primaryIcon={<PlusIcon size={16} />}
            onPrimaryClick={() => setShowKindChooser(true)}
            options={[
              {
                id: 'compare',
                label: 'Compare options…',
                description: 'Side-by-side: Agent / Continuous Agent / Team.',
                icon: <PlusIcon size={16} />,
                onSelect: () => setShowKindChooser(true),
              },
              {
                id: 'agent',
                label: 'Agent (skip chooser)',
                description: 'Open the guided agent wizard directly.',
                icon: <BotIcon size={16} />,
                onSelect: openAgentWizard,
              },
              {
                id: 'continuous-agent',
                label: 'Continuous Agent (skip chooser)',
                description: 'Wrap an agent so it wakes on inbound events.',
                icon: <LightningIcon size={16} />,
                onSelect: openContinuousAgentUI,
              },
              {
                id: 'team',
                label: 'Team (skip chooser)',
                description: 'Multi-agent coordination (LINE/MESH).',
                icon: <UsersIcon size={16} />,
                onSelect: openTeamsUI,
              },
            ]}
          />
        )}
      </div>

      <CreateChooserModal
        open={showKindChooser}
        onClose={() => setShowKindChooser(false)}
        onSelect={handleKindChosen}
      />

      <div className="space-y-6">
        <StudioTabs />
        <ContinuousAgentsPage />
      </div>
    </div>
  )
}
