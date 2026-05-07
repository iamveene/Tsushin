'use client'

/**
 * Studio → Continuous Agents
 *
 * Studio entry point for creating + managing Continuous Agents (the
 * always-on wrapper that wakes a single agent on a trigger event with
 * daily budget caps).
 *
 * Renders the same component as `/continuous-agents` (which now lives
 * under Watcher → Agents → Continuous Agents for run-history /
 * observability). The page intentionally re-mounts the same component
 * here so creation lives next to Agents and Teams in Studio (where
 * configuration belongs) while observability stays in Watcher (run
 * history, wake events).
 *
 * If you find yourself wanting to fork behaviour for the Studio mount,
 * push the difference into the underlying component as a prop instead
 * — the dual entry point is intentional and the two pages should stay
 * in lockstep.
 */

import StudioTabs from '@/components/studio/StudioTabs'
import ContinuousAgentsPage from '@/app/continuous-agents/page'

export default function StudioContinuousAgentsPage() {
  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8">
        <h1 className="text-3xl font-display font-bold text-white mb-2">Agent Studio</h1>
        <p className="text-tsushin-slate">Configure AI agents with different personalities and capabilities</p>
      </div>
      <div className="space-y-6">
        <StudioTabs />
        <ContinuousAgentsPage />
      </div>
    </div>
  )
}
