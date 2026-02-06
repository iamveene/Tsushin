/**
 * Clipboard utility with fallback for non-secure contexts (HTTP).
 *
 * navigator.clipboard requires a secure context (HTTPS or localhost).
 * When accessed over plain HTTP on a LAN IP, navigator.clipboard is undefined.
 * This utility falls back to the deprecated document.execCommand('copy')
 * approach using a temporary textarea element.
 */
export async function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  // Fallback for non-secure contexts
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  try {
    const ok = document.execCommand('copy')
    if (!ok) {
      throw new Error('execCommand copy returned false')
    }
  } finally {
    document.body.removeChild(textarea)
  }
}
