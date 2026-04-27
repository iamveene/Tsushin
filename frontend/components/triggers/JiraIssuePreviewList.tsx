'use client'

import type { JiraIssuePreview } from '@/lib/client'
import { ExternalLinkIcon } from '@/components/ui/icons'

interface Props {
  issues?: JiraIssuePreview[] | null
  siteUrl?: string | null
  emptyLabel?: string
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function issueType(issue: JiraIssuePreview): string | null {
  return textValue(issue.issue_type_name) || textValue(issue.issue_type) || textValue(issue.type)
}

function issueDescription(issue: JiraIssuePreview): string | null {
  return textValue(issue.description_preview) || textValue(issue.description)
}

function issueHref(issue: JiraIssuePreview, siteUrl?: string | null): string | null {
  const explicit = textValue(issue.url) || textValue(issue.link) || textValue(issue.issue_url)
  if (explicit) return explicit
  const key = textValue(issue.key)
  if (!key || !siteUrl) return null
  const normalizedSite = siteUrl.replace(/\/$/, '').replace(/\/jira$/i, '')
  return `${normalizedSite}/browse/${encodeURIComponent(key)}`
}

export default function JiraIssuePreviewList({ issues, siteUrl, emptyLabel = 'No sample issues returned.' }: Props) {
  if (!issues || issues.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-tsushin-border p-4 text-sm text-tsushin-slate">
        {emptyLabel}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {issues.map((issue, index) => {
        const key = textValue(issue.key) || textValue(issue.id) || `sample-${index + 1}`
        const summary = textValue(issue.summary) || 'Untitled issue'
        const href = issueHref(issue, siteUrl)
        const type = issueType(issue)
        const description = issueDescription(issue)
        return (
          <div key={`${key}:${index}`} className="rounded-xl border border-tsushin-border bg-black/20 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 font-mono text-sm text-blue-200 hover:text-white"
                    >
                      {key}
                      <ExternalLinkIcon size={12} />
                    </a>
                  ) : (
                    <span className="font-mono text-sm text-blue-200">{key}</span>
                  )}
                  {type && (
                    <span className="rounded-full border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 text-xs text-blue-100">
                      {type}
                    </span>
                  )}
                  {issue.status && (
                    <span className="rounded-full border border-tsushin-border px-2 py-0.5 text-xs text-tsushin-fog">
                      {issue.status}
                    </span>
                  )}
                </div>
                <div className="mt-2 text-sm font-medium text-white">{summary}</div>
              </div>
              {issue.updated && (
                <div className="shrink-0 text-xs text-tsushin-slate">{issue.updated}</div>
              )}
            </div>
            {description && (
              <p className="mt-3 line-clamp-3 text-sm text-tsushin-slate">{description}</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
