/**
 * Smart Paste Utility
 *
 * Detects structured content (JSON, code blocks, URLs) in pasted text
 * and auto-formats it with appropriate markdown code fences.
 */

/**
 * Analyzes pasted text and returns a formatted version if the content
 * is detected as JSON or code. Returns null if no transformation is needed.
 */
export function formatPastedContent(text: string): string | null {
  if (!text || !text.trim()) return null

  const trimmed = text.trim()

  // JSON detection: try parsing and wrap if valid object/array
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed !== null && typeof parsed === 'object') {
      return '```json\n' + JSON.stringify(parsed, null, 2) + '\n```'
    }
  } catch {
    // Not valid JSON, continue checking
  }

  // URL detection: single line starting with http(s)
  if (/^https?:\/\/\S+$/.test(trimmed)) {
    return null // No transformation for URLs
  }

  // Code detection: multi-line with consistent indentation
  const lines = text.split('\n')
  if (lines.length >= 2) {
    const indentedLines = lines.filter(line => /^[\t ]{1,}/.test(line) && line.trim().length > 0)
    const nonEmptyLines = lines.filter(line => line.trim().length > 0)

    // At least 2 indented lines and it's not just a plain paragraph
    if (indentedLines.length >= 2 && indentedLines.length / nonEmptyLines.length > 0.3) {
      return '```\n' + text + '\n```'
    }
  }

  // Plain text: no transformation
  return null
}
