'use client'

import { useState, useCallback } from 'react'
import { useDragContext } from '../context/DragContext'
import { createDragGhost, removeDragGhost } from './dragGhost'
import type { PaletteItemData, DragTransferData } from '../types'

interface PaletteItemProps { item: PaletteItemData; disabled?: boolean; onDoubleClick: (item: PaletteItemData) => void }

export default function PaletteItem({ item, disabled, onDoubleClick }: PaletteItemProps) {
  const { setActiveDrag } = useDragContext()
  const [isDragging, setIsDragging] = useState(false)

  const handleDragStart = useCallback((e: React.DragEvent) => {
    if (disabled) { e.preventDefault(); return }
    const transferData: DragTransferData = { categoryId: item.categoryId, nodeType: item.nodeType, itemId: item.id, itemName: item.name, metadata: item.metadata }
    e.dataTransfer.setData('application/studio-palette', JSON.stringify(transferData))
    e.dataTransfer.effectAllowed = 'copy'

    // Custom ghost image
    const ghostEl = createDragGhost(item)
    e.dataTransfer.setDragImage(ghostEl, 90, 20)
    setTimeout(() => removeDragGhost(ghostEl), 0)

    setActiveDrag(transferData)
    setIsDragging(true)
  }, [item, disabled, setActiveDrag])

  const handleDragEnd = useCallback(() => {
    setActiveDrag(null)
    setIsDragging(false)
  }, [setActiveDrag])

  return (
    <div
      // BUG-601 FIX: Only allow HTML5 drag for UNATTACHED items.
      // Previously attached items were draggable=true and the tooltip
      // promised "drag to detach" — but the canvas has no
      // drop-to-detach handler, so the drag is a no-op. Setting
      // ``draggable={false}`` on attached items kills the native drag
      // UX and the tooltip below now truthfully describes the only
      // available action (double-click).
      draggable={!disabled && !item.isAttached}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDoubleClick={() => !disabled && onDoubleClick(item)}
      className={`palette-item flex items-center gap-2 px-3 py-1.5 mx-1 rounded-md text-sm ${item.isAttached ? 'attached' : ''} ${disabled ? 'disabled' : ''} ${isDragging ? 'dragging' : ''}`}
      title={
        disabled
          ? 'Limit reached for this category'
          : item.isAttached
            ? 'Double-click to detach'
            : 'Double-click or drag to attach'
      }>
      {/* Drag grip icon - visible on hover */}
      <svg className="drag-grip w-3 h-3 flex-shrink-0" viewBox="0 0 12 12" fill="currentColor">
        <circle cx="3.5" cy="2" r="1.2" /><circle cx="8.5" cy="2" r="1.2" />
        <circle cx="3.5" cy="6" r="1.2" /><circle cx="8.5" cy="6" r="1.2" />
        <circle cx="3.5" cy="10" r="1.2" /><circle cx="8.5" cy="10" r="1.2" />
      </svg>
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${item.isAttached ? 'bg-green-400' : 'bg-gray-600'}`} />
      <span className={`flex-1 truncate text-xs ${item.isAttached ? 'text-white' : 'text-tsushin-slate'}`}>{item.name}</span>
      {item.isAttached && <svg className="w-3 h-3 text-green-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.5 12.75l6 6 9-13.5" /></svg>}
    </div>
  )
}
