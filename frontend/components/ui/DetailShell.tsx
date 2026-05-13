'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { ChevronLeftIcon } from '@/components/ui/icons'

export interface BreadcrumbItem {
  label: string
  href?: string
}

export interface DetailShellHeaderProps {
  breadcrumb?: BreadcrumbItem[]
  backHref?: string
  backLabel?: string
  title: ReactNode
  icon?: ReactNode
  description?: ReactNode
  badges?: ReactNode
  meta?: ReactNode
  actions?: ReactNode
}

export function DetailShellHeader({
  breadcrumb,
  backHref,
  backLabel,
  title,
  icon,
  description,
  badges,
  meta,
  actions,
}: DetailShellHeaderProps) {
  const showBackOnly = !breadcrumb && backHref

  return (
    <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0 flex-1">
        {breadcrumb && breadcrumb.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-tsushin-slate">
            {breadcrumb.map((item, i) => {
              const isLast = i === breadcrumb.length - 1
              return (
                <span key={`${item.label}-${i}`} className="inline-flex items-center gap-2">
                  {item.href && !isLast ? (
                    <Link href={item.href} className="transition-colors hover:text-white">
                      {item.label}
                    </Link>
                  ) : (
                    <span className={isLast ? 'text-tsushin-fog' : ''}>{item.label}</span>
                  )}
                  {!isLast && <span aria-hidden>/</span>}
                </span>
              )
            })}
          </div>
        )}
        {showBackOnly && (
          <Link
            href={backHref}
            className="mb-3 inline-flex items-center gap-2 text-sm text-tsushin-slate transition-colors hover:text-white"
          >
            <ChevronLeftIcon size={16} />
            {backLabel || 'Back'}
          </Link>
        )}
        <div className="flex flex-wrap items-center gap-3">
          {icon}
          <h1 className="text-3xl font-display font-bold text-white">{title}</h1>
          {badges}
        </div>
        {description && (
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">{description}</p>
        )}
        {meta && (
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-tsushin-slate">
            {meta}
          </div>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export default DetailShellHeader
