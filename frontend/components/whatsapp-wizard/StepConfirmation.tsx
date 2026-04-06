'use client'

import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepConfirmation() {
  const { state, closeWizard } = useWhatsAppWizard()

  const items = [
    {
      label: 'WhatsApp Connected',
      value: state.createdInstance?.phone_number || 'N/A',
      done: !!state.stepsCompleted[2],
    },
    {
      label: 'DM Settings',
      value: state.configuredFilters?.dm_auto_mode
        ? 'Auto-reply ON'
        : state.configuredFilters?.dm_auto_mode === false
        ? 'Auto-reply OFF (DM Trigger contacts only)'
        : 'Not configured',
      done: !!state.stepsCompleted[3],
    },
    {
      label: 'Group Filters',
      value: state.configuredFilters?.group_filters?.length
        ? `${state.configuredFilters.group_filters.length} group(s) selected`
        : 'All groups monitored',
      done: !!state.stepsCompleted[4],
    },
    {
      label: 'Contacts',
      value: state.createdContacts.length > 0
        ? `${state.createdContacts.length} contact(s) added`
        : 'None added (can add later)',
      done: state.createdContacts.length > 0,
    },
    {
      label: 'Agent Bound',
      value: state.boundAgentName || 'Not bound',
      done: !!state.stepsCompleted[6],
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
                  item.done ? 'bg-green-500' : 'bg-tsushin-slate/30'
                }`}
              >
                {item.done ? (
                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <span className="w-2 h-2 rounded-full bg-tsushin-slate/50" />
                )}
              </div>
              <span className="text-sm font-medium text-white">{item.label}</span>
            </div>
            <span className="text-xs text-tsushin-slate">{item.value}</span>
          </div>
        ))}
      </div>

      <div className="bg-teal-500/10 border border-teal-500/20 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-teal-300 mb-2">What's next?</h4>
        <ul className="text-xs text-tsushin-slate space-y-1.5">
          <li>Send a message to {state.createdInstance?.phone_number || 'your WhatsApp number'} to test</li>
          <li>Use the Playground to test agent responses before going live</li>
          <li>Visit the Hub page to fine-tune filters anytime</li>
          <li>Go to Contacts to manage who your agent recognizes</li>
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
