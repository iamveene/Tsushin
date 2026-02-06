'use client'

/**
 * EmptyState - Reusable illustrated empty state component
 * Premium UI with animated illustrations and call-to-action
 */

import React from 'react'

type EmptyStateVariant =
  | 'no-agents'
  | 'no-flows'
  | 'no-conversations'
  | 'no-results'
  | 'no-data'
  | 'error'
  | 'welcome'
  | 'coming-soon'

interface EmptyStateProps {
  variant?: EmptyStateVariant
  title?: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  className?: string
}

// SVG illustrations for each variant
const illustrations: Record<EmptyStateVariant, React.ReactNode> = {
  'no-agents': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Robot body */}
      <rect x="60" y="80" width="80" height="90" rx="12" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Robot head */}
      <rect x="70" y="40" width="60" height="50" rx="8" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Antenna */}
      <line x1="100" y1="40" x2="100" y2="25" className="stroke-tsushin-indigo" strokeWidth="3" strokeLinecap="round" />
      <circle cx="100" cy="20" r="6" className="fill-tsushin-indigo animate-pulse" />
      {/* Eyes */}
      <circle cx="85" cy="60" r="8" className="fill-tsushin-indigo/20 stroke-tsushin-indigo" strokeWidth="2" />
      <circle cx="115" cy="60" r="8" className="fill-tsushin-indigo/20 stroke-tsushin-indigo" strokeWidth="2" />
      <circle cx="85" cy="60" r="3" className="fill-tsushin-indigo" />
      <circle cx="115" cy="60" r="3" className="fill-tsushin-indigo" />
      {/* Mouth */}
      <path d="M85 75 Q100 85 115 75" className="stroke-tsushin-muted" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* Chest panel */}
      <rect x="80" y="100" width="40" height="30" rx="4" className="fill-tsushin-deep stroke-tsushin-border" strokeWidth="1" />
      <circle cx="90" cy="110" r="4" className="fill-tsushin-success animate-pulse" />
      <circle cx="100" cy="110" r="4" className="fill-tsushin-warning" />
      <circle cx="110" cy="110" r="4" className="fill-tsushin-vermilion/50" />
      {/* Arms */}
      <rect x="35" y="90" width="20" height="60" rx="6" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <rect x="145" y="90" width="20" height="60" rx="6" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Question marks */}
      <text x="30" y="60" className="fill-tsushin-muted text-2xl font-bold animate-bounce-soft">?</text>
      <text x="160" y="70" className="fill-tsushin-muted text-xl font-bold animate-bounce-soft" style={{ animationDelay: '0.3s' }}>?</text>
    </svg>
  ),

  'no-flows': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Flow nodes */}
      <rect x="80" y="20" width="40" height="30" rx="6" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <rect x="30" y="85" width="40" height="30" rx="6" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <rect x="130" y="85" width="40" height="30" rx="6" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <rect x="80" y="150" width="40" height="30" rx="6" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Connecting lines (dashed - not connected) */}
      <path d="M100 50 L50 85" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="5 5" />
      <path d="M100 50 L150 85" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="5 5" />
      <path d="M50 115 L100 150" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="5 5" />
      <path d="M150 115 L100 150" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="5 5" />
      {/* Icons in nodes */}
      <circle cx="100" cy="35" r="6" className="fill-tsushin-indigo" />
      <circle cx="50" cy="100" r="6" className="fill-tsushin-warning" />
      <circle cx="150" cy="100" r="6" className="fill-tsushin-accent" />
      <circle cx="100" cy="165" r="6" className="fill-tsushin-success" />
      {/* Plus icon */}
      <circle cx="100" cy="100" r="20" className="fill-tsushin-indigo/10 stroke-tsushin-indigo" strokeWidth="2" strokeDasharray="4 4" />
      <line x1="92" y1="100" x2="108" y2="100" className="stroke-tsushin-indigo" strokeWidth="2" strokeLinecap="round" />
      <line x1="100" y1="92" x2="100" y2="108" className="stroke-tsushin-indigo" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),

  'no-conversations': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Chat bubble 1 */}
      <path d="M30 60 Q30 40 50 40 L130 40 Q150 40 150 60 L150 100 Q150 120 130 120 L70 120 L50 140 L50 120 Q30 120 30 100 Z" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Chat bubble 2 */}
      <path d="M50 150 Q50 130 70 130 L150 130 Q170 130 170 150 L170 170 Q170 190 150 190 L90 190 L70 200 L70 190 Q50 190 50 170 Z" className="fill-tsushin-indigo/10 stroke-tsushin-indigo/50" strokeWidth="2" />
      {/* Dots in bubble 1 */}
      <circle cx="70" cy="80" r="6" className="fill-tsushin-muted animate-pulse" />
      <circle cx="90" cy="80" r="6" className="fill-tsushin-muted animate-pulse" style={{ animationDelay: '0.2s' }} />
      <circle cx="110" cy="80" r="6" className="fill-tsushin-muted animate-pulse" style={{ animationDelay: '0.4s' }} />
      {/* Lines in bubble 2 */}
      <line x1="70" y1="150" x2="130" y2="150" className="stroke-tsushin-indigo/30" strokeWidth="3" strokeLinecap="round" />
      <line x1="70" y1="165" x2="110" y2="165" className="stroke-tsushin-indigo/20" strokeWidth="3" strokeLinecap="round" />
    </svg>
  ),

  'no-results': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Magnifying glass */}
      <circle cx="85" cy="85" r="45" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="3" />
      <circle cx="85" cy="85" r="35" className="fill-tsushin-deep stroke-tsushin-muted" strokeWidth="2" />
      <line x1="120" y1="120" x2="160" y2="160" className="stroke-tsushin-muted" strokeWidth="8" strokeLinecap="round" />
      {/* X mark inside */}
      <line x1="70" y1="70" x2="100" y2="100" className="stroke-tsushin-vermilion/50" strokeWidth="3" strokeLinecap="round" />
      <line x1="100" y1="70" x2="70" y2="100" className="stroke-tsushin-vermilion/50" strokeWidth="3" strokeLinecap="round" />
      {/* Sparkles around */}
      <circle cx="150" cy="50" r="3" className="fill-tsushin-indigo/50 animate-pulse" />
      <circle cx="40" cy="140" r="2" className="fill-tsushin-accent/50 animate-pulse" style={{ animationDelay: '0.5s' }} />
      <circle cx="170" cy="100" r="2" className="fill-tsushin-warning/50 animate-pulse" style={{ animationDelay: '1s' }} />
    </svg>
  ),

  'no-data': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Database cylinders */}
      <ellipse cx="100" cy="50" rx="50" ry="15" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <path d="M50 50 L50 150 Q50 165 100 165 Q150 165 150 150 L150 50" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <ellipse cx="100" cy="150" rx="50" ry="15" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Data lines (faded/empty) */}
      <line x1="65" y1="80" x2="135" y2="80" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="4 4" />
      <line x1="65" y1="100" x2="135" y2="100" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="4 4" />
      <line x1="65" y1="120" x2="135" y2="120" className="stroke-tsushin-muted" strokeWidth="2" strokeDasharray="4 4" />
      {/* Empty indicator */}
      <circle cx="100" cy="100" r="20" className="fill-tsushin-deep stroke-tsushin-muted" strokeWidth="2" strokeDasharray="3 3" />
      <text x="94" y="106" className="fill-tsushin-muted text-lg font-bold">0</text>
    </svg>
  ),

  'error': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Warning triangle */}
      <path d="M100 30 L170 150 L30 150 Z" className="fill-tsushin-vermilion/10 stroke-tsushin-vermilion" strokeWidth="3" strokeLinejoin="round" />
      {/* Exclamation mark */}
      <line x1="100" y1="70" x2="100" y2="110" className="stroke-tsushin-vermilion" strokeWidth="6" strokeLinecap="round" />
      <circle cx="100" cy="130" r="5" className="fill-tsushin-vermilion" />
      {/* Sparks */}
      <path d="M50 100 L40 95 L50 90" className="stroke-tsushin-vermilion/50" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M150 100 L160 95 L150 90" className="stroke-tsushin-vermilion/50" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),

  'welcome': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Sun/Star burst */}
      <circle cx="100" cy="100" r="30" className="fill-tsushin-indigo/20" />
      <circle cx="100" cy="100" r="20" className="fill-gradient-primary" />
      {/* Rays */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, i) => (
        <line
          key={angle}
          x1={100 + 40 * Math.cos(angle * Math.PI / 180)}
          y1={100 + 40 * Math.sin(angle * Math.PI / 180)}
          x2={100 + 60 * Math.cos(angle * Math.PI / 180)}
          y2={100 + 60 * Math.sin(angle * Math.PI / 180)}
          className="stroke-tsushin-indigo/50"
          strokeWidth="3"
          strokeLinecap="round"
          style={{ animation: `pulse-soft 2s ease-in-out infinite`, animationDelay: `${i * 0.1}s` }}
        />
      ))}
      {/* Sparkles */}
      <circle cx="50" cy="50" r="4" className="fill-tsushin-accent animate-pulse" />
      <circle cx="150" cy="60" r="3" className="fill-tsushin-warning animate-pulse" style={{ animationDelay: '0.3s' }} />
      <circle cx="160" cy="140" r="3" className="fill-tsushin-success animate-pulse" style={{ animationDelay: '0.6s' }} />
      <circle cx="40" cy="130" r="4" className="fill-tsushin-indigo animate-pulse" style={{ animationDelay: '0.9s' }} />
    </svg>
  ),

  'coming-soon': (
    <svg className="w-full h-full" viewBox="0 0 200 200" fill="none">
      {/* Rocket */}
      <path d="M100 40 L120 80 L120 140 L100 160 L80 140 L80 80 Z" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Window */}
      <circle cx="100" cy="100" r="15" className="fill-tsushin-indigo/20 stroke-tsushin-indigo" strokeWidth="2" />
      <circle cx="100" cy="100" r="8" className="fill-tsushin-accent/30" />
      {/* Fins */}
      <path d="M80 120 L60 150 L80 140" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      <path d="M120 120 L140 150 L120 140" className="fill-tsushin-surface stroke-tsushin-border" strokeWidth="2" />
      {/* Flames */}
      <path d="M90 160 Q100 180 100 190 Q100 180 110 160" className="fill-tsushin-warning stroke-tsushin-vermilion" strokeWidth="1" />
      <path d="M95 160 Q100 175 100 180 Q100 175 105 160" className="fill-tsushin-vermilion" />
      {/* Stars */}
      <circle cx="40" cy="60" r="2" className="fill-white/50 animate-pulse" />
      <circle cx="160" cy="80" r="2" className="fill-white/50 animate-pulse" style={{ animationDelay: '0.5s' }} />
      <circle cx="50" cy="140" r="1.5" className="fill-white/30 animate-pulse" style={{ animationDelay: '1s' }} />
      <circle cx="150" cy="50" r="1.5" className="fill-white/30 animate-pulse" style={{ animationDelay: '1.5s' }} />
    </svg>
  ),
}

