'use client'

import type { BuilderPersonaData } from '../types'

interface PersonaInfoPanelProps {
  data: BuilderPersonaData
}

export default function PersonaInfoPanel({ data }: PersonaInfoPanelProps) {
  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Name</label>
        <p className="text-sm text-white">{data.name}</p>
      </div>

      {data.role && (
        <div className="config-field">
          <label>Role</label>
          <p className="text-sm text-tsushin-slate">{data.role}</p>
        </div>
      )}

      {data.personalityTraits && (
        <div className="config-field">
          <label>Personality Traits</label>
          <p className="text-sm text-tsushin-slate">{data.personalityTraits}</p>
        </div>
      )}

      <div className="config-field">
        <label>Status</label>
        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${data.isActive ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-400'}`}>
          {data.isActive ? 'Active' : 'Inactive'}
        </span>
      </div>

      <div className="border-t border-tsushin-border pt-3">
        <a
          href="/agents?tab=personas"
          className="inline-flex items-center gap-1.5 text-xs text-tsushin-indigo hover:text-tsushin-indigo/80 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
          </svg>
          Edit in Personas
        </a>
      </div>
    </div>
  )
}
