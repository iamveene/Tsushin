'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { api, Agent, SandboxedTool } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onComplete?: () => void
}

type Step = 1 | 2 | 3 | 4 | 5

interface AssignmentRow {
  key: string
  agentName: string
  toolName: string
  status: 'pending' | 'ok' | 'skipped' | 'error'
  message?: string
}

const TOOL_EXAMPLES: Record<string, { command: string; description: string }> = {
  dig: {
    command: '/tool dig lookup domain=google.com record_type=A',
    description: 'DNS lookup for a domain',
  },
  nmap: {
    command: '/tool nmap quick_scan target=scanme.nmap.org',
    description: 'Quick port scan',
  },
  httpx: {
    command: '/tool httpx probe target=https://example.com',
    description: 'HTTP fingerprint + tech detection',
  },
  whois_lookup: {
    command: '/tool whois_lookup lookup domain=example.com',
    description: 'WHOIS registration record',
  },
  webhook: {
    command: '/tool webhook get url=https://httpbin.org/get',
    description: 'Generic HTTP client',
  },
  subfinder: {
    command: '/tool subfinder enumerate domain=example.com',
    description: 'Subdomain enumeration',
  },
  katana: {
    command: '/tool katana crawl target=https://example.com depth=2',
    description: 'Web crawler',
  },
  nuclei: {
    command: '/tool nuclei scan target=https://example.com',
    description: 'Template-based vulnerability scan',
  },
  sqlmap: {
    command: '/tool sqlmap test url=https://example.com/?id=1',
    description: 'SQLi detection (safe baseline only)',
  },
}

