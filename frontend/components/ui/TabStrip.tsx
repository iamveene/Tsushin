'use client'

import { ReactNode } from 'react'

interface TabStripProps {
  /** Tab items (Links, buttons, etc.). Each child must include `whitespace-nowrap` and `flex-shrink-0` for the overflow behaviour to work. */
  children: ReactNode
  /** Optional wrapper className for outer container styling (border, glass card, etc.). */
  className?: string
  /** Optional inner nav className (e.g. extra spacing). */
  navClassName?: string
  /** ARIA label for the tab group. */
  ariaLabel?: string
}

/**
 * Single source of truth for horizontal page-level tab strips.
 *
 * Why this exists: hand-rolled `<nav className="flex">` strips get clipped on
 * narrow viewports / when tab count grows. This component wraps a flex nav
 * inside an `overflow-x-auto` container with `min-w-max` so tabs scroll
 * horizontally instead of being cut off. All page tab strips should use this
 * — do not hand-roll new ones.
 *
 * Each child should declare `whitespace-nowrap flex-shrink-0` so a single tab
 * never collapses or wraps mid-label.
 */
export default function TabStrip({
  children,
  className = '',
  navClassName = '',
  ariaLabel,
}: TabStripProps) {
  return (
    <div className={`overflow-x-auto overflow-y-hidden ${className}`}>
      <nav
        className={`flex min-w-max ${navClassName}`}
        aria-label={ariaLabel}
      >
        {children}
      </nav>
    </div>
  )
}
