'use client'

import React, { useState, useMemo } from 'react'

interface RegexTesterProps {
  pattern: string
  placeholder?: string
}

interface MatchResult {
  fullMatch: string
  groups: string[]
  index: number
}

export function RegexTester({ pattern, placeholder = 'Enter test text...' }: RegexTesterProps) {
  const [testInput, setTestInput] = useState('')
  const [isExpanded, setIsExpanded] = useState(false)

  const matchResult = useMemo((): { matches: MatchResult[], error: string | null } => {
    if (!pattern || !testInput) {
      return { matches: [], error: null }
    }

    try {
      const regex = new RegExp(pattern, 'g')
      const matches: MatchResult[] = []
      let match

      while ((match = regex.exec(testInput)) !== null) {
        matches.push({
          fullMatch: match[0],
          groups: match.slice(1),
          index: match.index
        })
        // Prevent infinite loops for zero-length matches
        if (match[0].length === 0) {
          regex.lastIndex++
        }
      }

      return { matches, error: null }
    } catch (e) {
      return { matches: [], error: (e as Error).message }
    }
  }, [pattern, testInput])

  // Highlight matches in the test input
  const highlightedText = useMemo(() => {
    if (!testInput || matchResult.matches.length === 0) {
      return null
    }

    const parts: { text: string; isMatch: boolean; matchIndex?: number }[] = []
    let lastIndex = 0

    matchResult.matches.forEach((match, idx) => {
      // Add non-matching text before this match
      if (match.index > lastIndex) {
        parts.push({ text: testInput.slice(lastIndex, match.index), isMatch: false })
      }
      // Add the match
      parts.push({ text: match.fullMatch, isMatch: true, matchIndex: idx })
      lastIndex = match.index + match.fullMatch.length
    })

    // Add remaining non-matching text
    if (lastIndex < testInput.length) {
      parts.push({ text: testInput.slice(lastIndex), isMatch: false })
    }

    return parts
  }, [testInput, matchResult.matches])

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="text-xs text-teal-400 hover:text-teal-300 flex items-center gap-1 transition-colors"
      >
        <span className={`transform transition-transform ${isExpanded ? 'rotate-90' : ''}`}>▶</span>
        Test Pattern
      </button>

      {isExpanded && (
        <div className="mt-2 p-3 bg-tsushin-dark/30 rounded-lg border border-tsushin-border/50 space-y-3">
          <div>
            <label className="block text-xs text-tsushin-slate mb-1">Test Input</label>
            <input
              type="text"
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
              placeholder={placeholder}
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded text-white text-sm placeholder-tsushin-slate/50 focus:border-teal-500 focus:ring-1 focus:ring-teal-500"
            />
          </div>

          {testInput && (
            <div className="space-y-2">
              {/* Match status */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-tsushin-slate">Result:</span>
                {matchResult.error ? (
                  <span className="text-xs text-red-400">Invalid pattern</span>
                ) : matchResult.matches.length > 0 ? (
                  <span className="text-xs text-green-400">
                    ✓ {matchResult.matches.length} match{matchResult.matches.length > 1 ? 'es' : ''} found
                  </span>
                ) : (
                  <span className="text-xs text-yellow-400">✗ No match</span>
                )}
              </div>

              {/* Highlighted preview */}
              {highlightedText && (
                <div className="text-xs">
                  <span className="text-tsushin-slate">Preview: </span>
                  <span className="font-mono">
                    {highlightedText.map((part, idx) => (
                      <span
                        key={idx}
                        className={part.isMatch ? 'bg-teal-500/30 text-teal-300 px-0.5 rounded' : 'text-white'}
                      >
                        {part.text}
                      </span>
                    ))}
                  </span>
                </div>
              )}

              {/* Captured groups */}
              {matchResult.matches.length > 0 && matchResult.matches.some(m => m.groups.length > 0) && (
                <div className="text-xs">
                  <span className="text-tsushin-slate">Captured Groups:</span>
                  <div className="mt-1 space-y-1">
                    {matchResult.matches.map((match, matchIdx) => (
                      match.groups.length > 0 && (
                        <div key={matchIdx} className="flex gap-2 flex-wrap">
                          {match.groups.map((group, groupIdx) => (
                            <span
                              key={groupIdx}
                              className="px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded font-mono"
                            >
                              ${groupIdx + 1}: {group || '(empty)'}
                            </span>
                          ))}
                        </div>
                      )
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Quick help */}
          <div className="text-xs text-tsushin-slate/70 border-t border-tsushin-border/30 pt-2">
            <span className="font-medium">Quick Reference:</span>
            <span className="ml-2">
              <code className="bg-tsushin-dark/50 px-1 rounded">^</code> start
              <code className="bg-tsushin-dark/50 px-1 rounded ml-2">$</code> end
              <code className="bg-tsushin-dark/50 px-1 rounded ml-2">.*</code> any
              <code className="bg-tsushin-dark/50 px-1 rounded ml-2">\s+</code> whitespace
              <code className="bg-tsushin-dark/50 px-1 rounded ml-2">(.+)</code> capture
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
