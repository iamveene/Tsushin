'use client'

import { useId } from 'react'
import { getProviderModelLabels } from '@/lib/provider-models'

interface ProviderModelInputProps {
  vendor?: string | null
  models?: Array<string | null | undefined>
  value: string
  onChange: (value: string) => void
  currentModel?: string | null
  disabled?: boolean
  required?: boolean
  placeholder?: string
  className?: string
  listId?: string
  includeFallbacks?: boolean
  dataTestId?: string
}

export default function ProviderModelInput({
  vendor,
  models = [],
  value,
  onChange,
  currentModel,
  disabled,
  required,
  placeholder = 'Select or type a model ID',
  className = '',
  listId,
  includeFallbacks,
  dataTestId,
}: ProviderModelInputProps) {
  const generatedId = useId()
  const resolvedListId = listId || `provider-models-${generatedId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const options = getProviderModelLabels(vendor, models, {
    currentModel: currentModel ?? value,
    includeFallbacks,
  })

  return (
    <>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        list={resolvedListId}
        disabled={disabled}
        required={required}
        placeholder={placeholder}
        className={className}
        autoComplete="off"
        spellCheck={false}
        data-testid={dataTestId}
      />
      <datalist id={resolvedListId}>
        {options.map(option => (
          <option key={option.value} value={option.value} label={option.label} />
        ))}
      </datalist>
    </>
  )
}
