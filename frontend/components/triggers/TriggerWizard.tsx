'use client'

import { useEffect, useMemo, useState } from 'react'
import Wizard, { type WizardStep } from '@/components/ui/Wizard'
import { api, type TriggerCatalogEntry } from '@/lib/client'

export type TriggerId = 'email' | 'webhook'

interface Props {
  isOpen: boolean
  onClose: () => void
  onTriggerSelected: (triggerId: TriggerId) => void
}

const WIZARD_STEPS: WizardStep[] = [
  {
    id: 'trigger',
    label: 'Trigger',
    description: 'Choose the event source that should wake agents or flows.',
  },
  {
    id: 'configure',
    label: 'Configure',
    description: 'Finish setup in the trigger-specific wizard.',
  },
]

// Fallback catalog — matches TRIGGER_CATALOG in backend/channels/catalog.py.
// Drift guard: backend/tests/test_wizard_drift.py.
const FALLBACK_TRIGGERS: Array<TriggerCatalogEntry & { trigger_id: TriggerId }> = [
  {
    trigger_id: 'email',
    id: 'email',
    display_name: 'Email',
    description: 'Watch Gmail inbox activity and wake agents from matching messages.',
    requires_setup: true,
    setup_hint: 'Create an email trigger under Hub -> Communication -> Triggers.',
    icon_hint: 'gmail',
    tenant_has_configured: false,
  },
  {
    trigger_id: 'webhook',
    id: 'webhook',
    display_name: 'Webhook',
    description: 'Receive signed external events and optionally call back a customer system.',
    requires_setup: true,
    setup_hint: 'Create a webhook trigger under Hub -> Communication -> Triggers.',
    icon_hint: 'webhook',
    tenant_has_configured: false,
  },
]

const ICONS: Record<TriggerId, string> = {
  email: '✉️',
  webhook: '↪',
}

export default function TriggerWizard({ isOpen, onClose, onTriggerSelected }: Props) {
  const [triggers, setTriggers] = useState(FALLBACK_TRIGGERS)
  const [selectedTrigger, setSelectedTrigger] = useState<TriggerId | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return

    let cancelled = false
    api.getTriggerCatalog()
      .then((list) => {
        if (cancelled || !Array.isArray(list) || list.length === 0) return
        const liveById = new Map(list.map((entry) => [entry.id, entry]))
        setTriggers(
          FALLBACK_TRIGGERS.map((fallback) => {
            const live = liveById.get(fallback.id)
            return live
              ? {
                  ...fallback,
                  ...live,
                  trigger_id: fallback.trigger_id,
                }
              : fallback
          }),
        )
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err?.message || 'Could not load live trigger catalog')
      })

    return () => {
      cancelled = true
    }
  }, [isOpen])

  const actionableTriggers = useMemo(
    () => triggers.filter((entry) => entry.requires_setup),
    [triggers],
  )

  const handleContinue = () => {
    if (!selectedTrigger) return
    onClose()
    onTriggerSelected(selectedTrigger)
  }

  return (
    <Wizard
      isOpen={isOpen}
      onClose={onClose}
      title="Add Trigger"
      steps={WIZARD_STEPS}
      currentStep={1}
      footer={(
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleContinue}
            disabled={!selectedTrigger}
            className="rounded-lg bg-tsushin-accent px-4 py-2 text-sm font-medium text-[#051218] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Continue to Setup
          </button>
        </div>
      )}
      stepTitle="Pick a trigger type"
      stepDescription="Triggers wake agents from events outside the regular chat channels. Start with inbox activity or signed webhooks."
    >
      <div className="space-y-5">
        {loadError && (
          <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            Using offline trigger catalog — {loadError}
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-2">
          {actionableTriggers.map((trigger) => {
            const selected = selectedTrigger === trigger.trigger_id
            return (
              <button
                key={trigger.trigger_id}
                type="button"
                onClick={() => setSelectedTrigger(trigger.trigger_id)}
                className={`rounded-2xl border p-4 text-left transition-all ${
                  selected
                    ? 'border-tsushin-accent/50 bg-tsushin-accent/10'
                    : 'border-tsushin-border/70 bg-tsushin-slate/5 hover:bg-tsushin-slate/10'
                }`}
              >
                <div className="mb-3 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-black/20 text-lg">
                    <span aria-hidden="true">{ICONS[trigger.trigger_id]}</span>
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{trigger.display_name}</span>
                      {trigger.tenant_has_configured && (
                        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                          Already configured
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-tsushin-slate">{trigger.description}</p>
                  </div>
                </div>
                <p className="text-[11px] text-tsushin-slate/80">{trigger.setup_hint}</p>
              </button>
            )
          })}
        </div>
      </div>
    </Wizard>
  )
}
