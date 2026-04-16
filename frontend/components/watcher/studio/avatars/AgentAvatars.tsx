'use client'

import { memo } from 'react'

export interface AvatarDef {
  slug: string
  label: string
  svg: JSX.Element
  color: string
}

const svgProps = { fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor', strokeWidth: 1.5 }

export const AGENT_AVATARS: AvatarDef[] = [
  {
    slug: 'samurai', label: 'Samurai', color: 'bg-red-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-red-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 2L3 7v2h18V7L12 2zM4 11v2c0 4.418 3.582 8 8 8s8-3.582 8-8v-2H4z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 14h.01M15 14h.01M10 17h4" />
    </svg>,
  },
  {
    slug: 'ninja', label: 'Ninja', color: 'bg-purple-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-purple-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5c-4.142 0-7.5 3.358-7.5 7.5 0 2.485 1.208 4.689 3.068 6.053M12 4.5c4.142 0 7.5 3.358 7.5 7.5 0 2.485-1.208 4.689-3.068 6.053" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 12h18M9 12v0M15 12v0" />
      <circle cx="9" cy="10" r="1" fill="currentColor" />
      <circle cx="15" cy="10" r="1" fill="currentColor" />
    </svg>,
  },
  {
    slug: 'sensei', label: 'Sensei', color: 'bg-amber-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-amber-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c-2.5 0-5 1.5-5 4.5S9.5 12 12 12s5-1.5 5-4.5S14.5 3 12 3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 12c-2 1-4 3-4 5.5S5 21 7 21h10c2 0 4-1 4-3.5S19 13 17 12" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 9h4M12 15v3" />
    </svg>,
  },
  {
    slug: 'kitsune', label: 'Kitsune', color: 'bg-orange-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-orange-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 20l4-16 4 8 4-8 4 16" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 14l3 2 3-2" />
      <circle cx="10" cy="11" r="0.5" fill="currentColor" />
      <circle cx="14" cy="11" r="0.5" fill="currentColor" />
    </svg>,
  },
  {
    slug: 'oni', label: 'Oni', color: 'bg-red-600/20',
    svg: <svg {...svgProps} className="w-full h-full text-red-500">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 2l-1 4M16 2l1 4M5 8c0-1 1-2 3-2h8c2 0 3 1 3 2v4c0 4-2.5 8-7 8s-7-4-7-8V8z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h.01M15 12h.01M10 16c.667.667 1.333 1 2 1s1.333-.333 2-1" />
    </svg>,
  },
  {
    slug: 'torii', label: 'Torii Gate', color: 'bg-red-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-red-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 6h18M5 6v15M19 6v15M3 10h18M7 6V3M17 6V3" />
    </svg>,
  },
  {
    slug: 'katana', label: 'Katana', color: 'bg-slate-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-slate-300">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 20L20 4M4 20l2-2M6 18l-2-2M18 6l2-2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 9.5l-5 5" />
      <circle cx="16" cy="8" r="1" />
    </svg>,
  },
  {
    slug: 'sakura', label: 'Sakura', color: 'bg-pink-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-pink-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c1 2 1 4 0 6-1-2-1-4 0-6zM6 8c2 0.5 3.5 2 3.5 4-2-0.5-3.5-2-3.5-4zM18 8c-2 0.5-3.5 2-3.5 4 2-0.5 3.5-2 3.5-4z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 16c1.5-1.5 3-2 4.5-2 1.5 0 3 0.5 4.5 2M12 12v9" />
      <circle cx="12" cy="12" r="2" fill="currentColor" opacity="0.3" />
    </svg>,
  },
  {
    slug: 'crane', label: 'Crane', color: 'bg-sky-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-sky-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l6-6v4h6V6l6 6-6 6v-4H9v4L3 12z" />
    </svg>,
  },
  {
    slug: 'wave', label: 'Great Wave', color: 'bg-cyan-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-cyan-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 15c2.5-3 5-4 7.5-2s5 1 7.5-2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 19c2.5-3 5-4 7.5-2s5 1 7.5-2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 11c2.5-3 5-4 7.5-2s5 1 7.5-2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 7c1-2 3-4 6-4s5 2 6 4" />
    </svg>,
  },
  {
    slug: 'dragon', label: 'Dragon', color: 'bg-emerald-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-emerald-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c-2 0-4 2-4 5 0 2 1 3.5 2.5 4.5L8 17l-3 3h14l-3-3-2.5-4.5C15 11.5 16 10 16 8c0-3-2-5-4-5z" />
      <circle cx="10" cy="7" r="0.5" fill="currentColor" />
      <circle cx="14" cy="7" r="0.5" fill="currentColor" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M11 10h2" />
    </svg>,
  },
  {
    slug: 'robot', label: 'Robot', color: 'bg-blue-500/20',
    svg: <svg {...svgProps} className="w-full h-full text-blue-400">
      <rect x="6" y="7" width="12" height="10" rx="2" strokeWidth="1.5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v4M9 12h.01M15 12h.01M10 15h4M4 12H2M22 12h-2" />
      <circle cx="12" cy="3" r="1" />
    </svg>,
  },
  {
    slug: 'shield', label: 'Shield', color: 'bg-emerald-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-emerald-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>,
  },
  {
    slug: 'lightning', label: 'Lightning', color: 'bg-yellow-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-yellow-400">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
    </svg>,
  },
  {
    slug: 'zen', label: 'Zen', color: 'bg-teal-400/20',
    svg: <svg {...svgProps} className="w-full h-full text-teal-400">
      <circle cx="12" cy="12" r="9" strokeWidth="1.5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c0 5-4 9-9 9M12 3c0 5 4 9 9 9" />
    </svg>,
  },
]

export function getAvatarBySlug(slug: string | null | undefined): AvatarDef | null {
  if (!slug) return null
  return AGENT_AVATARS.find(a => a.slug === slug) || null
}

interface AgentAvatarIconProps {
  slug: string | null | undefined
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizeMap = { sm: 'w-5 h-5', md: 'w-6 h-6', lg: 'w-8 h-8' }
const containerMap = { sm: 'w-8 h-8', md: 'w-10 h-10', lg: 'w-12 h-12' }

function AgentAvatarIconInner({ slug, size = 'md', className = '' }: AgentAvatarIconProps) {
  const avatar = getAvatarBySlug(slug)

  if (avatar) {
    return (
      <div className={`${containerMap[size]} rounded-lg ${avatar.color} flex items-center justify-center flex-shrink-0 p-1.5 ${className}`}>
        {avatar.svg}
      </div>
    )
  }

  // Default flask/beaker icon
  return (
    <div className={`${containerMap[size]} rounded-lg bg-tsushin-indigo/20 flex items-center justify-center flex-shrink-0 ${className}`}>
      <svg className={`${sizeMap[size]} text-tsushin-indigo`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
      </svg>
    </div>
  )
}

export const AgentAvatarIcon = memo(AgentAvatarIconInner)
