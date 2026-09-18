'use strict'

const { contextBridge, ipcRenderer } = require('electron')

// Exposed to the setup/error pages AND to the Tsushin web app itself, so the
// web UI can detect the desktop shell (e.g. to hide "install" prompts).
contextBridge.exposeInMainWorld('tsushinDesktop', {
  isDesktop: true,
  getConfig: () => ipcRenderer.invoke('tsushin:get-config'),
  setServer: (url) => ipcRenderer.invoke('tsushin:set-server', url),
  retry: () => ipcRenderer.invoke('tsushin:retry'),
  openSetup: () => ipcRenderer.invoke('tsushin:open-setup'),
})
