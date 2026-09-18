'use strict'

const fs = require('fs')
const path = require('path')
const { app } = require('electron')

const CONFIG_FILE = () => path.join(app.getPath('userData'), 'config.json')

const DEFAULTS = {
  serverUrl: process.env.TSUSHIN_SERVER_URL || '',
  // Self-signed certs are normal for the local compose stack (https://localhost)
  // but must never be trusted for a remote host.
  allowInsecureLocalhost: true,
  window: { width: 1440, height: 900, x: undefined, y: undefined, maximized: false },
  zoom: 0,
}

let cache = null

function read() {
  if (cache) return cache
  try {
    const raw = fs.readFileSync(CONFIG_FILE(), 'utf8')
    cache = { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    cache = { ...DEFAULTS }
  }
  return cache
}

function write(patch) {
  cache = { ...read(), ...patch }
  try {
    fs.mkdirSync(path.dirname(CONFIG_FILE()), { recursive: true })
    fs.writeFileSync(CONFIG_FILE(), JSON.stringify(cache, null, 2), 'utf8')
  } catch (err) {
    console.error('[tsushin] failed to persist config:', err)
  }
  return cache
}

/**
 * Normalize whatever the user typed into an origin we are willing to load.
 * Accepts "tsushin.archsec.io", "localhost", "https://host:8443/path".
 * Returns null when it cannot be parsed into an http(s) origin.
 */
function normalizeServerUrl(input) {
  const raw = String(input || '').trim()
  if (!raw) return null
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`
  let url
  try {
    url = new URL(withScheme)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  if (!url.hostname) return null
  return url.origin
}

function isLocalHostname(hostname) {
  return (
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    hostname === '::1' ||
    hostname === '[::1]' ||
    hostname.endsWith('.localhost')
  )
}

module.exports = { read, write, normalizeServerUrl, isLocalHostname, CONFIG_FILE }
