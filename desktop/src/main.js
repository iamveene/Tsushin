'use strict'

const path = require('path')
const {
  app,
  BrowserWindow,
  Menu,
  shell,
  dialog,
  ipcMain,
  session,
} = require('electron')

const config = require('./config')

const IS_MAC = process.platform === 'darwin'
const SETUP_PAGE = path.join(__dirname, 'setup.html')
const ERROR_PAGE = path.join(__dirname, 'error.html')
const PRELOAD = path.join(__dirname, 'preload.js')

/** @type {BrowserWindow | null} */
let mainWindow = null

// Single instance: a second launch focuses the existing window.
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })
}

function currentServerOrigin() {
  return config.normalizeServerUrl(config.read().serverUrl)
}

// Hosts allowed to render INSIDE the shell: identity providers the web app
// redirects to during sign-in / integration consent. Everything else opens in
// the system browser, so a hijacked link cannot impersonate the app window.
const AUTH_HOSTS = [
  'accounts.google.com',
  'accounts.youtube.com',
  'oauth2.googleapis.com',
  'login.microsoftonline.com',
  'login.live.com',
  'github.com',
  'api.slack.com',
  'slack.com',
  'auth.atlassian.com',
  'app.asana.com',
  'auth.monday.com',
  'app.clickup.com',
  'api.notion.com',
]

function isAuthUrl(targetUrl) {
  try {
    const { hostname, protocol } = new URL(targetUrl)
    if (protocol !== 'https:') return false
    return AUTH_HOSTS.some((host) => hostname === host || hostname.endsWith(`.${host}`))
  } catch {
    return false
  }
}

/** Same-origin as the configured server (the only place app content may load). */
function isAppUrl(targetUrl) {
  const origin = currentServerOrigin()
  if (!origin) return false
  try {
    return new URL(targetUrl).origin === origin
  } catch {
    return false
  }
}

function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return
  const maximized = mainWindow.isMaximized()
  const bounds = maximized ? mainWindow.getNormalBounds() : mainWindow.getBounds()
  config.write({ window: { ...bounds, maximized } })
}

function loadStart(win) {
  const origin = currentServerOrigin()
  if (!origin) {
    win.loadFile(SETUP_PAGE)
    return
  }
  win.loadURL(origin)
}

function showError(win, detail) {
  const origin = currentServerOrigin() || ''
  win.loadFile(ERROR_PAGE, {
    query: { server: origin, detail: String(detail || '') },
  })
}

function createWindow() {
  const saved = config.read().window || {}

  mainWindow = new BrowserWindow({
    width: saved.width || 1440,
    height: saved.height || 900,
    x: saved.x,
    y: saved.y,
    minWidth: 900,
    minHeight: 600,
    show: false,
    backgroundColor: '#0b0d12',
    title: 'Tsushin',
    titleBarStyle: IS_MAC ? 'hiddenInset' : 'default',
    trafficLightPosition: IS_MAC ? { x: 16, y: 16 } : undefined,
    ...(IS_MAC ? {} : { icon: path.join(__dirname, '..', 'resources', 'icon.png') }),
    webPreferences: {
      preload: PRELOAD,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  })

  if (saved.maximized) mainWindow.maximize()

  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.on('close', saveWindowState)
  mainWindow.on('closed', () => {
    mainWindow = null
  })

  const wc = mainWindow.webContents

  const zoom = config.read().zoom || 0
  wc.on('did-finish-load', () => {
    wc.setZoomLevel(zoom)
  })

  // target="_blank" and window.open: keep app pages in-app, push the rest to
  // the system browser (OAuth consent screens, docs, customer links).
  wc.setWindowOpenHandler(({ url }) => {
    if (isAppUrl(url) || isAuthUrl(url)) {
      mainWindow.loadURL(url)
    } else if (/^https?:/i.test(url)) {
      shell.openExternal(url)
    }
    return { action: 'deny' }
  })

  // Top-level navigation away from the configured server leaves the shell.
  // OAuth consent (window.location.href = auth_url) must stay in the shell, or
  // the provider's callback would set the session cookie in the wrong browser.
  wc.on('will-navigate', (event, url) => {
    if (url.startsWith('file://') || isAppUrl(url) || isAuthUrl(url)) return
    event.preventDefault()
    if (/^https?:/i.test(url)) shell.openExternal(url)
  })

  wc.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    // -3 is ERR_ABORTED, emitted for ordinary client-side navigations.
    if (!isMainFrame || errorCode === -3) return
    if (validatedURL && validatedURL.startsWith('file://')) return
    showError(mainWindow, `${errorDescription} (${errorCode})`)
  })

  wc.on('render-process-gone', (_event, details) => {
    showError(mainWindow, `Renderer stopped: ${details.reason}`)
  })

  loadStart(mainWindow)
  return mainWindow
}

function applySecurityPolicies() {
  const ses = session.defaultSession

  // Only the configured origin may ask for camera/mic/notifications/clipboard.
  ses.setPermissionRequestHandler((contents, permission, callback) => {
    const allowed = ['notifications', 'media', 'clipboard-sanitized-write', 'fullscreen']
    callback(allowed.includes(permission) && isAppUrl(contents.getURL()))
  })
  ses.setPermissionCheckHandler((_contents, permission, requestingOrigin) => {
    const origin = currentServerOrigin()
    return Boolean(origin) && requestingOrigin === origin
  })
}

// Self-signed certificates are expected for the local compose stack. Accept
// them for loopback hosts only; anything else keeps normal TLS enforcement.
app.on('certificate-error', (event, _wc, url, _error, _cert, callback) => {
  let hostname = ''
  try {
    hostname = new URL(url).hostname
  } catch {
    /* fall through to default rejection */
  }
  if (config.read().allowInsecureLocalhost && hostname && config.isLocalHostname(hostname)) {
    event.preventDefault()
    callback(true)
    return
  }
  callback(false)
})

