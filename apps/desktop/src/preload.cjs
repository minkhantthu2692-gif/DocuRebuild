"use strict";

const { contextBridge, ipcRenderer } = require("electron");

/**
 * Expose only the launch token and build metadata. No Node API, filesystem or
 * generic IPC bridge reaches the page. The token never touches disk or the
 * process command line.
 *
 * The bridge is installed only when the document is the local application
 * origin. If the window ever navigated elsewhere, that page would see no
 * bridge and could not read the launch token.
 */
const config = ipcRenderer.sendSync("docurebuild:config");
if (config.apiToken && config.origin && window.location.origin === config.origin) {
  contextBridge.exposeInMainWorld("docurebuild", {
    apiToken: config.apiToken,
    platform: config.platform,
    version: config.version,
  });
}
