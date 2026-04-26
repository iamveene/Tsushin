'use client'

/**
 * Webhook trigger detail page.
 *
 * Wave 3 of the Triggers ↔ Flows unification (release/0.7.0) retired the
 * standalone fork (~370 lines) into the shared `<TriggerDetailShell>`
 * component, which now handles all five trigger kinds with a uniform
 * Source / Routing / Outputs structure.
 */

import TriggerDetailShell from '@/components/triggers/TriggerDetailShell'

export default function WebhookTriggerDetailPage() {
  return <TriggerDetailShell kind="webhook" />
}
