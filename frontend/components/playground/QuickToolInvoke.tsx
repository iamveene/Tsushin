'use client'

/**
 * QuickToolInvoke - Quick tool invocation popover
 * Allows users to quickly specify arguments and execute tools
 */

import React, { useState, useRef, useEffect } from 'react'

interface ToolCommand {
  template: string
  description: string
  placeholder: string
}

interface ToolInfo {
  id: string
  name: string
  icon: string
  description: string
  commands: ToolCommand[]
}

// Tool definitions with command templates
const TOOL_COMMANDS: Record<string, ToolCommand[]> = {
  nmap: [
    { template: 'nmap -sV {target}', description: 'Version detection scan', placeholder: 'target IP or hostname' },
    { template: 'nmap -sn {target}', description: 'Ping scan (host discovery)', placeholder: 'network range (e.g., 192.168.1.0/24)' },
    { template: 'nmap -A {target}', description: 'Aggressive scan (OS, version, scripts)', placeholder: 'target IP or hostname' },
    { template: 'nmap -p {ports} {target}', description: 'Specific port scan', placeholder: 'ports,target (e.g., 80,443 192.168.1.1)' },
    { template: 'nmap -sS -T4 {target}', description: 'Fast SYN scan', placeholder: 'target IP or hostname' },
  ],
  nuclei: [
    { template: 'nuclei -u {target}', description: 'Scan single URL', placeholder: 'URL (e.g., https://example.com)' },
    { template: 'nuclei -u {target} -t cves/', description: 'CVE templates only', placeholder: 'URL' },
    { template: 'nuclei -u {target} -severity critical,high', description: 'Critical/High severity only', placeholder: 'URL' },
    { template: 'nuclei -u {target} -t exposures/', description: 'Exposure templates', placeholder: 'URL' },
  ],
  katana: [
    { template: 'katana -u {target}', description: 'Crawl single URL', placeholder: 'URL (e.g., https://example.com)' },
    { template: 'katana -u {target} -d 3', description: 'Crawl with depth 3', placeholder: 'URL' },
    { template: 'katana -u {target} -jc', description: 'Extract JavaScript endpoints', placeholder: 'URL' },
    { template: 'katana -u {target} -f url', description: 'Output URLs only', placeholder: 'URL' },
  ],
  httpx: [
    { template: 'httpx -u {target}', description: 'Probe single URL', placeholder: 'URL (e.g., https://example.com)' },
    { template: 'httpx -u {target} -sc -title', description: 'With status code and title', placeholder: 'URL' },
    { template: 'httpx -u {target} -tech-detect', description: 'Technology detection', placeholder: 'URL' },
    { template: 'httpx -u {target} -screenshot', description: 'Take screenshot', placeholder: 'URL' },
  ],
  subfinder: [
    { template: 'subfinder -d {target}', description: 'Find subdomains', placeholder: 'domain (e.g., example.com)' },
    { template: 'subfinder -d {target} -silent', description: 'Silent mode (subdomains only)', placeholder: 'domain' },
    { template: 'subfinder -d {target} -all', description: 'Use all sources', placeholder: 'domain' },
  ],
  python: [
    { template: 'python -c "{code}"', description: 'Run Python code', placeholder: 'Python code' },
    { template: 'python {script}', description: 'Run Python script', placeholder: 'script.py' },
  ],
}

interface QuickToolInvokeProps {
  tool: ToolInfo | null
  onClose: () => void
  onExecute: (command: string) => void
  position?: { x: number; y: number }
}