// Default content for each variant
const defaultContent: Record<EmptyStateVariant, { title: string; description: string }> = {
  'no-agents': {
    title: 'No Agents Configured',
    description: 'Create your first AI agent to start automating conversations and workflows.',
  },
  'no-flows': {
    title: 'No Flows Created',
    description: 'Design your first multi-step flow to automate complex conversations.',
  },
  'no-conversations': {
    title: 'No Conversations Yet',
    description: 'Conversations will appear here as your agents interact with users.',
  },
  'no-results': {
    title: 'No Results Found',
    description: 'Try adjusting your search criteria or filters.',
  },
  'no-data': {
    title: 'No Data Available',
    description: 'Data will appear here once activity is recorded.',
  },
  'error': {
    title: 'Something Went Wrong',
    description: 'We encountered an error. Please try again or contact support.',
  },
  'welcome': {
    title: 'Welcome to Tsushin',
    description: 'Your agentic messaging framework is ready. Let\'s get started!',
  },
  'coming-soon': {
    title: 'Coming Soon',
    description: 'This feature is currently under development. Stay tuned!',
  },
}

export default function EmptyState({
  variant = 'no-data',
  title,
  description,
  actionLabel,
  onAction,
  className = '',
}: EmptyStateProps) {
  const content = defaultContent[variant]

  return (
    <div className={`empty-state py-16 ${className}`}>
      {/* Illustration */}
      <div className="w-32 h-32 mb-8 mx-auto animate-float">
        {illustrations[variant]}
      </div>

      {/* Content */}
      <h3 className="text-xl font-display font-semibold text-white mb-2 text-balance">
        {title || content.title}
      </h3>
      <p className="text-tsushin-slate max-w-md mx-auto mb-6 text-balance">
        {description || content.description}
      </p>

      {/* Action button */}
      {actionLabel && onAction && (
        <button onClick={onAction} className="btn-primary">
          {actionLabel}
        </button>
      )}
    </div>
  )
}
