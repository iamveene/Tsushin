'use client'

/**
 * SectionHeader
 *
 * Lightweight typographic header used by the three-section Trigger Overview
 * (Source / Routing / Outputs). Wave 2 of the Triggers ↔ Flows unification.
 *
 * Pure presentational — no behavior, no state. Renders an `<h2>` followed by
 * an optional subtitle paragraph in `text-tsushin-slate`.
 */

interface Props {
  title: string
  subtitle?: string
}

export default function SectionHeader({ title, subtitle }: Props) {
  return (
    <div className="space-y-1">
      <h2 className="text-lg font-semibold text-white">{title}</h2>
      {subtitle && (
        <p className="text-sm text-tsushin-slate">{subtitle}</p>
      )}
    </div>
  )
}
