'use client'

import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepConfirmation() {
  const { state, closeWizard } = useWhatsAppWizard()

  const items = [
    {
      label: 'WhatsApp Instance',
      value: state.instanceDisplayName
        ? `${state.instanceDisplayName} (${state.createdInstance?.phone_number})`
        : state.createdInstance?.phone_number || 'N/A',
      done: !!state.stepsCompleted[2],
    },
    {
      label: 'Bot Contact',
      value: state.botContact
        ? state.botContact.friendly_name
        : 'Skipped',
      done: !!state.botContact,
    },
    {
      label: 'Your Contact',
      value: state.userContact
        ? `${state.userContact.friendly_name} (${state.userContact.phone_number})`
        : 'Skipped',
      done: !!state.userContact,
    },
    {
      label: 'DM Mode',
      value: state.configuredFilters?.dm_auto_mode
        ? 'Auto-reply to everyone'
        : state.configuredFilters?.dm_auto_mode === false
        ? 'Contacts only'
        : 'Not configured',
      done: !!state.stepsCompleted[4],
    },
    {
      label: 'Group Filters',
      value: state.configuredFilters?.group_filters?.length
        ? `${state.configuredFilters.group_filters.length} group(s) selected`
        : 'All groups monitored',
      done: !!state.stepsCompleted[5],
    },
    {
      label: 'Additional Contacts',
      value: (() => {
        const wizardIds = new Set<number>()
        if (state.botContact) wizardIds.add(state.botContact.id)
        if (state.userContact) wizardIds.add(state.userContact.id)
        const manual = state.createdContacts.filter((c) => !wizardIds.has(c.id))
        return manual.length > 0
          ? `${manual.length} contact(s) added`
          : 'None added (can add later)'
      })(),
      done: (() => {
        const wizardIds = new Set<number>()
        if (state.botContact) wizardIds.add(state.botContact.id)
        if (state.userContact) wizardIds.add(state.userContact.id)
        return state.createdContacts.filter((c) => !wizardIds.has(c.id)).length > 0
      })(),
    },
    {
      label: 'Agent',
      value: state.boundAgentName || 'Not bound',
      done: !!state.stepsCompleted[7],
    },
  ]

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 bg-green-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h3 className="text-xl font-bold text-white mb-2">Setup Complete!</h3>
        <p className="text-tsushin-slate max-w-sm mx-auto">
          Your WhatsApp integration is ready. Here's a summary of what was configured:
        </p>
      </div>

      <div className="bg-tsushin-deep/50 rounded-xl divide-y divide-tsushin-border">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-3">
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
                  item.done ? 'bg-green-500' : 'bg-amber-500/30'
                }`}
              >
                {item.done ? (
                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                )}
              </div>
              <span className="text-sm font-medium text-white">{item.label}</span>
            </div>
            <span className={`text-xs ${item.done ? 'text-tsushin-slate' : 'text-amber-400'}`}>{item.value}</span>
          </div>
        ))}
      </div>

      <div className="bg-teal-500/10 border border-teal-500/20 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-teal-300 mb-2">What's next?</h4>
        <ul className="text-xs text-tsushin-slate space-y-1.5">
          <li>Send a message to {state.createdInstance?.phone_number || 'your WhatsApp number'} to test</li>
          <li>Use the <span className="text-white font-medium">Playground</span> to test agent responses before going live</li>
          <li>Visit the <span className="text-white font-medium">Hub</span> page to fine-tune filters anytime</li>
          <li>Go to <span className="text-white font-medium">Contacts</span> to manage who your agent recognizes</li>
        </ul>
      </div>

      <button
        onClick={closeWizard}
        className="w-full py-3 bg-gradient-to-r from-teal-500 to-cyan-500 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-600 transition-all"
      >
        Done — Go to Hub
      </button>
    </div>
  )
}
