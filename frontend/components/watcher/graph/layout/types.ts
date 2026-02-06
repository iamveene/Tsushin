/**
 * Layout Type Definitions
 * Phase 2: Types for auto-layout algorithms
 *
 * This file is safe to import during SSR as it contains no dagre imports
 */

export interface LayoutOptions {
  direction: 'TB' | 'LR' | 'BT' | 'RL'  // Top-Bottom, Left-Right, Bottom-Top, Right-Left
  nodeSpacing: number    // Horizontal spacing between nodes (nodesep)
  rankSpacing: number    // Vertical spacing between ranks (ranksep)
}

export const DEFAULT_LAYOUT_OPTIONS: LayoutOptions = {
  direction: 'LR',       // Left-to-Right as default
  nodeSpacing: 80,
  rankSpacing: 120,
}
