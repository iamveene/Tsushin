'use client'

/**
 * StepVariablePanel Component
 *
 * Collapsible panel showing available output variables from previous workflow steps.
 * Provides click-to-insert functionality for easy variable injection into templates.
 *
 * Adapted from ASM Platform's StepContextHelper pattern, enhanced with:
 * - Click-to-insert at cursor position (not just clipboard copy)
 * - 7 step types (tool, notification, message, conversation, skill, slash_command, summarization)
 * - Template helpers + conditionals reference
 * - Tsushin dark theme (slate/cyan)
 */

import { useState } from 'react'
import {
  getOutputFieldsForStepType,
  getSourceStepVariables,
  generateVariableTemplate,
  HELPER_FUNCTIONS,
  FLOW_CONTEXT_VARS,
  CONDITIONAL_EXAMPLES,
  type StepVariable,
} from '@/lib/stepOutputVariables'

interface StepInfo {
  name: string
  type: string
  position: number
  config?: Record<string, any>
}

interface StepVariablePanelProps {
  allSteps: StepInfo[]
  currentStepPosition: number
  onInsertVariable: (template: string) => void
}

const STEP_TYPE_ICONS: Record<string, string> = {
  tool: 'W',         // Wrench
  notification: 'B',  // Bell
  message: 'E',       // Envelope
  conversation: 'C',  // Chat
  skill: 'S',         // Brain/Skill
  slash_command: '/',  // Command
  summarization: 'D',  // Document
  gate: 'G',          // Gate
  source: '⚡',       // v0.7.0 — trigger source step
}

// v0.7.0 release-finishing fix: source steps need kind-aware deep payload
// paths so the Notification step in an auto-generated Jira/Email flow can
// reference {{step_1.payload.issue.key}} or {{step_1.payload.subject}}
// directly. This helper picks the right list per step.
function getStepFields(step: StepInfo): StepVariable[] {
  if (step.type === 'source' || step.type === 'Source') {
    const kind = (step.config?.trigger_kind || step.config?.triggerKind || null) as string | null
    return getSourceStepVariables(kind)
  }
  return getOutputFieldsForStepType(step.type)
}

