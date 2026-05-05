'use client'

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDownIcon } from '@/components/ui/icons'

export interface SplitButtonOption {
  id: string
  label: string
  description?: string
  icon?: ReactNode
  disabled?: boolean
  onSelect: () => void
}

interface SplitButtonProps {
  primaryLabel: string
  primaryIcon?: ReactNode
  onPrimaryClick: () => void
  options: SplitButtonOption[]
  disabled?: boolean
  menuLabel?: string
}

export default function SplitButton({
  primaryLabel,
  primaryIcon,
  onPrimaryClick,
  options,
  disabled = false,
  menuLabel = 'Choose create type',
}: SplitButtonProps) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const handleSelect = (option: SplitButtonOption) => {
    if (option.disabled) return
    setOpen(false)
    option.onSelect()
  }

  return (
    <div className="relative inline-flex" ref={menuRef}>
      <button
        type="button"
        onClick={onPrimaryClick}
        disabled={disabled}
        className="btn-primary flex items-center gap-2 rounded-r-none border-r border-white/20"
      >
        {primaryIcon}
        {primaryLabel}
      </button>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        disabled={disabled}
        className="btn-primary rounded-l-none px-2.5"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={menuLabel}
      >
        <ChevronDownIcon size={16} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-2 w-56 overflow-hidden rounded-lg border border-tsushin-border bg-tsushin-surface shadow-2xl"
        >
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              role="menuitem"
              onClick={() => handleSelect(option)}
              disabled={option.disabled}
              className="flex w-full items-start gap-3 px-3.5 py-3 text-left text-sm text-tsushin-pearl transition-colors hover:bg-tsushin-indigo/15 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {option.icon && (
                <span className="mt-0.5 text-tsushin-indigo-glow">{option.icon}</span>
              )}
              <span className="min-w-0">
                <span className="block font-medium">{option.label}</span>
                {option.description && (
                  <span className="mt-0.5 block text-xs leading-5 text-tsushin-slate">
                    {option.description}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
