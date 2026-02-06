/**
 * Layout utilities barrel export
 * Phase 2: Auto-layout algorithms
 *
 * IMPORTANT: Only types and constants are exported here for SSR safety.
 * The actual layout functions (useAutoLayout, getLayoutedElements) should be
 * imported directly from their files ONLY inside dynamically imported components.
 */

// Safe SSR exports - types and constants only
export type { LayoutOptions } from './types'
export { DEFAULT_LAYOUT_OPTIONS } from './types'
