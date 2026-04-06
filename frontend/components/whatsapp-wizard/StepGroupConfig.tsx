'use client'

import { useState, useCallback } from 'react'
import { api } from '@/lib/client'
import { TypeaheadChipInput, TypeaheadSuggestion } from '@/components/hub/TypeaheadChipInput'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepGroupConfig() {
  const { state, setFiltersData, markStepComplete, nextStep } = useWhatsAppWizard()

  const [groupFilters, setGroupFilters] = useState<string[]>(state.createdInstance?.group_filters ?? [])
  const [groupKeywords, setGroupKeywords] = useState<string[]>(state.createdInstance?.group_keywords ?? [])
  const [keywordInput, setKeywordInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const instanceId = state.createdInstanceId

  const handleSearchGroups = useCallback(async (query: string): Promise<TypeaheadSuggestion[]> => {
    if (!instanceId) return []
    const res = await api.searchWhatsAppGroups(instanceId, query, 20)
    return (res.groups || []).map((g) => ({ value: g.name, label: g.name, sublabel: g.jid }))
  }, [instanceId])

  const addKeyword = () => {
    const kw = keywordInput.trim()
    if (kw && !groupKeywords.includes(kw)) {
      setGroupKeywords([...groupKeywords, kw])
    }
    setKeywordInput('')
  }

  const removeKeyword = (kw: string) => {
    setGroupKeywords(groupKeywords.filter((k) => k !== kw))
  }

  const handleSave = async () => {
    if (!instanceId) return
    setSaving(true)
    setError(null)
    try {
      await api.updateMCPInstanceFilters(instanceId, {
        group_filters: groupFilters,
        group_keywords: groupKeywords,
      })
      setFiltersData({ group_filters: groupFilters, group_keywords: groupKeywords })
      markStepComplete(4)
      nextStep()
    } catch (e: any) {
      setError(e.message || 'Failed to save group settings')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <p className="text-tsushin-slate text-sm">
        Choose which WhatsApp groups your agent monitors and what triggers a response.
      </p>

      {/* Group Filters */}
      <div>
        <label className="block text-sm font-medium text-white mb-1">
          Group Allowlist <span className="text-tsushin-slate font-normal">(optional)</span>
        </label>
        <p className="text-xs text-tsushin-slate mb-2">
          Add specific groups to monitor. If you leave this empty, the agent listens to <span className="text-white">all</span> groups it's a member of.
        </p>
        <TypeaheadChipInput
          value={groupFilters}
          onChange={setGroupFilters}
          onSearch={handleSearchGroups}
          placeholder="Type to search groups, or enter a name"
          emptyStateText="No groups configured. All groups will be monitored."
          chipClassName="bg-teal-500/20 border-teal-500/30 text-teal-300"
          chipRemoveClassName="text-teal-400 hover:text-red-400"
          addButtonClassName="bg-teal-600 hover:bg-teal-700"
        />
      </div>

      {/* How triggers work */}
      <div className="bg-tsushin-deep/50 rounded-xl p-4 space-y-2">
        <h4 className="text-sm font-semibold text-white">How group messages work</h4>
        <p className="text-xs text-tsushin-slate">
          In groups, your agent responds when:
        </p>
        <ul className="text-xs text-tsushin-slate space-y-1.5 ml-4">
          <li className="flex items-start gap-2">
            <span className="text-teal-400 font-bold mt-0.5">@</span>
            <span>Someone <span className="text-white">@mentions</span> the agent's contact name (always active)</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-amber-400 font-bold mt-0.5">#</span>
            <span>A message contains one of the <span className="text-white">keywords</span> you set below</span>
          </li>
        </ul>
      </div>

      {/* Keywords */}
      <div>
        <label className="block text-sm font-medium text-white mb-1">
          Trigger Keywords <span className="text-tsushin-slate font-normal">(optional)</span>
        </label>
        <p className="text-xs text-tsushin-slate mb-2">
          Words that make the agent respond in a group, besides @mentions. For example: &quot;help&quot;, &quot;support&quot;, &quot;bot&quot;.
        </p>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
            placeholder="Enter a keyword"
            className="flex-1 bg-tsushin-deep border border-tsushin-border rounded-lg px-3 py-2 text-white text-sm placeholder-tsushin-slate/50"
          />
          <button
            onClick={addKeyword}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm transition-colors"
          >
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {groupKeywords.length === 0 ? (
            <p className="text-xs text-tsushin-slate italic">No keywords set. Only @mentions will trigger the agent.</p>
          ) : (
            groupKeywords.map((kw) => (
              <span
                key={kw}
                className="inline-flex items-center gap-1 px-2 py-1 bg-amber-500/20 border border-amber-500/30 rounded text-xs text-amber-300"
              >
                {kw}
                <button onClick={() => removeKeyword(kw)} className="text-amber-400 hover:text-red-400">
                  &times;
                </button>
              </span>
            ))
          )}
        </div>
      </div>

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
