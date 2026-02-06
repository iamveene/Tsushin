/**
 * Usage Limit Card Component
 * Shows current usage vs limits for organization resources
 */

interface UsageLimitCardProps {
  title: string
  current: number
  limit: number
  unit?: string
}

export default function UsageLimitCard({ title, current, limit, unit = '' }: UsageLimitCardProps) {
  const percentage = (current / limit) * 100
  const isNearLimit = percentage >= 80
  const isAtLimit = percentage >= 100

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}:</span>
        <span className="text-sm text-gray-600 dark:text-gray-400">
          {current} / {limit} {unit}
        </span>
      </div>
      <div className="relative w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full transition-all ${
            isAtLimit
              ? 'bg-red-500'
              : isNearLimit
              ? 'bg-yellow-500'
              : 'bg-blue-500 dark:bg-blue-600'
          }`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        />
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400">{percentage.toFixed(0)}% used</div>
    </div>
  )
}
