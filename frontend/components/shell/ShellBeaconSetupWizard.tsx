'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { api, authenticatedFetch, Agent } from '@/lib/client'
import BeaconInstallInstructions from './BeaconInstallInstructions'

interface Props {
  isOpen: boolean
  onClose: () => void
  onComplete?: () => void
}

type Step = 1 | 2 | 3 | 4 | 5 | 6

interface BeaconConfig {
  name: string
  display_name: string
  mode: 'beacon' | 'interactive'
  poll_interval: number
  retention_days: number
  yolo_mode: boolean
  allowed_commands: string[]
  allowed_paths: string[]
}

interface AssignmentResult {
  agentId: number
  agentName: string
  status: 'pending' | 'ok' | 'error'
  message?: string
}

const DEFAULT_CONFIG: BeaconConfig = {
  name: '',
  display_name: '',
  mode: 'beacon',
  poll_interval: 5,
  retention_days: 30,
  yolo_mode: false,
  allowed_commands: [],
  allowed_paths: [],
}

const POLL_INTERVALS = [3, 5, 10, 30, 60]
const RETENTION_OPTIONS = [7, 14, 30, 90]

export default function ShellBeaconSetupWizard({ isOpen, onClose, onComplete }: Props) {
  const [step, setStep] = useState<Step>(1)
  const [config, setConfig] = useState<BeaconConfig>(DEFAULT_CONFIG)

  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())

  const [createdBeacon, setCreatedBeacon] = useState<{ id: number; api_key: string; name: string } | null>(null)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [assignmentResults, setAssignmentResults] = useState<AssignmentResult[]>([])

  const [cmdDraft, setCmdDraft] = useState('')
  const [pathDraft, setPathDraft] = useState('')

  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setConfig(DEFAULT_CONFIG)
    setAgents([])
    setSelectedAgentIds(new Set())
    setCreatedBeacon(null)
    setCreating(false)
    setError(null)
    setAssignmentResults([])
    setCmdDraft('')
    setPathDraft('')
  }, [isOpen])

  useEffect(() => {
    if (step !== 3 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true).then(setAgents).finally(() => setAgentsLoading(false))
  }, [step, agents.length])

  const handleClose = () => onClose()

  const createBeaconAndAssign = async () => {
    setCreating(true)
    setError(null)
    try {
      const res = await authenticatedFetch('/api/shell/integrations', {
        method: 'POST',
        body: JSON.stringify({
          name: config.name.trim(),
          display_name: config.display_name.trim() || undefined,
          mode: config.mode,
          poll_interval: config.poll_interval,
          retention_days: config.retention_days,
          yolo_mode: config.yolo_mode,
          allowed_commands: config.allowed_commands,
          allowed_paths: config.allowed_paths,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setCreatedBeacon({ id: data.id, api_key: data.api_key, name: data.name })

      const selectedAgents = agents.filter((a) => selectedAgentIds.has(a.id))
      const results: AssignmentResult[] = selectedAgents.map((a) => ({
        agentId: a.id,
        agentName: a.contact_name,
        status: 'pending',
      }))
      setAssignmentResults(results)

      for (let i = 0; i < selectedAgents.length; i += 1) {
        const agent = selectedAgents[i]
        try {
          await api.updateAgentSkill(agent.id, 'shell', {
            is_enabled: true,
            config: { execution_mode: 'hybrid' },
          })
          setAssignmentResults((prev) =>
            prev.map((r, idx) => (idx === i ? { ...r, status: 'ok' } : r)),
          )
        } catch (err: any) {
          setAssignmentResults((prev) =>
            prev.map((r, idx) =>
              idx === i ? { ...r, status: 'error', message: err?.message || 'Failed' } : r,
            ),
          )
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to create beacon')
    } finally {
      setCreating(false)
    }
  }

  useEffect(() => {
    if (step === 5 && !createdBeacon && !creating && !error) {
      createBeaconAndAssign()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  if (!isOpen) return null

  const totalSteps = 6
  const stepIndicator = (
    <div className="flex items-center justify-center gap-1.5 mb-5">
      {[1, 2, 3, 4, 5, 6].map((n) => (
        <div key={n} className="flex items-center gap-1.5">
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
              n === step ? 'bg-teal-500 text-white' :
              n < step ? 'bg-teal-500/20 text-teal-400' :
              'bg-white/5 text-gray-500'
            }`}
          >
            {n < step ? '✓' : n}
          </div>
          {n < totalSteps && (
            <div className={`w-5 h-0.5 ${n < step ? 'bg-teal-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  // ==========================================================================
  // STEP 1 — Welcome
  // ==========================================================================
  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
        <button onClick={() => setStep(2)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Get started →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Set up a Shell Beacon" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">Run commands on a remote host</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              A beacon is a small daemon that polls Tsushin for commands and runs them on the
              target host. This wizard creates the beacon, shows you the one-time API key and
              install snippet, and turns on the <span className="text-teal-400">Shell</span> skill
              on the agents you pick.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Safety</div>
              <div className="text-white">Allowlist + approval queue + Sentinel</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Transport</div>
              <div className="text-white">Outbound poll (no inbound port)</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Runtime</div>
              <div className="text-white">Python 3.10+ · Linux / macOS / Windows</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Auth</div>
              <div className="text-white">Per-beacon API key (shown once)</div>
            </div>
          </div>
          <div className="text-xs text-gray-400 bg-teal-500/5 border border-teal-500/20 rounded-lg p-3">
            <span className="text-teal-400 font-medium">Tip:</span> use the default allowlists +
            approval workflow unless you own the target host. YOLO mode skips approvals — keep it
            off for production systems.
          </div>
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 2 — Configure
  // ==========================================================================
  if (step === 2) {
    const canProceed = config.name.trim().length > 0
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button
          onClick={() => setStep(3)}
          disabled={!canProceed}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40"
        >
          Next: Link agents →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Configure Beacon" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Beacon name *</label>
            <input
              type="text"
              value={config.name}
              onChange={(e) => setConfig({ ...config, name: e.target.value })}
              placeholder="production-server"
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Display name (optional)</label>
            <input
              type="text"
              value={config.display_name}
              onChange={(e) => setConfig({ ...config, display_name: e.target.value })}
              placeholder="Production web server"
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Mode</label>
            <div className="grid grid-cols-2 gap-3">
              {(['beacon', 'interactive'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setConfig({ ...config, mode: m })}
                  className={`p-3 text-left rounded-lg border ${
                    config.mode === m
                      ? 'border-teal-500/60 bg-teal-500/10'
                      : 'border-white/10 hover:bg-white/[0.03]'
                  }`}
                >
                  <div className="text-sm text-white capitalize">{m}</div>
                  <div className="text-xs text-gray-500">
                    {m === 'beacon' ? 'Polls for commands (recommended)' : 'Keeps a live shell open'}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">Poll interval (s)</label>
              <select
                value={config.poll_interval}
                onChange={(e) => setConfig({ ...config, poll_interval: parseInt(e.target.value, 10) })}
                className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              >
                {POLL_INTERVALS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">Retention (days)</label>
              <select
                value={config.retention_days}
                onChange={(e) => setConfig({ ...config, retention_days: parseInt(e.target.value, 10) })}
                className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              >
                {RETENTION_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Allowed commands</label>
            <div className="flex gap-2 flex-wrap mb-2">
              {config.allowed_commands.map((c) => (
                <span key={c} className="text-xs px-2 py-1 rounded bg-teal-500/15 text-teal-300 flex items-center gap-1">
                  {c}
                  <button
                    onClick={() => setConfig({ ...config, allowed_commands: config.allowed_commands.filter((x) => x !== c) })}
                    className="text-teal-200 hover:text-white"
                  >×</button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={cmdDraft}
                onChange={(e) => setCmdDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && cmdDraft.trim()) {
                    setConfig({ ...config, allowed_commands: [...config.allowed_commands, cmdDraft.trim()] })
                    setCmdDraft('')
                  }
                }}
                placeholder="uptime"
                className="flex-1 px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              />
              <button
                onClick={() => {
                  if (cmdDraft.trim()) {
                    setConfig({ ...config, allowed_commands: [...config.allowed_commands, cmdDraft.trim()] })
                    setCmdDraft('')
                  }
                }}
                className="px-3 py-2 text-sm bg-white/5 hover:bg-white/10 text-white rounded-lg"
              >
                Add
              </button>
            </div>
            <p className="text-[11px] text-gray-500 mt-1">
              Leave empty to allow all commands (still subject to Sentinel patterns + approval).
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Allowed paths</label>
            <div className="flex gap-2 flex-wrap mb-2">
              {config.allowed_paths.map((p) => (
                <span key={p} className="text-xs px-2 py-1 rounded bg-teal-500/15 text-teal-300 flex items-center gap-1 font-mono">
                  {p}
                  <button
                    onClick={() => setConfig({ ...config, allowed_paths: config.allowed_paths.filter((x) => x !== p) })}
                    className="text-teal-200 hover:text-white"
                  >×</button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={pathDraft}
                onChange={(e) => setPathDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && pathDraft.trim()) {
                    setConfig({ ...config, allowed_paths: [...config.allowed_paths, pathDraft.trim()] })
                    setPathDraft('')
                  }
                }}
                placeholder="/var/log"
                className="flex-1 px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm font-mono focus:border-teal-500/50 focus:outline-none"
              />
              <button
                onClick={() => {
                  if (pathDraft.trim()) {
                    setConfig({ ...config, allowed_paths: [...config.allowed_paths, pathDraft.trim()] })
                    setPathDraft('')
                  }
                }}
                className="px-3 py-2 text-sm bg-white/5 hover:bg-white/10 text-white rounded-lg"
              >
                Add
              </button>
            </div>
          </div>

          <div className="pt-3 border-t border-white/5">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.yolo_mode}
                onChange={(e) => setConfig({ ...config, yolo_mode: e.target.checked })}
                className="rounded bg-[#0a0a0f] border-white/20 text-red-500 focus:ring-red-500"
              />
              <span className="text-sm text-white">YOLO mode — skip approvals</span>
            </label>
            {config.yolo_mode && (
              <p className="text-xs text-red-400 mt-1.5 ml-6">
                ⚠ Commands execute immediately without human approval. Do not enable on production hosts.
              </p>
            )}
          </div>
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 3 — Link agents
  // ==========================================================================
  if (step === 3) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
          <button onClick={() => { setSelectedAgentIds(new Set()); setStep(4) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
            Skip this step
          </button>
        </div>
        <button onClick={() => setStep(4)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Next: Review →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Link beacon to agents" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <p className="text-sm text-gray-300 leading-relaxed">
            We'll enable the <span className="text-teal-400">Shell</span> skill on each selected agent so they
            can run <code className="text-teal-400">/shell</code> commands routed through this beacon.
          </p>

          {agentsLoading ? (
            <div className="text-center py-8 text-sm text-gray-500">Loading agents…</div>
          ) : agents.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg bg-white/[0.02]">
              No active agents. You can link an agent later.
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">
                  {selectedAgentIds.size} of {agents.length} agent{agents.length !== 1 ? 's' : ''} selected
                </span>
                <button
                  onClick={() => {
                    if (selectedAgentIds.size === agents.length) setSelectedAgentIds(new Set())
                    else setSelectedAgentIds(new Set(agents.map((a) => a.id)))
                  }}
                  className="text-xs text-teal-400 hover:text-teal-300"
                >
                  {selectedAgentIds.size === agents.length ? 'Clear all' : 'Select all'}
                </button>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-3 bg-white/[0.02]">
                {agents.map((agent) => (
                  <label key={agent.id} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-white/5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedAgentIds.has(agent.id)}
                      onChange={(e) => {
                        const next = new Set(selectedAgentIds)
                        if (e.target.checked) next.add(agent.id)
                        else next.delete(agent.id)
                        setSelectedAgentIds(next)
                      }}
                      className="w-4 h-4 rounded border-white/20 text-teal-500 focus:ring-teal-500 bg-[#0a0a0f]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{agent.contact_name}</div>
                      <div className="text-xs text-gray-500">{agent.model_provider}/{agent.model_name}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 4 — Review
  // ==========================================================================
  if (step === 4) {
    const selectedAgents = agents.filter((a) => selectedAgentIds.has(a.id))
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button onClick={() => setStep(5)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Create beacon
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Review & create" footer={footer} size="lg">
        <div className="space-y-4">
          {stepIndicator}
          <div className="grid gap-3">
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Beacon</div>
              <div className="text-sm text-white">{config.name}{config.display_name ? ` — ${config.display_name}` : ''}</div>
              <div className="text-xs text-gray-500 mt-1">
                Mode: {config.mode} · Poll: {config.poll_interval}s · Retention: {config.retention_days}d
              </div>
            </div>
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Policy</div>
              <div className="text-sm text-white">
                Commands: {config.allowed_commands.length ? config.allowed_commands.join(', ') : 'All (Sentinel gates apply)'}
              </div>
              <div className="text-sm text-white">
                Paths: {config.allowed_paths.length ? config.allowed_paths.join(', ') : 'All'}
              </div>
              {config.yolo_mode && (
                <div className="mt-2 text-xs text-red-400 bg-red-900/20 border border-red-700/40 rounded px-2 py-1.5">
                  ⚠ YOLO mode is on — commands skip the approval queue.
                </div>
              )}
            </div>
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Agents</div>
              {selectedAgents.length === 0 ? (
                <div className="text-sm text-gray-400">No agents selected.</div>
              ) : (
                <div className="flex flex-wrap gap-2 mt-1">
                  {selectedAgents.map((a) => (
                    <span key={a.id} className="text-xs px-2 py-1 rounded bg-teal-500/15 text-teal-300">
                      {a.contact_name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 5 — Create + install instructions
  // ==========================================================================
  if (step === 5) {
    const footer = createdBeacon ? (
      <div className="flex items-center justify-between w-full">
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
          Close
        </button>
        <button onClick={() => setStep(6)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Continue →
        </button>
      </div>
    ) : (
      <div className="flex items-center justify-end w-full">
        <button disabled className="px-4 py-2 text-sm bg-teal-500/50 text-white/60 rounded-lg">
          Creating…
        </button>
      </div>
    )
    return (
      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title={createdBeacon ? `Beacon "${createdBeacon.name}" created` : 'Creating beacon…'}
        footer={footer}
        size="lg"
      >
        <div className="space-y-4">
          {stepIndicator}
          {error && (
            <div className="text-sm text-red-400 bg-red-900/20 border border-red-700/40 rounded px-3 py-2">
              {error}
            </div>
          )}
          {!createdBeacon && !error && (
            <div className="py-10 text-center text-sm text-gray-400">
              Registering beacon and enabling the Shell skill on selected agents…
            </div>
          )}
          {createdBeacon && (
            <>
              {assignmentResults.length > 0 && (
                <div className="space-y-1.5">
                  {assignmentResults.map((r) => (
                    <div key={r.agentId} className="flex items-center gap-2 text-xs">
                      <span className={`${
                        r.status === 'ok' ? 'text-green-400' :
                        r.status === 'error' ? 'text-red-400' : 'text-gray-400'
                      }`}>
                        {r.status === 'ok' ? '✓' : r.status === 'error' ? '!' : '…'}
                      </span>
                      <span className="text-gray-300">{r.agentName}</span>
                      {r.status === 'error' && r.message && <span className="text-red-400">— {r.message}</span>}
                    </div>
                  ))}
                </div>
              )}
              <BeaconInstallInstructions apiKey={createdBeacon.api_key} apiBaseUrl="" />
            </>
          )}
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 6 — Test examples
  // ==========================================================================
  const footer = (
    <div className="flex items-center justify-between w-full">
      <a
        href="/hub/shell?tab=approvals"
        className="px-4 py-2 text-sm text-gray-400 hover:text-white"
      >
        Open Approval Queue
      </a>
      <button
        onClick={() => { onComplete?.(); handleClose() }}
        className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg"
      >
        Done
      </button>
    </div>
  )
  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Try it out" footer={footer} size="lg">
      <div className="space-y-5">
        {stepIndicator}
        <p className="text-sm text-gray-300">
          Once the beacon is running, try these commands from a linked agent in Playground or WhatsApp:
        </p>
        <div className="space-y-2">
          {['/shell uptime', '/shell ls /tmp', '/shell df -h', '/shell whoami && hostname'].map((cmd) => (
            <div key={cmd} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <code className="flex-1 text-sm text-teal-300 font-mono">{cmd}</code>
              <button
                onClick={() => navigator.clipboard?.writeText(cmd)}
                className="text-xs px-2 py-1 bg-white/5 hover:bg-white/10 text-gray-300 rounded"
              >
                Copy
              </button>
            </div>
          ))}
        </div>
        <div className="text-xs text-gray-400 bg-teal-500/5 border border-teal-500/20 rounded-lg p-3">
          Unless YOLO mode is on, the first run of each unique command goes through the approval queue at
          Hub → Shell → Approvals. Approve it once and subsequent identical runs will be faster.
        </div>
      </div>
    </Modal>
  )
}
