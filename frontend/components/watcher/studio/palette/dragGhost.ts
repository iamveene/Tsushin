import type { PaletteItemData, ProfileCategoryId } from '../types'

const GHOST_COLORS: Record<ProfileCategoryId, string> = {
  persona: 'rgba(168, 85, 247, 0.8)',
  channels: 'rgba(59, 130, 246, 0.8)',
  skills: 'rgba(20, 184, 166, 0.8)',
  tools: 'rgba(249, 115, 22, 0.8)',
  security: 'rgba(239, 68, 68, 0.8)',
  knowledge: 'rgba(139, 92, 246, 0.8)',
  memory: 'rgba(59, 130, 246, 0.8)',
}

const GHOST_DOT_COLORS: Record<ProfileCategoryId, string> = {
  persona: '#a855f7',
  channels: '#3b82f6',
  skills: '#14b8a6',
  tools: '#f97316',
  security: '#ef4444',
  knowledge: '#8b5cf6',
  memory: '#3b82f6',
}

const CATEGORY_LABELS: Record<ProfileCategoryId, string> = {
  persona: 'Persona',
  channels: 'Channel',
  skills: 'Skill',
  tools: 'Tool',
  security: 'Security',
  knowledge: 'Knowledge',
  memory: 'Memory',
}

export function createDragGhost(item: PaletteItemData): HTMLElement {
  const borderColor = GHOST_COLORS[item.categoryId] || 'rgba(139, 146, 158, 0.8)'
  const dotColor = GHOST_DOT_COLORS[item.categoryId] || '#8B929E'
  const categoryLabel = CATEGORY_LABELS[item.categoryId] || item.categoryId
  const displayName = item.name.length > 22 ? item.name.slice(0, 20) + '...' : item.name

  const el = document.createElement('div')
  el.style.cssText = `
    position: fixed; top: -9999px; left: -9999px;
    background: rgba(22, 27, 34, 0.95);
    border: 1px solid ${borderColor};
    border-radius: 8px;
    padding: 6px 12px;
    display: flex; align-items: center; gap: 8px;
    font-family: -apple-system, system-ui, sans-serif;
    pointer-events: none;
    white-space: nowrap;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  `

  const dot = document.createElement('span')
  dot.style.cssText = `width: 8px; height: 8px; border-radius: 50%; background: ${dotColor}; flex-shrink: 0;`

  const name = document.createElement('span')
  name.style.cssText = 'color: white; font-size: 12px; font-weight: 500;'
  name.textContent = displayName

  const label = document.createElement('span')
  label.style.cssText = 'color: rgba(139, 146, 158, 0.7); font-size: 11px; margin-left: 4px;'
  label.textContent = categoryLabel

  el.appendChild(dot)
  el.appendChild(name)
  el.appendChild(label)

  document.body.appendChild(el)
  return el
}

export function removeDragGhost(el: HTMLElement): void {
  el.parentNode?.removeChild(el)
}
