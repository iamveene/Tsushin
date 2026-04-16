'use client'

import { createContext, useContext, useState, type ReactNode } from 'react'
import type { DragTransferData } from '../types'

interface DragContextValue {
  activeDrag: DragTransferData | null
  setActiveDrag: (data: DragTransferData | null) => void
}

const DragContext = createContext<DragContextValue>({
  activeDrag: null,
  setActiveDrag: () => {},
})

export function DragProvider({ children }: { children: ReactNode }) {
  const [activeDrag, setActiveDrag] = useState<DragTransferData | null>(null)
  return (
    <DragContext.Provider value={{ activeDrag, setActiveDrag }}>
      {children}
    </DragContext.Provider>
  )
}

export function useDragContext() {
  return useContext(DragContext)
}
