'use client'

import { useState, useCallback } from 'react'
import { api } from '@/lib/client'
import { TypeaheadChipInput, TypeaheadSuggestion } from '@/components/hub/TypeaheadChipInput'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import InfoTooltip from '@/components/ui/InfoTooltip'
import ToggleSwitch from '@/components/ui/ToggleSwitch'

export default function StepDmConfig() {
  const { state, setFiltersData, markStepComplete, nextStep } = useWhatsAppWizard()

  const [dmAutoMode, setDmAutoMode] = useState(state.createdInstance?.dm_auto_mode ?? true)
  const [numberFilters, setNumberFilters] = useState<string[]>(state.createdInstance?.number_filters ?? [])
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const instanceId = state.createdInstanceId

  const handleSearchContacts = useCallback(async (query: string): Promise<TypeaheadSuggestion[]> => {
    if (!instanceId) return []
    const res = await api.searchWhatsAppContacts(instanceId, query, 20)
    return (res.contacts || []).map((c) => {
      const phoneStr = c.phone.startsWith('+') ? c.phone : `+${c.phone}`
      return { value: phoneStr, label: c.name || phoneStr, sublabel: c.name ? phoneStr : undefined }
    })
  }, [instanceId])

  const handleSave = async () => {
    if (!instanceId) return
    setSaving(true)
    setError(null)
    try {
      await api.updateMCPInstanceFilters(instanceId, {
        dm_auto_mode: dmAutoMode,
        number_filters: numberFilters,
      })
      setFiltersData({ dm_auto_mode: dmAutoMode, number_filters: numberFilters })
      markStepComplete(4)
      nextStep()
    } catch (e: any) {
      setError(e.message || 'Failed to save DM settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <p className="text-tsushin-slate text-sm">
        Control how your agent responds to direct (private) messages on WhatsApp.
      </p>

      {/* DM Auto Mode */}
      <div className="bg-tsushin-deep/50 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-white">Auto-Reply to Everyone</h4>
            <InfoTooltip
              text="When ON, every direct message gets an AI response — good for customer support. When OFF, only contacts with 'DM Trigger' enabled will get responses — good for selective automation."
              position="bottom"
            />
          </div>
          <ToggleSwitch checked={dmAutoMode} onChange={setDmAutoMode} size="md" />
        </div>

        {dmAutoMode ? (
          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3">
            <p className="text-sm text-green-300">
              Your agent will respond to <span className="font-semibold">every</span> direct message. Great for customer support bots.
            </p>
          </div>
        ) : (
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
            <p className="text-sm text-blue-300">
              Your agent will only respond to contacts marked with <span className="font-semibold">DM Trigger</span>. Add these in the Contacts step.
            </p>
            {state.userContact && (
              <p className="text-xs text-blue-300/70 mt-1.5">
                Your own contact already has DM Trigger enabled.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Advanced toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="text-sm text-teal-400 hover:text-teal-300 transition-colors"
      >
        {showAdvanced ? 'Hide advanced options' : 'Show advanced options'}
      </button>

      {/* Number Filters (advanced) */}
      {showAdvanced && (
        <div>
          <label className="block text-sm font-medium text-white mb-1">
            DM Allowlist <span className="text-tsushin-slate font-normal">(optional)</span>
          </label>
          <p className="text-xs text-tsushin-slate mb-2">
            If you add numbers here, <span className="text-white">only</span> these people can DM your agent. Leave empty to allow everyone.
          </p>
          <TypeaheadChipInput
            value={numberFilters}
            onChange={setNumberFilters}
            onSearch={handleSearchContacts}
            placeholder="Type a name or phone (+5500000000001)"
            emptyStateText="No numbers added. All DMs are allowed."
            chipClassName="bg-purple-500/20 border-purple-500/30 text-purple-300"
            chipRemoveClassName="text-purple-400 hover:text-red-400"
            addButtonClassName="bg-purple-600 hover:bg-purple-700"
          />
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={saving || !instanceId}
        className="w-full py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors"
      >
        {saving ? 'Saving...' : 'Save & Continue'}
      </button>
    </div>
  )
}
