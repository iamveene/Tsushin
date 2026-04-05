'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export interface TypeaheadSuggestion {
  /** The value stored on the chip (what gets persisted) */
  value: string
  /** Primary display line in the dropdown */
  label: string
  /** Optional secondary line (e.g., phone number under contact name) */
  sublabel?: string
}

export interface TypeaheadChipInputProps {
  /** Current list of chip values */
  value: string[]
  /** Called when chips are added/removed */
  onChange: (next: string[]) => void
  /**
   * Lookup function. Called on debounced input with the raw query.
   * Should return up to N suggestions ordered by relevance.
   * If it throws or returns [], the input falls back to free-text entry.
   */
  onSearch: (query: string) => Promise<TypeaheadSuggestion[]>
  placeholder?: string
  emptyStateText?: string
  /** Tailwind classes for chip styling, e.g. "bg-teal-500/20 border-teal-500/30 text-teal-300" */
  chipClassName?: string
  /** Tailwind classes for the × button */
  chipRemoveClassName?: string
  /** Tailwind classes for the Add button */
  addButtonClassName?: string
  disabled?: boolean
  /** Minimum query length before searching (default 1) */
  minQueryLength?: number
  /** Debounce in ms (default 250) */
  debounceMs?: number
}

/**
 * Text input with autocomplete dropdown that commits selections as chips.
 * Supports free-text entry when no suggestion matches (so users can pre-configure
 * filters for contacts/groups that aren't yet in the WhatsApp store).
 */
export function TypeaheadChipInput({
  value,
  onChange,
  onSearch,
  placeholder = 'Type to search...',
  emptyStateText,
  chipClassName = 'bg-teal-500/20 border-teal-500/30 text-teal-300',
  chipRemoveClassName = 'text-teal-400 hover:text-red-400',
  addButtonClassName = 'bg-teal-600 hover:bg-teal-700',
  disabled = false,
  minQueryLength = 1,
  debounceMs = 250,
}: TypeaheadChipInputProps) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<TypeaheadSuggestion[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [loading, setLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestIdRef = useRef(0)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (query.trim().length < minQueryLength) {
      setSuggestions([])
      setActiveIndex(-1)
      return
    }
    debounceRef.current = setTimeout(async () => {
      const myRequestId = ++requestIdRef.current
      setLoading(true)
      try {
        const results = await onSearch(query.trim())
        // Ignore stale responses and unmounted state updates
        if (!mountedRef.current || myRequestId !== requestIdRef.current) return
        // Filter out suggestions whose value is already a chip
        const existing = new Set(value)
        setSuggestions(results.filter((s) => !existing.has(s.value)))
        setActiveIndex(-1)
      } catch {
        if (!mountedRef.current || myRequestId !== requestIdRef.current) return
        setSuggestions([])
      } finally {
        if (mountedRef.current && myRequestId === requestIdRef.current) setLoading(false)
      }
    }, debounceMs)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, onSearch, debounceMs, minQueryLength, value])

  const commitChip = useCallback(
    (raw: string) => {
      const trimmed = raw.trim()
      if (!trimmed) return
      if (value.includes(trimmed)) {
        setQuery('')
        setIsOpen(false)
        return
      }
      onChange([...value, trimmed])
      setQuery('')
      setSuggestions([])
      setActiveIndex(-1)
      setIsOpen(false)
    },
    [value, onChange]
  )

  const removeChip = useCallback(
    (chip: string) => {
      onChange(value.filter((v) => v !== chip))
    },
    [value, onChange]
  )

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      if (suggestions.length === 0) return
      e.preventDefault()
      setIsOpen(true)
      setActiveIndex((prev) => (prev + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      if (suggestions.length === 0) return
      e.preventDefault()
      setIsOpen(true)
      setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (isOpen && activeIndex >= 0 && suggestions[activeIndex]) {
        commitChip(suggestions[activeIndex].value)
      } else {
        commitChip(query)
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false)
    } else if (e.key === 'Backspace' && query === '' && value.length > 0) {
      removeChip(value[value.length - 1])
    }
  }

  const hasDropdown = isOpen && (loading || suggestions.length > 0)

  return (
    <div ref={containerRef}>
      <div className="flex gap-2 mb-2 relative">
        <div className="flex-1 relative">
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setIsOpen(true)
            }}
            onFocus={() => {
              if (query.trim().length >= minQueryLength) setIsOpen(true)
            }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            className="w-full bg-tsushin-deep border border-tsushin-slate/30 rounded px-3 py-2 text-white text-sm focus:outline-none focus:ring-1 focus:ring-teal-500/50 disabled:opacity-50"
            autoComplete="off"
          />
          {hasDropdown && (
            <div
              className="absolute z-50 top-full left-0 right-0 mt-1 bg-tsushin-deep border border-tsushin-slate/30 rounded shadow-lg max-h-64 overflow-y-auto"
              role="listbox"
            >
              {loading && suggestions.length === 0 && (
                <div className="px-3 py-2 text-xs text-tsushin-slate italic">Searching…</div>
              )}
              {suggestions.map((s, idx) => (
                <button
                  key={`${s.value}-${idx}`}
                  type="button"
                  role="option"
                  aria-selected={idx === activeIndex}
                  onClick={() => commitChip(s.value)}
                  onMouseEnter={() => setActiveIndex(idx)}
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-tsushin-slate/10 ${
                    idx === activeIndex ? 'bg-tsushin-slate/10' : ''
                  }`}
                >
                  <div className="text-white truncate">{s.label}</div>
                  {s.sublabel && (
                    <div className="text-xs text-tsushin-slate truncate">{s.sublabel}</div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => commitChip(query)}
          disabled={disabled || query.trim() === ''}
          className={`px-4 py-2 text-white rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed ${addButtonClassName}`}
        >
          Add
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {value.length === 0 ? (
          emptyStateText ? (
            <p className="text-xs text-tsushin-slate italic">{emptyStateText}</p>
          ) : null
        ) : (
          value.map((chip) => (
            <span
              key={chip}
              className={`inline-flex items-center gap-1 px-2 py-1 border rounded text-xs ${chipClassName}`}
            >
              {chip}
              <button
                type="button"
                onClick={() => removeChip(chip)}
                className={chipRemoveClassName}
                aria-label={`Remove ${chip}`}
              >
                ×
              </button>
            </span>
          ))
        )}
      </div>
    </div>
  )
}

export default TypeaheadChipInput
