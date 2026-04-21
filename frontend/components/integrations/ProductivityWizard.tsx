'use client'

/**
 * ProductivityWizard — guided entry point for the Hub > Productivity tab.
 *
 * Replaces the fixed "Google Integration / Asana / Google Calendar (Not
 * Connected)" placeholder cards with a single "+ Add Productivity
 * Integration" launcher. The wizard walks the user through two steps
 * (category -> service) and then hands off to the existing per-service
 * setup wizard (GmailSetupWizard, GoogleCalendarSetupWizard, Asana OAuth
 * connect). Those sub-wizards already handle OAuth popups, polling, and
 * Link-to-Agents, so the dispatcher pattern avoids duplicating deep flows.
 *
 * Catalog source: /api/hub/productivity-services (see
 * backend/api/routes_hub_providers.py). The frontend keeps a static
 * fallback so the picker works offline / pre-catalog.
 *
 * backend/tests/test_wizard_drift.py cross-checks every backend catalog
 * entry against the fallback array below.
 */

import { useEffect, useMemo, useState } from 'react'
import Modal from '@/components/ui/Modal'
import { api, type ProductivityServiceInfo } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  /** Invoked when the user picks a service on step 2 and clicks Continue.
   *  The Hub page is responsible for opening the appropriate sub-wizard
   *  (GmailSetupWizard, GoogleCalendarSetupWizard) or kicking off the
   *  Asana OAuth flow. The wizard closes itself before the callback fires. */
  onServiceSelected: (serviceId: string) => void
}

type CategoryId = 'calendar' | 'email' | 'tasks' | 'knowledge_base'

interface CategoryMeta {
  id: CategoryId
  label: string
  description: string
  icon: string
}

const CATEGORIES: CategoryMeta[] = [
  { id: 'calendar', label: 'Calendar', description: 'Schedule, query and manage events.', icon: '📅' },
  { id: 'email', label: 'Email', description: 'Read, search, and route emails.', icon: '✉️' },
  { id: 'tasks', label: 'Tasks & Projects', description: 'Track work items across teams.', icon: '✅' },
  { id: 'knowledge_base', label: 'Knowledge Base', description: 'Link docs and wikis to agents.', icon: '📚' },
]

// Fallback catalog — matches PRODUCTIVITY_CATALOG in
// backend/hub/productivity_catalog.py. Drift guard:
// backend/tests/test_wizard_drift.py.
const FALLBACK_SERVICES: ProductivityServiceInfo[] = [
  {
    id: 'google_calendar',
    name: 'Google Calendar',
    description: 'Create, update, and query calendar events from agents.',
    category: 'calendar',
    vendor: 'google',
    requires_oauth: true,
    oauth_provider: 'google',
    integration_type: 'calendar',
    icon_hint: 'calendar',
    status: 'available',
    tenant_has_configured: false,
    tenant_has_oauth_credentials: false,
  },
  {
    id: 'gmail',
    name: 'Gmail',
    description: 'Read, search, and route emails through agents.',
    category: 'email',
    vendor: 'google',
    requires_oauth: true,
    oauth_provider: 'google',
    integration_type: 'gmail',
    icon_hint: 'gmail',
    status: 'available',
    tenant_has_configured: false,
    tenant_has_oauth_credentials: false,
  },
  {
    id: 'asana',
    name: 'Asana',
    description: 'Create and manage tasks across Asana workspaces.',
    category: 'tasks',
    vendor: 'asana',
    requires_oauth: true,
    oauth_provider: 'asana',
    integration_type: 'asana',
    icon_hint: 'asana',
    status: 'available',
    tenant_has_configured: false,
    tenant_has_oauth_credentials: false,
  },
]

