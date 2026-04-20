'use client'

import { useState } from 'react'

type Tone = 'teal' | 'purple' | 'blue' | 'amber' | 'slate'

const TONES: Record<Tone, { body: string; button: string }> = {
  teal: {
    body: 'text-teal-200 border-teal-700/60',
    button: 'bg-teal-600/30 text-teal-200 border-teal-500/40 hover:bg-teal-600/50',
  },
  purple: {
    body: 'text-purple-200 border-gray-700',
    button: 'bg-purple-600/30 text-purple-200 border-purple-500/40 hover:bg-purple-600/50',
  },
  blue: {
    body: 'text-blue-200 border-blue-700/60',
    button: 'bg-blue-600/30 text-blue-200 border-blue-500/40 hover:bg-blue-600/50',
  },
  amber: {
    body: 'text-amber-200 border-amber-700/60',
    button: 'bg-amber-600/30 text-amber-200 border-amber-500/40 hover:bg-amber-600/50',
  },
  slate: {
    body: 'text-slate-200 border-slate-700',
    button: 'bg-slate-600/30 text-slate-200 border-slate-500/40 hover:bg-slate-600/50',
  },
}

interface Props {
  value: string
  label?: string
  tone?: Tone
  maxHeight?: string
}

export default function CopyableBlock({ value, label, tone = 'teal', maxHeight = '12rem' }: Props) {
  const [copied, setCopied] = useState(false)
  const t = TONES[tone]
  return (
    <div className="relative">
      <pre
        className={`bg-gray-900 text-xs font-mono rounded-lg p-3 overflow-x-auto border ${t.body}`}
        style={{ maxHeight }}
      >
        {value}
      </pre>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard?.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        className={`absolute top-2 right-2 px-2 py-1 text-xs border rounded transition-colors ${t.button}`}
      >
        {copied ? 'Copied!' : `Copy${label ? ' ' + label : ''}`}
      </button>
    </div>
  )
}
