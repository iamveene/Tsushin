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

// Base input classes for dark mode compatibility
const baseInputClasses = 'w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-transparent'

/**
 * Dark mode-compatible text input
 * @example
 * <Input type="text" label="API Key" placeholder="Enter your API key" />
 */
export function Input({ label, error, helperText, className = '', ...props }: InputProps) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100">
          {label}
        </label>
      )}
      <input
        {...props}
        className={`${baseInputClasses} ${error ? 'border-red-500 dark:border-red-400' : ''} ${className}`}
      />
      {helperText && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{helperText}</p>
      )}
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400 mt-1">{error}</p>
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
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100">
          {label}
        </label>
      )}
      <textarea
        {...props}
        className={`${baseInputClasses} ${error ? 'border-red-500 dark:border-red-400' : ''} ${className}`}
      />
      {helperText && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{helperText}</p>
      )}
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400 mt-1">{error}</p>
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
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium mb-2 text-gray-900 dark:text-gray-100">
          {label}
        </label>
      )}
      <select
        {...props}
        className={`${baseInputClasses} ${error ? 'border-red-500 dark:border-red-400' : ''} ${className}`}
      >
        {children}
      </select>
      {helperText && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{helperText}</p>
      )}
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400 mt-1">{error}</p>
      )}
    </div>
  )
}