export default function QuickToolInvoke({ tool, onClose, onExecute, position }: QuickToolInvokeProps) {
  const [selectedCommand, setSelectedCommand] = useState(0)
  const [argument, setArgument] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Get commands for this tool
  const commands = tool ? TOOL_COMMANDS[tool.id] || [] : []

  // Focus input when opened
  useEffect(() => {
    if (tool && inputRef.current) {
      inputRef.current.focus()
    }
  }, [tool])

  // Close on escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onClose])

  if (!tool || commands.length === 0) return null

  const currentCommand = commands[selectedCommand]

  const handleExecute = () => {
    // Read from DOM directly to support browser automation
    const inputElement = containerRef.current?.querySelector('input[type="text"]') as HTMLInputElement
    const argValue = inputElement?.value?.trim() || argument.trim()

    if (!argValue) return

    // Build the command by replacing placeholder
    let command = currentCommand.template
    if (command.includes('{target}')) {
      command = command.replace('{target}', argValue)
    } else if (command.includes('{code}')) {
      command = command.replace('{code}', argValue)
    } else if (command.includes('{script}')) {
      command = command.replace('{script}', argValue)
    } else if (command.includes('{ports}')) {
      // For port scan, expect "ports target" format
      const parts = argValue.split(/\s+/)
      if (parts.length >= 2) {
        command = command.replace('{ports}', parts[0]).replace('{target}', parts.slice(1).join(' '))
      } else {
        command = command.replace('{ports} {target}', argValue)
      }
    }

    onExecute(command)
    setArgument('')
    if (inputElement) inputElement.value = ''
    onClose()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleExecute()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedCommand(prev => Math.max(0, prev - 1))
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedCommand(prev => Math.min(commands.length - 1, prev + 1))
    }
  }

  return (
    <div
      ref={containerRef}
      className="quick-tool-invoke"
      style={position ? {
        position: 'absolute',
        left: position.x,
        top: position.y,
      } : undefined}
    >
      {/* Header */}
      <div className="quick-tool-header">
        <div className="flex items-center gap-2">
          <span className="text-lg">{tool.icon}</span>
          <div>
            <h3 className="font-semibold text-[var(--pg-text)]">{tool.name}</h3>
            <p className="text-xs text-[var(--pg-text-muted)]">{tool.description}</p>
          </div>
        </div>
        <button onClick={onClose} className="btn-icon text-[var(--pg-text-muted)] hover:text-[var(--pg-text)]">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Command Templates */}
      <div className="quick-tool-commands">
        <label className="text-xs text-[var(--pg-text-secondary)] mb-1 block">Command Template</label>
        <div className="space-y-1">
          {commands.map((cmd, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedCommand(idx)}
              className={`quick-tool-command ${selectedCommand === idx ? 'active' : ''}`}
            >
              <code className="text-xs text-[var(--pg-accent)] font-mono">{cmd.template.replace(/{[^}]+}/g, '...')}</code>
              <span className="text-xs text-[var(--pg-text-muted)]">{cmd.description}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Argument Input */}
      <div className="quick-tool-input">
        <label className="text-xs text-[var(--pg-text-secondary)] mb-1 block">
          {currentCommand.placeholder.charAt(0).toUpperCase() + currentCommand.placeholder.slice(1)}
        </label>
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            defaultValue={argument}
            onChange={(e) => setArgument(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={currentCommand.placeholder}
            className="quick-tool-text-input"
          />
          <button
            onClick={handleExecute}
            className="quick-tool-execute-btn"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 9l3 3m0 0l-3 3m3-3H8m13 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Execute
          </button>
        </div>
        <p className="text-[10px] text-[var(--pg-text-muted)] mt-1">
          Press <kbd className="px-1 py-0.5 bg-[var(--pg-surface)] rounded text-[var(--pg-text-secondary)]">Enter</kbd> to execute •
          <kbd className="px-1 py-0.5 bg-[var(--pg-surface)] rounded text-[var(--pg-text-secondary)] ml-1">↑↓</kbd> to change command
        </p>
      </div>

      {/* Preview */}
      <div className="quick-tool-preview">
        <label className="text-xs text-[var(--pg-text-secondary)] mb-1 block">Command Preview</label>
        <code className="block text-xs font-mono p-2 bg-[var(--pg-void)] rounded border border-[var(--pg-border)] text-[var(--pg-text-secondary)] overflow-x-auto">
          {argument.trim()
            ? currentCommand.template.replace(/{[^}]+}/g, argument.trim())
            : currentCommand.template
          }
        </code>
      </div>
    </div>
  )
}