export default function ProductivityWizard({ isOpen, onClose, onServiceSelected }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  const [category, setCategory] = useState<CategoryId | null>(null)
  const [services, setServices] = useState<ProductivityServiceInfo[]>(FALLBACK_SERVICES)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null)

  // Reset state whenever the modal opens, and fetch the live catalog.
  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setCategory(null)
    setSelectedServiceId(null)
    setLoadError(null)
    let cancelled = false
    api.getProductivityServices()
      .then(list => { if (!cancelled && Array.isArray(list) && list.length > 0) setServices(list) })
      .catch(err => {
        // Fall back to the static array; the picker still works offline.
        if (!cancelled) setLoadError(err?.message || 'Could not load live catalog')
      })
    return () => { cancelled = true }
  }, [isOpen])

  const categoryServices = useMemo(() => {
    if (!category) return []
    return services.filter(s => s.category === category && s.status !== 'coming_soon')
  }, [services, category])

  const categoriesWithServices = useMemo(() => {
    return new Set(services.map(s => s.category))
  }, [services])

  const handleContinue = () => {
    if (!selectedServiceId) return
    // Close the outer wizard before handing off — the per-service sub-wizard
    // will open its own modal and we don't want them stacked.
    onClose()
    onServiceSelected(selectedServiceId)
  }

  if (!isOpen) return null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Add Productivity Integration" size="lg">
      <div className="space-y-5">
        {/* Stepper */}
        <div className="flex items-center gap-2 text-xs text-tsushin-slate">
          <span className={`px-2 py-0.5 rounded-full border ${step === 1 ? 'bg-tsushin-accent/20 border-tsushin-accent/40 text-tsushin-accent' : 'border-tsushin-slate/20'}`}>1. Category</span>
          <span>→</span>
          <span className={`px-2 py-0.5 rounded-full border ${step === 2 ? 'bg-tsushin-accent/20 border-tsushin-accent/40 text-tsushin-accent' : 'border-tsushin-slate/20'}`}>2. Service</span>
          <span>→</span>
          <span className="px-2 py-0.5 rounded-full border border-tsushin-slate/20 opacity-60">3. Connect</span>
        </div>

        {loadError && (
          <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-3 py-2">
            Using offline catalog — {loadError}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <p className="text-sm text-tsushin-slate">
              Pick what kind of productivity tool you want to connect. Only categories with at least one
              available service are enabled.
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              {CATEGORIES.map(cat => {
                const enabled = categoriesWithServices.has(cat.id)
                const selected = category === cat.id
                return (
                  <button
                    key={cat.id}
                    type="button"
                    disabled={!enabled}
                    onClick={() => setCategory(cat.id)}
                    className={`text-left p-4 rounded-xl border transition-all ${
                      selected
                        ? 'bg-tsushin-accent/10 border-tsushin-accent/50'
                        : enabled
                          ? 'bg-tsushin-slate/5 border-tsushin-slate/20 hover:bg-tsushin-slate/10'
                          : 'bg-tsushin-slate/5 border-tsushin-slate/10 opacity-50 cursor-not-allowed'
                    }`}
                  >
                    <div className="flex items-center gap-3 mb-1">
                      <span className="text-2xl">{cat.icon}</span>
                      <span className="font-semibold text-white">{cat.label}</span>
                      {!enabled && (
                        <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-tsushin-slate/20 text-tsushin-slate">
                          Coming soon
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-tsushin-slate">{cat.description}</p>
                  </button>
                )
              })}
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={onClose} className="btn-ghost px-4 py-2 text-sm">Cancel</button>
              <button
                type="button"
                disabled={!category}
                onClick={() => setStep(2)}
                className={`btn-primary px-4 py-2 text-sm ${!category ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 2 && category && (
          <div className="space-y-4">
            <p className="text-sm text-tsushin-slate">
              Choose the service to connect. Services already configured for this tenant are badged — you can
              still add another instance (e.g. a second Google Calendar account) by selecting again.
            </p>
            {categoryServices.length === 0 ? (
              <div className="text-sm text-tsushin-slate bg-tsushin-slate/5 border border-tsushin-slate/20 rounded px-3 py-4">
                No services registered for this category yet.
              </div>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {categoryServices.map(svc => {
                  const selected = selectedServiceId === svc.id
                  return (
                    <button
                      key={svc.id}
                      type="button"
                      onClick={() => setSelectedServiceId(svc.id)}
                      className={`text-left p-4 rounded-xl border transition-all ${
                        selected
                          ? 'bg-tsushin-accent/10 border-tsushin-accent/50'
                          : 'bg-tsushin-slate/5 border-tsushin-slate/20 hover:bg-tsushin-slate/10'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-white">{svc.name}</span>
                        {svc.tenant_has_configured && (
                          <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                            Already connected
                          </span>
                        )}
                        {svc.status === 'beta' && (
                          <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-sky-500/15 text-sky-400 border border-sky-500/30">
                            Beta
                          </span>
                        )}
                      </div>
                      {svc.description && <p className="text-xs text-tsushin-slate">{svc.description}</p>}
                      {svc.requires_oauth && (
                        <p className="text-[10px] text-tsushin-slate/70 mt-2">
                          {svc.oauth_provider === 'google' && !svc.tenant_has_oauth_credentials
                            ? 'Requires Google OAuth credentials — you will be guided through the upload.'
                            : 'OAuth consent required.'}
                        </p>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
            <div className="flex justify-between gap-2">
              <button type="button" onClick={() => setStep(1)} className="btn-ghost px-4 py-2 text-sm">
                Back
              </button>
              <div className="flex gap-2">
                <button type="button" onClick={onClose} className="btn-ghost px-4 py-2 text-sm">Cancel</button>
                <button
                  type="button"
                  disabled={!selectedServiceId}
                  onClick={handleContinue}
                  className={`btn-primary px-4 py-2 text-sm ${!selectedServiceId ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  Continue to Connect
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
