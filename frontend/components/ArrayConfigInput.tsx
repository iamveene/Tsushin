'use client'

import { useState } from 'react'

interface ArrayConfigInputProps {
  value: string[]
  onChange: (newValue: string[]) => void
  placeholder?: string
  className?: string
}

export function ArrayConfigInput({
  value,
  onChange,
  placeholder = "Type and press Enter to add",
  className = ""
}: ArrayConfigInputProps) {
  const [inputValue, setInputValue] = useState('')

  const inputClasses = `flex-1 px-3 py-2 border dark:border-gray-700 rounded-md
    text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800
    focus:ring-2 focus:ring-blue-500 focus:border-transparent ${className}`

  const addItem = () => {
    if (inputValue.trim() && !value.includes(inputValue.trim())) {
      onChange([...value, inputValue.trim()])
      setInputValue('')
    }
  }

  const removeItem = (index: number) => {
    onChange(value.filter((_, i) => i !== index))
  }

  return (
    <div>
      <div className="flex gap-2 mb-2">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              addItem()
            }
          }}
          className={inputClasses}
          placeholder={placeholder}
        />
        <button
          type="button"
          onClick={addItem}
          className="px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 whitespace-nowrap"
        >
          Add
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {value.map((item: string, idx: number) => (
          <span
            key={idx}
            className="px-3 py-1 bg-blue-100 dark:bg-blue-800/30 text-blue-800 dark:text-blue-200 rounded-full text-sm flex items-center gap-2"
          >
            {item}
            <button
              type="button"
              onClick={() => removeItem(idx)}
              className="text-blue-600 dark:text-blue-300 hover:text-blue-800 dark:hover:text-blue-100 font-bold"
            >
              ×
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}
