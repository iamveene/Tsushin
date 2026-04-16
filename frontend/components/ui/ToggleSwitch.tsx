'use client'

interface ToggleSwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  size?: 'sm' | 'md' | 'lg'
  title?: string
  activeColor?: string
  inactiveColor?: string
}

const sizes = {
  sm: {
    track: 'h-5 w-9',
    knob: 'h-4 w-4',
    translate: 'translate-x-4',
  },
  md: {
    track: 'h-6 w-11',
    knob: 'h-5 w-5',
    translate: 'translate-x-5',
  },
  lg: {
    track: 'h-7 w-14',
    knob: 'h-6 w-6',
    translate: 'translate-x-7',
  },
}

export default function ToggleSwitch({
  checked,
  onChange,
  disabled = false,
  size = 'sm',
  title,
  activeColor = 'bg-teal-500',
  inactiveColor = 'bg-tsushin-slate/40',
}: ToggleSwitchProps) {
  const s = sizes[size]

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={`relative inline-flex ${s.track} shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
        checked ? activeColor : inactiveColor
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      title={title}
    >
      <span
        className={`pointer-events-none inline-block ${s.knob} transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? s.translate : 'translate-x-0'
        }`}
      />
    </button>
  )
}
