/**
 * Browser-group folding helpers — shared by the flow editor step list and
 * the watcher run-detail modal so both surfaces render the same
 * collapsible card for a recording session.
 *
 * Two grouping signals:
 *   1. A real `browser_group` parent followed by `browser_automation`
 *      children that share its `group_recording_id`. This is the new
 *      production-ready shape emitted by the recorder /compile endpoint.
 *   2. Two or more consecutive `browser_automation` steps with NO
 *      preceding `browser_group` (legacy flat shape). They are folded
 *      into a *synthetic* group so the editor can render the same card.
 *      `Save` persists the synthetic group as a real one via the
 *      backend's compile_events_into_group shape.
 *
 * The helper is intentionally generic over the input shape so it can run
 * against both the editor's step list (CreateFlowStepData / EditableStepData)
 * and the watcher's FlowNodeRun arrays — callers supply a row mapper.
 */

import type { RecordedDriverLabel } from './client'

export interface BrowserGroupParentData {
  groupRecordingId?: string
  targetHost: string
  driver: RecordedDriverLabel
  recordedAt?: string | null
}

export type GroupedStepEntry<T> =
  | { kind: 'single'; step: T; originalIndex: number }
  | {
      kind: 'group'
      // Real `browser_group` parent step if present, else null (synthetic).
      parent: T | null
      children: T[]
      // Original indices of (parent ? [parent, ...children] : children) in
      // the input array — drives delete/ungroup operations.
      originalIndices: number[]
      synthetic: boolean
      summary: BrowserGroupParentData
    }

interface StepLike {
  type: string
  // Optional flat config bag — the helper inspects `group_recording_id`,
  // `recorded_driver`, `recorded_at`, `target_host` if present.
  config?: Record<string, any> | null
}

function readConfig(step: StepLike): Record<string, any> {
  const cfg = (step.config ?? {}) as Record<string, any>
  return cfg
}

function summaryFromParent(step: StepLike): BrowserGroupParentData {
  const cfg = readConfig(step)
  const driver = (cfg.recorded_driver as RecordedDriverLabel) || 'human'
  return {
    groupRecordingId: cfg.group_recording_id ?? undefined,
    targetHost: cfg.target_host || 'browser session',
    driver,
    recordedAt: cfg.recorded_at ?? null,
  }
}

function summaryFromChildren(children: StepLike[]): BrowserGroupParentData {
  // Pick the first child's metadata as the canonical group identity.
  // Driver collapses to "mixed" if children disagree.
  const driversSeen = new Set<string>()
  let groupRecordingId: string | undefined
  let recordedAt: string | undefined
  let targetHost = 'browser session'

  for (const child of children) {
    const cfg = readConfig(child)
    if (!groupRecordingId && cfg.group_recording_id) groupRecordingId = cfg.group_recording_id
    if (!recordedAt && cfg.recorded_at) recordedAt = cfg.recorded_at
    if (cfg.recorded_driver) driversSeen.add(cfg.recorded_driver)
    if (cfg.url && targetHost === 'browser session') {
      try {
        targetHost = new URL(cfg.url).hostname.replace(/^www\./, '')
      } catch {
        // ignore non-URL strings
      }
    }
  }

  const driver: RecordedDriverLabel =
    driversSeen.size === 0
      ? 'human'
      : driversSeen.size === 1
        ? (Array.from(driversSeen)[0] as RecordedDriverLabel)
        : 'mixed'

  return { groupRecordingId, targetHost, driver, recordedAt }
}

/**
 * Fold consecutive browser_automation (and optionally a leading
 * browser_group parent) into grouped entries. Other step types pass
 * through as 'single' entries.
 */
export function groupBrowserSteps<T extends StepLike>(steps: T[]): GroupedStepEntry<T>[] {
  const out: GroupedStepEntry<T>[] = []
  let i = 0
  while (i < steps.length) {
    const step = steps[i]

    if (step.type === 'browser_group') {
      const parentCfg = readConfig(step)
      const expectedId = parentCfg.group_recording_id
      const children: T[] = []
      const indices: number[] = [i]
      let j = i + 1
      while (j < steps.length && steps[j].type === 'browser_automation') {
        const childCfg = readConfig(steps[j])
        // Stop at the first child that explicitly belongs to a different
        // recording — keeps two back-to-back recordings from collapsing.
        if (
          expectedId &&
          childCfg.group_recording_id &&
          childCfg.group_recording_id !== expectedId
        ) {
          break
        }
        children.push(steps[j])
        indices.push(j)
        j++
      }
      out.push({
        kind: 'group',
        parent: step,
        children,
        originalIndices: indices,
        synthetic: false,
        summary: summaryFromParent(step),
      })
      i = j
      continue
    }

    if (step.type === 'browser_automation') {
      // Greedy synthetic-group when 2+ consecutive browser_automation steps
      // appear without a parent. Single isolated browser_automation steps
      // stay flat — they may be one-off manual additions, not a recording.
      const children: T[] = [step]
      const indices: number[] = [i]
      let j = i + 1
      while (j < steps.length && steps[j].type === 'browser_automation') {
        // If a child carries a group_recording_id and the running summary
        // disagrees, stop — two recordings back-to-back.
        const firstId = readConfig(children[0]).group_recording_id
        const nextId = readConfig(steps[j]).group_recording_id
        if (firstId && nextId && firstId !== nextId) break
        children.push(steps[j])
        indices.push(j)
        j++
      }
      if (children.length >= 2) {
        out.push({
          kind: 'group',
          parent: null,
          children,
          originalIndices: indices,
          synthetic: true,
          summary: summaryFromChildren(children),
        })
        i = j
        continue
      }
      // Fall through: lone browser_automation as 'single'
    }

    out.push({ kind: 'single', step, originalIndex: i })
    i++
  }
  return out
}

/**
 * Build a child-row label for the BrowserGroupStep card from a
 * browser_automation step's config. Matches the recorder's naming
 * heuristic ("fill_q", "click_btn") but reads from arbitrary configs
 * so legacy flat steps also render meaningfully.
 */
export function describeBrowserChild(step: StepLike): { label: string; toolAction?: string } {
  const cfg = readConfig(step)
  const toolAction = cfg.tool_action as string | undefined
  // Prefer the step's own name if it's descriptive (recorder emits e.g.
  // "fill_objeto", "solve_captcha"); else fall back to action + selector.
  const name = (step as any).name as string | undefined
  if (name && name !== 'Step' && !/^Step \d+$/.test(name)) {
    return { label: name, toolAction }
  }
  if (toolAction === 'navigate' && cfg.url) {
    try {
      return { label: new URL(cfg.url).host, toolAction }
    } catch {
      return { label: String(cfg.url), toolAction }
    }
  }
  const selectors = (cfg.selectors as Array<{ selector?: string }> | undefined) || []
  const sel = selectors[0]?.selector
  if (sel) return { label: sel, toolAction }
  return { label: toolAction || 'browser action', toolAction }
}