app.on('web-contents-created', (_event, contents) => {
  contents.on('will-attach-webview', (event) => event.preventDefault())
})

/* ------------------------------ IPC surface ------------------------------ */

ipcMain.handle('tsushin:get-config', () => {
  const cfg = config.read()
  return {
    serverUrl: cfg.serverUrl,
    allowInsecureLocalhost: cfg.allowInsecureLocalhost,
    version: app.getVersion(),
    platform: process.platform,
  }
})

ipcMain.handle('tsushin:set-server', (_event, rawUrl) => {
  const origin = config.normalizeServerUrl(rawUrl)
  if (!origin) return { ok: false, error: 'Enter a valid address, e.g. tsushin.archsec.io' }
  config.write({ serverUrl: origin })
  if (mainWindow) mainWindow.loadURL(origin)
  return { ok: true, serverUrl: origin }
})

ipcMain.handle('tsushin:retry', () => {
  if (mainWindow) loadStart(mainWindow)
})

ipcMain.handle('tsushin:open-setup', () => {
  if (mainWindow) mainWindow.loadFile(SETUP_PAGE)
})

/* --------------------------------- Menu --------------------------------- */

function promptForServer() {
  if (mainWindow) mainWindow.loadFile(SETUP_PAGE)
}

async function signOutAndForget() {
  const { response } = await dialog.showMessageBox(mainWindow, {
    type: 'warning',
    buttons: ['Cancel', 'Clear'],
    defaultId: 0,
    cancelId: 0,
    message: 'Clear local session data?',
    detail:
      'Signs you out of this desktop app by deleting its cookies and cached data. Your Tsushin server is not affected.',
  })
  if (response !== 1) return
  await session.defaultSession.clearStorageData()
  if (mainWindow) loadStart(mainWindow)
}

function setZoom(delta) {
  if (!mainWindow) return
  const next = delta === 0 ? 0 : Math.max(-3, Math.min(3, mainWindow.webContents.getZoomLevel() + delta))
  mainWindow.webContents.setZoomLevel(next)
  config.write({ zoom: next })
}

function buildMenu() {
  /** @type {Electron.MenuItemConstructorOptions[]} */
  const template = [
    ...(IS_MAC
      ? [
          {
            label: 'Tsushin',
            submenu: [
              { role: 'about' },
              { type: 'separator' },
              { label: 'Server…', accelerator: 'Cmd+,', click: promptForServer },
              { label: 'Clear Session Data…', click: signOutAndForget },
              { type: 'separator' },
              { role: 'services' },
              { type: 'separator' },
              { role: 'hide' },
              { role: 'hideOthers' },
              { role: 'unhide' },
              { type: 'separator' },
              { role: 'quit' },
            ],
          },
        ]
      : []),
    {
      label: 'File',
      submenu: [
        ...(IS_MAC
          ? []
          : [
              { label: 'Server…', accelerator: 'Ctrl+,', click: promptForServer },
              { label: 'Clear Session Data…', click: signOutAndForget },
              { type: 'separator' },
            ]),
        IS_MAC ? { role: 'close' } : { role: 'quit' },
      ],
    },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        {
          label: 'Reload',
          accelerator: 'CmdOrCtrl+R',
          click: () => mainWindow && mainWindow.webContents.reload(),
        },
        {
          label: 'Force Reload',
          accelerator: 'CmdOrCtrl+Shift+R',
          click: () => mainWindow && mainWindow.webContents.reloadIgnoringCache(),
        },
        {
          label: 'Back',
          accelerator: IS_MAC ? 'Cmd+[' : 'Alt+Left',
          click: () => mainWindow && mainWindow.webContents.navigationHistory.goBack(),
        },
        {
          label: 'Forward',
          accelerator: IS_MAC ? 'Cmd+]' : 'Alt+Right',
          click: () => mainWindow && mainWindow.webContents.navigationHistory.goForward(),
        },
        { type: 'separator' },
        { label: 'Actual Size', accelerator: 'CmdOrCtrl+0', click: () => setZoom(0) },
        { label: 'Zoom In', accelerator: 'CmdOrCtrl+Plus', click: () => setZoom(0.5) },
        { label: 'Zoom Out', accelerator: 'CmdOrCtrl+-', click: () => setZoom(-0.5) },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        { role: 'toggleDevTools' },
      ],
    },
    { role: 'windowMenu' },
    {
      role: 'help',
      submenu: [
        {
          label: 'Tsushin Documentation',
          click: () => shell.openExternal('https://github.com/iamveene/tsushin'),
        },
        {
          label: 'Open Config Folder',
          click: () => shell.showItemInFolder(config.CONFIG_FILE()),
        },
      ],
    },
  ]

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

// Google (and several other providers) reject OAuth from user agents that
// advertise Electron. Present the underlying Chrome instead.
function normalizeUserAgent() {
  app.userAgentFallback = app.userAgentFallback
    .replace(/\sElectron\/[^\s]+/i, '')
    // Drop the "<app>/<version>" token Electron injects before "Chrome/".
    .replace(/\s[^\s]*\/[^\s]+(?=\sChrome\/)/i, '')
}

app.whenReady().then(() => {
  normalizeUserAgent()
  if (IS_MAC) app.setAboutPanelOptions({ applicationName: 'Tsushin', applicationVersion: app.getVersion() })
  applySecurityPolicies()
  buildMenu()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (!IS_MAC) app.quit()
})
