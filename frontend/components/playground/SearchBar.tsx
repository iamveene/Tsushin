'use client'

/**
 * Phase 14.5: Search Bar Component
 * Full-text and semantic search for playground conversations
 */

import React, { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/client'

interface SearchBarProps {
  onSearch: (query: string, mode: 'full_text' | 'semantic' | 'combined', filters: any) => void
  onClose: () => void
  collapsed?: boolean
  onExpand?: () => void
  currentQuery?: string
  currentMode?: 'full_text' | 'semantic' | 'combined'
  resultCount?: number
}

export default function SearchBar({
  onSearch,
  onClose,
  collapsed = false,
  onExpand,
  currentQuery = '',
  currentMode = 'full_text',
  resultCount = 0
}: SearchBarProps) {
  const [query, setQuery] = useState(currentQuery)
  const [mode, setMode] = useState<'full_text' | 'semantic' | 'combined'>(currentMode)
  const [showFilters, setShowFilters] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)

  // Filters
  const [agentId, setAgentId] = useState<number | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Sync with props when expanding from collapsed state
  useEffect(() => {
    if (!collapsed && currentQuery) {
      setQuery(currentQuery)
      setMode(currentMode)
    }
  }, [collapsed, currentQuery, currentMode])

  // Get suggestions as user types
  useEffect(() => {
    if (query.length >= 2) {
      const timer = setTimeout(async () => {
        try {
          const response = await api.getSearchSuggestions(query)
          setSuggestions(response.suggestions || [])
          setShowSuggestions(true)
        } catch (err) {
          console.error('Failed to get suggestions:', err)
        }
      }, 300)
      return () => clearTimeout(timer)
    } else {
      setSuggestions([])
      setShowSuggestions(false)
    }
  }, [query])

  const handleSearch = () => {
    if (!query.trim()) return

    const filters: any = {}
    if (agentId) filters.agent_id = agentId
    if (dateFrom) filters.date_from = dateFrom
    if (dateTo) filters.date_to = dateTo

    onSearch(query, mode, filters)
    setShowSuggestions(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  const selectSuggestion = (suggestion: string) => {
    setQuery(suggestion)
    setShowSuggestions(false)
    inputRef.current?.focus()
  }

  // Collapsed mode - compact bar showing current search
  if (collapsed) {
    return (
      <div className="fixed top-0 inset-x-0 z-[70] flex justify-center pt-4 px-4 pointer-events-none">
        <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow-2xl max-w-2xl w-full pointer-events-auto">
          <div className="p-3 flex items-center gap-3">
            {/* Search Icon */}
            <svg className="w-4 h-4 text-tsushin-slate flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>

            {/* Query Display */}
            <button
              onClick={onExpand}
              className="flex-1 text-left text-white hover:text-tsushin-accent transition-colors truncate"
            >
              <span className="font-medium">&quot;{currentQuery}&quot;</span>
              <span className="text-tsushin-slate text-sm ml-2">
                {resultCount} result{resultCount !== 1 ? 's' : ''} • {currentMode === 'full_text' ? 'Full-text' : currentMode === 'semantic' ? 'Semantic' : 'Combined'}
              </span>
            </button>

            {/* Expand Button */}
            <button
              onClick={onExpand}
              className="text-tsushin-slate hover:text-white transition-colors px-2 py-1 rounded hover:bg-tsushin-deepBlue"
              title="New search"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="text-tsushin-slate hover:text-white transition-colors"
              title="Close search"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-start justify-center pt-20 animate-fade-in">
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg shadow-2xl w-full max-w-2xl mx-4 animate-slide-up">
        {/* Search Input */}
        <div className="p-4 border-b border-tsushin-border">
          <div className="flex items-center gap-3">
            {/* Search Icon */}
            <svg className="w-5 h-5 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>

            {/* Input */}
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search conversations..."
              className="flex-1 bg-transparent text-white placeholder-tsushin-slate outline-none text-lg"
            />

            {/* Mode Toggle */}
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as any)}
              className="bg-tsushin-deepBlue text-tsushin-slate px-3 py-1 rounded text-sm border border-tsushin-border cursor-pointer"
            >
              <option value="full_text">Full-text</option>
              <option value="semantic">Semantic</option>
              <option value="combined">Combined</option>
            </select>

            {/* Filters Button */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`px-3 py-1 rounded text-sm border ${showFilters ? 'bg-tsushin-accent text-white border-tsushin-accent' : 'bg-tsushin-deepBlue text-tsushin-slate border-tsushin-border'}`}
            >
              Filters
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="text-tsushin-slate hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Suggestions */}
          {showSuggestions && suggestions.length > 0 && (
            <div className="mt-3 space-y-1">
              {suggestions.map((suggestion, idx) => (
                <button
                  key={idx}
                  onClick={() => selectSuggestion(suggestion)}
                  className="w-full text-left px-3 py-2 rounded text-sm text-tsushin-slate hover:bg-tsushin-deepBlue hover:text-white transition-colors"
                >
                  <svg className="w-4 h-4 inline mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                  </svg>
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          {/* Keyboard Hints */}
          <div className="mt-3 flex gap-4 text-xs text-tsushin-slate">
            <span><kbd className="px-2 py-1 bg-tsushin-deepBlue rounded">Enter</kbd> to search</span>
            <span><kbd className="px-2 py-1 bg-tsushin-deepBlue rounded">Esc</kbd> to close</span>
          </div>
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <div className="p-4 bg-tsushin-deepBlue/50 border-b border-tsushin-border space-y-3">
            <h3 className="text-sm font-medium text-white mb-3">Advanced Filters</h3>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-tsushin-slate mb-1 block">Date From</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full bg-tsushin-surface border border-tsushin-border rounded px-3 py-2 text-sm text-white"
                />
              </div>

              <div>
                <label className="text-xs text-tsushin-slate mb-1 block">Date To</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-full bg-tsushin-surface border border-tsushin-border rounded px-3 py-2 text-sm text-white"
                />
              </div>
            </div>

            <button
              onClick={() => {
                setAgentId(null)
                setDateFrom('')
                setDateTo('')
              }}
              className="text-xs text-tsushin-accent hover:text-tsushin-accent/80"
            >
              Clear filters
            </button>
          </div>
        )}

        {/* Search Button */}
        <div className="p-4">
          <button
            onClick={handleSearch}
            disabled={!query.trim()}
            className="w-full bg-tsushin-accent text-white px-4 py-3 rounded font-medium hover:bg-tsushin-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            Search
          </button>
        </div>
      </div>
    </div>
  )
}
