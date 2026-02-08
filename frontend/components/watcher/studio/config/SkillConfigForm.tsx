'use client'

import { useState, useEffect, useMemo } from 'react'
import type { BuilderSkillData } from '../types'
import type { SkillDefinition } from '@/lib/client'

interface SkillConfigFormProps {
  nodeId: string
  data: BuilderSkillData
  onUpdate: (nodeType: string, nodeId: string, config: Record<string, unknown>) => void
  skillDefinitions: SkillDefinition[]
}

interface SchemaProperty {
  type: string
  description?: string
  default?: unknown
  enum?: string[]
  items?: { type: string }
  minimum?: number
  maximum?: number
}

export default function SkillConfigForm({ nodeId, data, onUpdate, skillDefinitions }: SkillConfigFormProps) {
  const skillDef = useMemo(
    () => skillDefinitions.find(sd => sd.skill_type === data.skillType),
    [skillDefinitions, data.skillType]
  )

  const schema = skillDef?.config_schema || {}
  const properties = (schema.properties || {}) as Record<string, SchemaProperty>
  const propertyKeys = Object.keys(properties)

  const [config, setConfig] = useState<Record<string, unknown>>(data.config || {})

  useEffect(() => {
    setConfig(data.config || {})
  }, [data.config])

  const handleFieldChange = (key: string, value: unknown) => {
    const next = { ...config, [key]: value }
    setConfig(next)
    onUpdate('builder-skill', nodeId, { skillType: data.skillType, skillConfig: next })
  }

  const renderField = (key: string, prop: SchemaProperty) => {
    const value = config[key] ?? prop.default ?? ''

    // Boolean toggle
    if (prop.type === 'boolean') {
      const checked = !!value
      return (
        <div className="config-field" key={key}>
          <label>{formatLabel(key)}</label>
          <div className="flex items-center gap-3 mt-1">
            <button
              type="button"
              onClick={() => handleFieldChange(key, !checked)}
              className={`config-toggle ${checked ? 'active' : ''}`}
              role="switch"
              aria-checked={checked}
            >
              <span className="config-toggle-thumb" />
            </button>
            <span className="text-xs text-tsushin-slate">{checked ? 'Enabled' : 'Disabled'}</span>
          </div>
          {prop.description && <p className="field-help">{prop.description}</p>}
        </div>
      )
    }

    // String with enum (dropdown)
    if (prop.type === 'string' && prop.enum) {
      return (
        <div className="config-field" key={key}>
          <label>{formatLabel(key)}</label>
          <select
            className="config-select"
            value={(value as string) || ''}
            onChange={e => handleFieldChange(key, e.target.value)}
          >
            {prop.enum.map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
          {prop.description && <p className="field-help">{prop.description}</p>}
        </div>
      )
    }

    // Number / integer
    if (prop.type === 'number' || prop.type === 'integer') {
      return (
        <div className="config-field" key={key}>
          <label>{formatLabel(key)}</label>
          <input
            type="number"
            className="config-input"
            value={value as number || ''}
            min={prop.minimum}
            max={prop.maximum}
            step={prop.type === 'integer' ? 1 : 0.1}
            onChange={e => handleFieldChange(key, prop.type === 'integer' ? parseInt(e.target.value) : parseFloat(e.target.value))}
          />
          {prop.description && <p className="field-help">{prop.description}</p>}
        </div>
      )
    }

    // Array of strings
    if (prop.type === 'array' && prop.items?.type === 'string') {
      const arr = Array.isArray(value) ? value : []
      return (
        <div className="config-field" key={key}>
          <label>{formatLabel(key)}</label>
          <input
            type="text"
            className="config-input"
            value={arr.join(', ')}
            placeholder="Comma-separated values"
            onChange={e => handleFieldChange(key, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
          />
          {prop.description && <p className="field-help">{prop.description}</p>}
        </div>
      )
    }

    // Default: string input
    return (
      <div className="config-field" key={key}>
        <label>{formatLabel(key)}</label>
        <input
          type="text"
          className="config-input"
          value={(value as string) || ''}
          placeholder={prop.default !== undefined ? String(prop.default) : ''}
          onChange={e => handleFieldChange(key, e.target.value)}
        />
        {prop.description && <p className="field-help">{prop.description}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Skill</label>
        <p className="text-sm text-white">{data.skillName}</p>
        {data.category && <p className="field-help">Category: {data.category}</p>}
        {data.providerName && <p className="field-help">Provider: {data.providerName}</p>}
      </div>

      {propertyKeys.length > 0 ? (
        <>
          <div className="border-t border-tsushin-border pt-3">
            <p className="text-xs font-medium text-tsushin-slate uppercase tracking-wide mb-3">Configuration</p>
          </div>
          {propertyKeys.map(key => renderField(key, properties[key]))}
        </>
      ) : (
        <div className="text-xs text-tsushin-muted py-2">
          This skill has no configurable options.
        </div>
      )}
    </div>
  )
}

function formatLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, c => c.toUpperCase())
}
