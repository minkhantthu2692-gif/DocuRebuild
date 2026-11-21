"use strict";

const { contextBridge, ipcRenderer } = require("electron");

/**
 * Expose only the launch token and build metadata. No Node API, filesystem or
 * generic IPC bridge reaches the page. The token never touches disk or the
 * process command line.
 */
const config = ipcRenderer.sendSync("docurebuild:config");
contextBridge.exposeInMainWorld("docurebuild", {
  apiToken: config.apiToken,
  platform: config.platform,
  version: config.version,
});