export default function StepVariablePanel({
  allSteps,
  currentStepPosition,
  onInsertVariable,
}: StepVariablePanelProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    steps: true,
    helpers: false,
    conditionals: false,
    context: false,
  })
  const [copiedVar, setCopiedVar] = useState<string | null>(null)

  const previousSteps = allSteps.filter(s => s.position < currentStepPosition)
  const stepsWithFields = previousSteps.filter(s => getStepFields(s).length > 0)

  function toggleSection(key: string) {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }))
  }

  function handleInsert(template: string, key: string) {
    onInsertVariable(template)
    setCopiedVar(key)
    // Also copy to clipboard as fallback
    navigator.clipboard.writeText(template).catch(() => {})
    setTimeout(() => setCopiedVar(null), 1500)
  }

  const totalAvailable = stepsWithFields.length

  return (
    <div className="mt-2 border border-slate-700 rounded-lg overflow-hidden">
      {/* Toggle Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between px-3 py-2 bg-slate-800/60 hover:bg-slate-800/80 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-cyan-400 font-mono text-sm">{'{x}'}</span>
          <span className="text-xs font-medium text-slate-300">Variable Reference</span>
          {totalAvailable > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 font-medium">
              {totalAvailable} step{totalAvailable !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-slate-500 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="bg-slate-900/40 max-h-[420px] overflow-y-auto">
          {/* Usage hint */}
          <div className="px-3 py-2 border-b border-slate-800 bg-slate-800/30">
            <p className="text-[11px] text-slate-400">
              Click any variable to insert it at your cursor position.
              Variables are replaced with actual values when the flow runs.
            </p>
          </div>

          {/* ── Section 1: Previous Steps ── */}
          <div className="border-b border-slate-800">
            <button
              onClick={() => toggleSection('steps')}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-800/40 transition-colors"
            >
              <span className="text-xs font-medium text-slate-300">Previous Steps</span>
              <svg
                className={`w-3.5 h-3.5 text-slate-500 transition-transform ${expandedSections.steps ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {expandedSections.steps && (
              <div className="px-3 pb-3">
                {stepsWithFields.length === 0 ? (
                  <p className="text-[11px] text-slate-500 py-2">
                    {previousSteps.length === 0
                      ? 'This is the first step. Add steps above to see their output variables here.'
                      : 'No preceding steps with known output variables.'}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {stepsWithFields.map((step) => {
                      const fields = getStepFields(step)
                      const alias = step.config?.output_alias
                      const normalizedName = step.name.toLowerCase().replace(/[\s-]/g, '_')

                      return (
                        <div key={step.position} className="rounded-lg border border-slate-700/60 overflow-hidden">
                          {/* Step Header */}
                          <div className="px-2.5 py-1.5 bg-slate-800/50 flex items-center gap-2">
                            <span className="w-5 h-5 rounded flex items-center justify-center bg-slate-700 text-[10px] font-bold text-cyan-400">
                              {STEP_TYPE_ICONS[step.type] || '?'}
                            </span>
                            <span className="text-xs font-medium text-slate-200">
                              Step {step.position}: {step.name}
                            </span>
                            <span className="text-[10px] text-slate-500">({step.type})</span>
                          </div>

                          {/* Reference syntax hint */}
                          <div className="px-2.5 py-1 bg-slate-800/20 border-b border-slate-800/50">
                            <span className="text-[10px] text-slate-500">
                              Ref by position: <code className="text-amber-400/70">step_{step.position}</code>
                              {' | '}name: <code className="text-amber-400/70">{normalizedName}</code>
                              {alias && (
                                <>{' | '}alias: <code className="text-amber-400/70">{alias}</code></>
                              )}
                            </span>
                          </div>

                          {/* Variable chips */}
                          <div className="p-2 flex flex-wrap gap-1.5">
                            {fields.map((field: StepVariable) => {
                              const template = generateVariableTemplate(step.position, field.field)
                              const varKey = `${step.position}-${field.field}`
                              const isInserted = copiedVar === varKey

                              return (
                                <button
                                  key={varKey}
                                  onClick={() => handleInsert(template, varKey)}
                                  title={`${field.description} (${field.type})\nClick to insert: ${template}`}
                                  className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono
                                    border transition-all cursor-pointer
                                    ${isInserted
                                      ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                                      : 'bg-slate-800/50 border-slate-700 text-amber-400/90 hover:bg-cyan-500/10 hover:border-cyan-500/30 hover:text-cyan-400'
                                    }`}
                                >
                                  {isInserted ? (
                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                    </svg>
                                  ) : null}
                                  .{field.field}
                                  <span className="text-slate-500 text-[9px] font-sans ml-0.5">{field.type}</span>
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── Section 2: Helpers ── */}
          <div className="border-b border-slate-800">
            <button
              onClick={() => toggleSection('helpers')}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-800/40 transition-colors"
            >
              <span className="text-xs font-medium text-slate-300">Helper Functions</span>
              <svg
                className={`w-3.5 h-3.5 text-slate-500 transition-transform ${expandedSections.helpers ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {expandedSections.helpers && (
              <div className="px-3 pb-3 space-y-1">
                {HELPER_FUNCTIONS.map((helper) => {
                  const key = `helper-${helper.name}`
                  const isInserted = copiedVar === key

                  return (
                    <button
                      key={helper.name}
                      onClick={() => handleInsert(helper.syntax, key)}
                      title={helper.description}
                      className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-left transition-all
                        ${isInserted
                          ? 'bg-emerald-500/10'
                          : 'hover:bg-slate-800/50'
                        }`}
                    >
                      <code className={`text-[11px] font-mono ${isInserted ? 'text-emerald-400' : 'text-amber-400/80'}`}>
                        {helper.syntax}
                      </code>
                      <span className="text-[10px] text-slate-500 ml-2 flex-shrink-0">{helper.description}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* ── Section 3: Conditionals ── */}
          <div className="border-b border-slate-800">
            <button
              onClick={() => toggleSection('conditionals')}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-800/40 transition-colors"
            >
              <span className="text-xs font-medium text-slate-300">Conditionals</span>
              <svg
                className={`w-3.5 h-3.5 text-slate-500 transition-transform ${expandedSections.conditionals ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {expandedSections.conditionals && (
              <div className="px-3 pb-3 space-y-1">
                {CONDITIONAL_EXAMPLES.map((cond, i) => {
                  const key = `cond-${i}`
                  const isInserted = copiedVar === key

                  return (
                    <button
                      key={i}
                      onClick={() => handleInsert(cond.syntax, key)}
                      title={cond.description}
                      className={`w-full flex items-start gap-2 px-2 py-1.5 rounded text-left transition-all
                        ${isInserted
                          ? 'bg-emerald-500/10'
                          : 'hover:bg-slate-800/50'
                        }`}
                    >
                      <code className={`text-[11px] font-mono break-all ${isInserted ? 'text-emerald-400' : 'text-violet-400/80'}`}>
                        {cond.syntax}
                      </code>
                      <span className="text-[10px] text-slate-500 flex-shrink-0">{cond.description}</span>
                    </button>
                  )
                })}
                <div className="mt-1 px-2">
                  <p className="text-[10px] text-slate-500">
                    Operators: <code className="text-slate-400">==</code> <code className="text-slate-400">!=</code>{' '}
                    <code className="text-slate-400">&gt;</code> <code className="text-slate-400">&lt;</code>{' '}
                    <code className="text-slate-400">and</code> <code className="text-slate-400">or</code>{' '}
                    <code className="text-slate-400">not</code>
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* ── Section 4: Flow Context ── */}
          <div>
            <button
              onClick={() => toggleSection('context')}
              className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-800/40 transition-colors"
            >
              <span className="text-xs font-medium text-slate-300">Flow Context</span>
              <svg
                className={`w-3.5 h-3.5 text-slate-500 transition-transform ${expandedSections.context ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {expandedSections.context && (
              <div className="px-3 pb-3 space-y-1">
                {FLOW_CONTEXT_VARS.map((ctx) => {
                  const template = `{{${ctx.variable}}}`
                  const key = `ctx-${ctx.variable}`
                  const isInserted = copiedVar === key

                  return (
                    <button
                      key={ctx.variable}
                      onClick={() => handleInsert(template, key)}
                      title={ctx.description}
                      className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-left transition-all
                        ${isInserted
                          ? 'bg-emerald-500/10'
                          : 'hover:bg-slate-800/50'
                        }`}
                    >
                      <code className={`text-[11px] font-mono ${isInserted ? 'text-emerald-400' : 'text-cyan-400/80'}`}>
                        {template}
                      </code>
                      <span className="text-[10px] text-slate-500 ml-2 flex-shrink-0">{ctx.description}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
