/**
 * Usage Limit Card Component
 * Shows current usage vs limits for organization resources
 * BUG-130: Added visual warning indicators for plan overages
 */

interface UsageLimitCardProps {
  title: string
  current: number
  limit: number
  unit?: string
}

export default function UsageLimitCard({ title, current, limit, unit = '' }: UsageLimitCardProps) {
  const isUnlimited = limit === -1
  const percentage = isUnlimited ? 0 : (current / limit) * 100
  const isNearLimit = !isUnlimited && percentage >= 80
  const isAtLimit = !isUnlimited && percentage >= 100
  const isOverLimit = !isUnlimited && current > limit

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}:</span>
        <span className={`text-sm font-medium inline-flex items-center gap-1.5 ${
          isOverLimit
            ? 'text-red-400'
            : isNearLimit
            ? 'text-yellow-400'
            : 'text-gray-600 dark:text-gray-400'
        }`}>
          {isOverLimit && (
            <svg className="w-4 h-4 text-red-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          )}
          {current} / {isUnlimited ? '\u221E' : limit} {unit}
          {isOverLimit && (
            <span className="text-xs bg-red-500/15 text-red-400 border border-red-500/30 px-1.5 py-0.5 rounded">
              Exceeds limit
            </span>
          )}
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
          style={{ width: isUnlimited ? '0%' : `${Math.min(percentage, 100)}%` }}
        />
      </div>
      <div className={`text-xs ${isOverLimit ? 'text-red-400 font-medium' : 'text-gray-500 dark:text-gray-400'}`}>
        {isUnlimited ? 'Unlimited' : `${percentage.toFixed(0)}% used`}
        {isOverLimit && ` \u2014 ${current - limit} over plan limit`}
      </div>
    </div>
  )
}