export default function SandboxedToolsSetupWizard({ isOpen, onClose, onComplete }: Props) {
  const [step, setStep] = useState<Step>(1)

  const [tools, setTools] = useState<SandboxedTool[]>([])
  const [toolsLoading, setToolsLoading] = useState(false)
  const [selectedToolIds, setSelectedToolIds] = useState<Set<number>>(new Set())

  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())

  const [assignmentRows, setAssignmentRows] = useState<AssignmentRow[]>([])
  const [applying, setApplying] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setTools([])
    setSelectedToolIds(new Set())
    setAgents([])
    setSelectedAgentIds(new Set())
    setAssignmentRows([])
    setApplying(false)
  }, [isOpen])

  useEffect(() => {
    if (step !== 2 || tools.length > 0) return
    setToolsLoading(true)
    api
      .getSandboxedTools()
      .then((list) => {
        setTools(list)
        setSelectedToolIds(new Set(list.filter((t) => t.is_enabled).map((t) => t.id)))
      })
      .finally(() => setToolsLoading(false))
  }, [step, tools.length])

  useEffect(() => {
    if (step !== 3 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true).then(setAgents).finally(() => setAgentsLoading(false))
  }, [step, agents.length])

  const runApply = async () => {
    setApplying(true)
    const selectedTools = tools.filter((t) => selectedToolIds.has(t.id))
    const selectedAgents = agents.filter((a) => selectedAgentIds.has(a.id))

    const rows: AssignmentRow[] = []
    for (const agent of selectedAgents) {
      rows.push({
        key: `skill-${agent.id}`,
        agentName: agent.contact_name,
        toolName: 'sandboxed_tools skill',
        status: 'pending',
      })
      for (const tool of selectedTools) {
        rows.push({
          key: `tool-${agent.id}-${tool.id}`,
          agentName: agent.contact_name,
          toolName: tool.name,
          status: 'pending',
        })
      }
    }
    setAssignmentRows(rows)

    let rowIdx = 0
    for (const agent of selectedAgents) {
      // Enable the skill (idempotent)
      try {
        await api.updateAgentSkill(agent.id, 'sandboxed_tools', { is_enabled: true })
        setAssignmentRows((prev) =>
          prev.map((r, idx) => (idx === rowIdx ? { ...r, status: 'ok' } : r)),
        )
      } catch (err: any) {
        setAssignmentRows((prev) =>
          prev.map((r, idx) =>
            idx === rowIdx ? { ...r, status: 'error', message: err?.message || 'Failed' } : r,
          ),
        )
      }
      rowIdx += 1

      // Assign each selected tool
      for (const tool of selectedTools) {
        try {
          await api.addAgentSandboxedTool(agent.id, {
            sandboxed_tool_id: tool.id,
            is_enabled: true,
          })
          setAssignmentRows((prev) =>
            prev.map((r, idx) => (idx === rowIdx ? { ...r, status: 'ok' } : r)),
          )
        } catch (err: any) {
          // 400 "already assigned" is idempotent success
          const msg = err?.message || ''
          const alreadyAssigned = /already|409|400/i.test(msg)
          setAssignmentRows((prev) =>
            prev.map((r, idx) =>
              idx === rowIdx
                ? {
                    ...r,
                    status: alreadyAssigned ? 'skipped' : 'error',
                    message: alreadyAssigned ? 'already assigned' : msg,
                  }
                : r,
            ),
          )
        }
        rowIdx += 1
      }
    }
    setApplying(false)
  }

  useEffect(() => {
    if (step === 5 && assignmentRows.length === 0 && !applying) {
      runApply()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  if (!isOpen) return null

  const totalSteps = 5
  const stepIndicator = (
    <div className="flex items-center justify-center gap-2 mb-5">
      {[1, 2, 3, 4, 5].map((n) => (
        <div key={n} className="flex items-center gap-2">
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
            <div className={`w-6 h-0.5 ${n < step ? 'bg-teal-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
        <button onClick={() => setStep(2)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Get started →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Set up sandboxed tools" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">What are sandboxed tools?</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              Tsushin ships with a curated toolbox that runs inside an isolated Docker workspace per tenant.
              Agents call them with <code className="text-teal-400">/tool &lt;name&gt; &lt;command&gt; param=value</code>.
              Pre-seeded: dig, nmap, httpx, whois, webhook, subfinder, katana, nuclei, sqlmap.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Isolation</div>
              <div className="text-white">Per-tenant Docker workspace</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Tools seeded</div>
              <div className="text-white">9 out of the box</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Custom tools</div>
              <div className="text-white">Add your own via Hub → Sandboxed Tools</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Execution</div>
              <div className="text-white">LLM-decided or explicit slash command</div>
            </div>
          </div>
        </div>
      </Modal>
    )
  }

  if (step === 2) {
    const canProceed = selectedToolIds.size > 0
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
      <Modal isOpen={isOpen} onClose={onClose} title="Select tools" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          {toolsLoading ? (
            <div className="py-10 text-center text-sm text-gray-400">Loading tools…</div>
          ) : tools.length === 0 ? (
            <div className="py-6 text-center text-sm text-gray-400 border border-white/5 rounded-lg bg-white/[0.02]">
              No sandboxed tools found in this tenant. Seed them from Hub → Sandboxed Tools first.
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">
                  {selectedToolIds.size} of {tools.length} tools selected
                </span>
                <div className="flex gap-3">
                  <button
                    onClick={() => setSelectedToolIds(new Set(tools.map((t) => t.id)))}
                    className="text-xs text-teal-400 hover:text-teal-300"
                  >
                    Select all
                  </button>
                  <button
                    onClick={() => setSelectedToolIds(new Set())}
                    className="text-xs text-gray-400 hover:text-gray-300"
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2 max-h-80 overflow-y-auto">
                {tools.map((tool) => (
                  <label
                    key={tool.id}
                    className="flex items-start gap-3 p-3 rounded-lg border border-white/10 hover:bg-white/[0.03] cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedToolIds.has(tool.id)}
                      onChange={(e) => {
                        const next = new Set(selectedToolIds)
                        if (e.target.checked) next.add(tool.id)
                        else next.delete(tool.id)
                        setSelectedToolIds(next)
                      }}
                      className="mt-1 w-4 h-4 rounded border-white/20 text-teal-500 focus:ring-teal-500 bg-[#0a0a0f]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{tool.name}</div>
                      <div className="text-[11px] text-gray-500 truncate">{tool.tool_type}</div>
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

  if (step === 3) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        </div>
        <button
          onClick={() => setStep(4)}
          disabled={selectedAgentIds.size === 0}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40"
        >
          Next: Review →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Link tools to agents" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <p className="text-sm text-gray-300">
            Each selected tool will be mapped to each selected agent, and the
            <span className="text-teal-400"> sandboxed_tools</span> skill will be enabled on them.
          </p>
          {agentsLoading ? (
            <div className="text-center py-8 text-sm text-gray-500">Loading agents…</div>
          ) : agents.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg bg-white/[0.02]">
              No active agents. Create one from Studio first.
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

  if (step === 4) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button onClick={() => setStep(5)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Apply
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Review & apply" footer={footer} size="lg">
        <div className="space-y-4">
          {stepIndicator}
          <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
            <div className="text-xs text-gray-500 mb-1">Summary</div>
            <div className="text-sm text-white">
              {selectedToolIds.size} tool{selectedToolIds.size !== 1 ? 's' : ''} ×{' '}
              {selectedAgentIds.size} agent{selectedAgentIds.size !== 1 ? 's' : ''} ={' '}
              {selectedToolIds.size * selectedAgentIds.size} mappings
            </div>
          </div>
          <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
            <div className="text-xs text-gray-500 mb-1">Tools</div>
            <div className="flex flex-wrap gap-2">
              {tools.filter((t) => selectedToolIds.has(t.id)).map((t) => (
                <span key={t.id} className="text-xs px-2 py-1 rounded bg-teal-500/15 text-teal-300">{t.name}</span>
              ))}
            </div>
          </div>
          <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
            <div className="text-xs text-gray-500 mb-1">Agents</div>
            <div className="flex flex-wrap gap-2">
              {agents.filter((a) => selectedAgentIds.has(a.id)).map((a) => (
                <span key={a.id} className="text-xs px-2 py-1 rounded bg-teal-500/15 text-teal-300">{a.contact_name}</span>
              ))}
            </div>
          </div>
        </div>
      </Modal>
    )
  }

  // Step 5 — apply + success
  const allDone = assignmentRows.length > 0 && assignmentRows.every((r) => r.status !== 'pending')
  const selectedTools = tools.filter((t) => selectedToolIds.has(t.id))
  const footer = allDone ? (
    <div className="flex items-center justify-between w-full">
      <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Close</button>
      <button
        onClick={() => { onComplete?.(); onClose() }}
        className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg"
      >
        Done
      </button>
    </div>
  ) : (
    <div className="flex items-center justify-end w-full">
      <button disabled className="px-4 py-2 text-sm bg-teal-500/50 text-white/60 rounded-lg">Applying…</button>
    </div>
  )
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={allDone ? 'Tools linked' : 'Linking tools…'}
      footer={footer}
      size="lg"
    >
      <div className="space-y-5">
        {stepIndicator}
        {assignmentRows.length === 0 ? (
          <div className="py-10 text-center text-sm text-gray-400">Starting…</div>
        ) : (
          <div className="max-h-48 overflow-y-auto space-y-1.5">
            {assignmentRows.map((r) => (
              <div key={r.key} className="flex items-center gap-2 text-xs text-gray-300">
                <span className={`${
                  r.status === 'ok' ? 'text-green-400' :
                  r.status === 'error' ? 'text-red-400' :
                  r.status === 'skipped' ? 'text-gray-500' : 'text-gray-400'
                }`}>
                  {r.status === 'ok' ? '✓' : r.status === 'error' ? '!' : r.status === 'skipped' ? '⇢' : '…'}
                </span>
                <span className="flex-1 truncate">{r.agentName} — {r.toolName}</span>
                {r.message && <span className="text-[11px] text-gray-500">{r.message}</span>}
              </div>
            ))}
          </div>
        )}
        {allDone && (
          <>
            <div className="pt-3 border-t border-white/5">
              <h4 className="text-sm font-medium text-white mb-2">Try one of these</h4>
              <div className="space-y-2">
                {selectedTools
                  .map((t) => TOOL_EXAMPLES[t.name])
                  .filter(Boolean)
                  .slice(0, 5)
                  .map((ex, idx) => (
                    <div key={idx} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/5">
                      <div className="flex-1 min-w-0">
                        <code className="text-sm text-teal-300 font-mono block truncate">{ex!.command}</code>
                        <div className="text-[11px] text-gray-500">{ex!.description}</div>
                      </div>
                      <button
                        onClick={() => navigator.clipboard?.writeText(ex!.command)}
                        className="text-xs px-2 py-1 bg-white/5 hover:bg-white/10 text-gray-300 rounded"
                      >
                        Copy
                      </button>
                    </div>
                  ))}
              </div>
            </div>
            <div className="text-xs text-gray-400 bg-teal-500/5 border border-teal-500/20 rounded-lg p-3">
              Send these from an agent in Playground or WhatsApp. Executions show up in Hub → Sandboxed Tools → Executions.
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
