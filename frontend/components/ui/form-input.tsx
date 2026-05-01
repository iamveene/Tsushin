/**
 * Dark mode-compatible form input components
 * Use these instead of raw input/select/textarea elements to ensure consistent dark mode support
 */

import React from 'react'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  helperText?: string
}

interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  helperText?: string
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  helperText?: string
  children: React.ReactNode
}

// Base input classes using tsushin design tokens
const baseInputClasses = 'w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-deep placeholder:text-tsushin-muted focus:ring-2 focus:ring-teal-500/20 focus:border-teal-500 transition-colors'

/**
 * Dark mode-compatible text input
 * @example
 * <Input type="text" label="API Key" placeholder="Enter your API key" />
 */
export function Input({ label, error, helperText, className = '', ...props }: InputProps) {
  const generatedId = React.useId()
  const inputId = props.id ?? (label ? generatedId : undefined)

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium mb-2 text-tsushin-fog">
          {label}
        </label>
      )}
      <input
        {...props}
        id={inputId}
        className={`${baseInputClasses} ${error ? 'border-tsushin-vermilion' : ''} ${className}`}
      />
      {helperText && (
        <p className="text-xs text-tsushin-slate mt-1">{helperText}</p>
      )}
      {error && (
        <p className="text-xs text-tsushin-vermilion mt-1">{error}</p>
      )}
    </div>
  )
}

/**
 * Dark mode-compatible textarea
 * @example
 * <TextArea label="Description" rows={4} />
 */
export function TextArea({ label, error, helperText, className = '', ...props }: TextAreaProps) {
  const generatedId = React.useId()
  const textAreaId = props.id ?? (label ? generatedId : undefined)

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={textAreaId} className="block text-sm font-medium mb-2 text-tsushin-fog">
          {label}
        </label>
      )}
      <textarea
        {...props}
        id={textAreaId}
        className={`${baseInputClasses} ${error ? 'border-tsushin-vermilion' : ''} ${className}`}
      />
      {helperText && (
        <p className="text-xs text-tsushin-slate mt-1">{helperText}</p>
      )}
      {error && (
        <p className="text-xs text-tsushin-vermilion mt-1">{error}</p>
      )}
    </div>
  )
}

/**
 * Dark mode-compatible select dropdown
 * @example
 * <Select label="Provider">
 *   <option value="openai">OpenAI</option>
 *   <option value="anthropic">Anthropic</option>
 * </Select>
 */
export function Select({ label, error, helperText, className = '', children, ...props }: SelectProps) {
  const generatedId = React.useId()
  const selectId = props.id ?? (label ? generatedId : undefined)

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium mb-2 text-tsushin-fog">
          {label}
        </label>
      )}
      <select
        {...props}
        id={selectId}
        className={`${baseInputClasses} ${error ? 'border-tsushin-vermilion' : ''} ${className}`}
      >
        {children}
      </select>
      {helperText && (
        <p className="text-xs text-tsushin-slate mt-1">{helperText}</p>
      )}
      {error && (
        <p className="text-xs text-tsushin-vermilion mt-1">{error}</p>
      )}
    </div>
  )
}
