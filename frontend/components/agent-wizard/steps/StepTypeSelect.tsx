'use client'

import { useEffect, type ReactNode } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import type { AgentType } from '@/lib/agent-wizard/reducer'

interface TypeCard {
  id: AgentType
  title: string
  body: string
  icon: ReactNode
}

const cards: TypeCard[] = [
  {
    id: 'text',
    title: 'Text',
    body: 'Chats in text. Answers messages, runs tools, searches the web.',
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    id: 'audio',
    title: 'Audio',
    body: 'Speaks back or transcribes voice notes. Great for WhatsApp voice.',
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 016 0v8.25a3 3 0 01-3 3z" />
      </svg>
    ),
  },
  {
    id: 'hybrid',
    title: 'Hybrid',
    body: 'Does both. Takes voice in, replies with voice or text as needed.',
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12a7.5 7.5 0 0115 0m-15 0a7.5 7.5 0 0015 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.13l1.41-.513M5.106 17.785l1.15-.964m11.49-9.642l1.149-.964M7.501 19.795l.75-1.3m7.5-12.99l.75-1.3m-6.063 16.658l.26-1.477m2.605-14.772l.26-1.477m0 17.726l-.26-1.477M10.698 4.614l-.26-1.477" />
      </svg>
    ),
  },
]

export default function StepTypeSelect() {
  const { state, setType, markStepComplete } = useAgentWizard()

  useEffect(() => {
    markStepComplete('type', state.draft.type !== null)
  }, [state.draft.type, markStepComplete])

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">What kind of agent are you building?</h3>
        <p className="text-sm text-gray-300">Pick a starting point — you can always change skills and voice later.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {cards.map(card => {
          const isSelected = state.draft.type === card.id
          return (
            <button
              key={card.id}
              type="button"
              onClick={() => setType(card.id)}
              className={`text-left p-4 rounded-xl border transition-all ${
                isSelected
                  ? 'border-teal-400 bg-teal-500/10 shadow-[0_0_24px_-8px_rgba(20,184,166,0.5)]'
                  : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${isSelected ? 'bg-teal-500/20 text-teal-300' : 'bg-white/5 text-gray-400'}`}>
                  {card.icon}
                </div>
                {isSelected && (
                  <span className="w-5 h-5 rounded-full bg-teal-500 text-white flex items-center justify-center text-xs">✓</span>
                )}
              </div>
              <div className="text-white font-medium">{card.title}</div>
              <div className="text-xs text-gray-400 mt-1">{card.body}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
