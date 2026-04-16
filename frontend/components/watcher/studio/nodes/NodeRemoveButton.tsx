'use client'

import { memo, useCallback } from 'react'

interface NodeRemoveButtonProps {
  onDetach: () => void
  label: string
}

function NodeRemoveButton({ onDetach, label }: NodeRemoveButtonProps) {
  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    e.preventDefault()
    onDetach()
  }, [onDetach])

  return (
    <button
      type="button"
      onClick={handleClick}
      className="nodrag nopan node-remove-btn absolute -top-2 -right-2 w-5 h-5 rounded-full bg-tsushin-surface border border-tsushin-border flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/30 hover:border-red-400/60 hover:text-red-400 text-tsushin-muted z-10"
      aria-label={label}
      title="Remove"
    >
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  )
}

export default memo(NodeRemoveButton)
