'use client'

/**
 * ManagedContainerPanel — shared lifecycle controls for auto-provisioned
 * container-based services (Ollama, Kokoro, SearXNG).
 *
 * Extracted from the inline `renderManagedContainerControls()` helper that
 * previously lived in `hub/page.tsx`. Consolidating this into a real component
 * means every managed local service exposes the exact same set of affordances
 * (enable/disable toggle, restart, logs, delete, optional test) so the Hub
 * feels coherent regardless of which service the user is looking at.
 */

import ToggleSwitch from '@/components/ui/ToggleSwitch'

export interface ManagedContainerPanelProps {
  /** Normalized container status string. 'running' | 'stopped' | 'creating' | 'provisioning' | 'error' | 'none' */
  status: string
  /** True while any action is in-flight; disables all controls. */
  isBusy: boolean
  /** Toggle from running ↔ stopped. Start when stopped, stop when running. */
  onToggle: () => void
  /** Restart the container. Hidden when handler is absent. */
  onRestart?: () => void
  /** Open/close the logs drawer. Hidden when handler is absent. */
  onLogs?: () => void
  /** Current logs-open state — controls the Logs/Hide Logs label swap. */
  logsOpen?: boolean
  /** Delete/deprovision the container. Hidden when handler is absent. */
  onDelete?: () => void
  /** Test connection (non-container services also render this). Hidden when absent. */
  onTest?: () => void
  /** Optional custom label for the Test button (default 'Test'). */
  testLabel?: string
}

/**
 * Render a uniform control strip for a managed container.
 * The Enable/Disable toggle is the single source of truth for lifecycle.
 */
export default function ManagedContainerPanel({
  status,
  isBusy,
  onToggle,
  onRestart,
  onLogs,
  logsOpen,
  onDelete,
  onTest,
  testLabel = 'Test',
}: ManagedContainerPanelProps) {
  const raw = (status || 'none').toLowerCase()
  // Docker reports 'exited' for a cleanly-stopped container that still exists;
  // downstream logic only distinguishes 'running' vs 'stopped', so collapse both.
  const normalized = raw === 'exited' ? 'stopped' : raw
  const isRunning = normalized === 'running'
  const isProvisioning = normalized === 'creating' || normalized === 'provisioning'
  const canRestart = normalized === 'running' || normalized === 'stopped'

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5">
        <ToggleSwitch
          checked={isRunning}
          onChange={onToggle}
          disabled={isBusy || isProvisioning}
          title={isRunning ? 'Stop container' : 'Start container'}
          activeColor="bg-tsushin-success"
        />
        <span className="text-[11px] text-tsushin-slate">
          {isProvisioning ? 'Provisioning' : isRunning ? 'Enabled' : 'Disabled'}
        </span>
      </div>
      {canRestart && onRestart && (
        <button
          onClick={onRestart}
          disabled={isBusy}
          className="text-[11px] bg-white/5 border border-white/10 text-tsushin-slate hover:bg-white/10 rounded px-2 py-1 disabled:opacity-50"
        >
          Restart
        </button>
      )}
      {isRunning && onLogs && (
        <button
          onClick={onLogs}
          className="text-[11px] bg-white/5 border border-white/10 text-tsushin-slate hover:bg-white/10 rounded px-2 py-1"
        >
          {logsOpen ? 'Hide Logs' : 'Logs'}
        </button>
      )}
      {isRunning && onTest && (
        <button
          onClick={onTest}
          disabled={isBusy}
          className="text-[11px] bg-white/5 border border-white/10 text-tsushin-slate hover:bg-white/10 rounded px-2 py-1 disabled:opacity-50"
        >
          {testLabel}
        </button>
      )}
      {onDelete && (
        <button
          onClick={onDelete}
          disabled={isBusy}
          className="ml-auto text-[11px] bg-tsushin-vermilion/10 border border-tsushin-vermilion/20 text-tsushin-vermilion hover:bg-tsushin-vermilion/20 rounded px-2 py-1 disabled:opacity-50"
        >
          Delete
        </button>
      )}
    </div>
  )
}
