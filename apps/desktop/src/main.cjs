"use strict";

/**
 * DocuRebuild desktop shell.
 *
 * The shell owns the application window and the lifecycle of the bundled
 * Python backend. It binds the backend to a random loopback port, generates a
 * per-launch token, and never exposes the API to another machine. User data
 * stays in the same local folder the browser build already uses.
 */

const {
  app,
  BrowserWindow,
  Menu,
  dialog,
  ipcMain,
  nativeTheme,
  screen,
  session,
  shell,
} = require("electron");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const APP_ID = "com.docurebuild.app";
const DATA_FOLDER = "DocuRebuild";
const WINDOW_STATE_FILE = "window-state.json";
const STARTUP_TIMEOUT_MS = 45000;

let mainWindow = null;
let backend = null;
let backendToken = null;
let backendPort = null;
let backendReady = false;
let quitting = false;
let logDirectory = null;

app.setName("DocuRebuild");
app.setAppUserModelId(APP_ID);
const userDataDirectory = path.join(app.getPath("appData"), DATA_FOLDER);
app.setPath("userData", userDataDirectory);

function getDataDirectory() {
  if (process.env.DOCUREBUILD_DATA_DIR) {
    return process.env.DOCUREBUILD_DATA_DIR;
  }
  const localAppData = process.env.LOCALAPPDATA || app.getPath("appData");
  // Match platformdirs.user_data_dir("DocuRebuild", "DocuRebuild") so an
  // existing local workspace keeps its projects after the desktop upgrade.
  return path.join(localAppData, DATA_FOLDER, DATA_FOLDER);
}

function getResourceRoot() {
  if (process.env.DOCUREBUILD_DESKTOP_RESOURCES) {
    return process.env.DOCUREBUILD_DESKTOP_RESOURCES;
  }
  return app.isPackaged
    ? process.resourcesPath
    : path.join(__dirname, "..", "..", "..", "dist", "desktop");
}

function getBackendExecutable() {
  const suffix = process.platform === "win32" ? ".exe" : "";
  return path.join(getResourceRoot(), "backend", `docurebuild-backend${suffix}`);
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close(() => {
        if (port) resolve(port);
        else reject(new Error("Could not allocate a local port."));
      });
    });
  });
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function tailLog() {
  if (!logDirectory) return "";
  try {
    const text = fs.readFileSync(path.join(logDirectory, "backend.log"), "utf8");
    return text.slice(-4000);
  } catch {
    return "";
  }
}

function stopBackend() {
  if (!backend || backend.exitCode !== null) return;
  if (process.platform === "win32" && backend.pid) {
    // Kill the whole tree so a Tesseract child cannot outlive the window.
    spawn("taskkill", ["/pid", String(backend.pid), "/t", "/f"], {
      windowsHide: true,
      stdio: "ignore",
    });
    return;
  }
  backend.kill();
}

async function startBackend() {
  const executable = getBackendExecutable();
  if (!fs.existsSync(executable)) {
    throw new Error(`The bundled backend was not found: ${executable}`);
  }
  const resources = getResourceRoot();
  const tesseract = path.join(resources, "tesseract", "tesseract.exe");
  const tessdata = path.join(resources, "tesseract", "tessdata");
  const web = path.join(resources, "web");

  backendPort = await findFreePort();
  backendToken = crypto.randomBytes(32).toString("hex");
  logDirectory = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logDirectory, { recursive: true });
  fs.mkdirSync(getDataDirectory(), { recursive: true });

  const environment = {
    ...process.env,
    DOCUREBUILD_ENVIRONMENT: "production",
    DOCUREBUILD_DATA_DIR: getDataDirectory(),
    DOCUREBUILD_API_TOKEN: backendToken,
    DOCUREBUILD_WEB_DIST: web,
    DOCUREBUILD_LOG_DIR: logDirectory,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
  };
  if (fs.existsSync(tesseract)) {
    environment.DOCUREBUILD_TESSERACT_CMD = tesseract;
    environment.DOCUREBUILD_TESSDATA_DIR = tessdata;
  }

  backend = spawn(executable, ["--port", String(backendPort)], {
    cwd: path.dirname(executable),
    env: environment,
    windowsHide: true,
    stdio: "ignore",
  });

  backend.once("error", (error) => {
    backendReady = false;
    if (!quitting) showStartupFailure(error.message);
  });

  backend.once("exit", (code, signal) => {
    // A crash after startup would otherwise leave a window with no API behind it.
    const wasReady = backendReady;
    backendReady = false;
    if (!quitting && wasReady) {
      showStartupFailure(
        `The local workspace service stopped unexpectedly (${code ?? signal}).`,
      );
    }
  });

  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (backend.exitCode !== null) {
      throw new Error(
        `The local backend stopped during startup (exit code ${backend.exitCode}).`,
      );
    }
    try {
      const response = await fetch(
        `http://127.0.0.1:${backendPort}/api/health`,
        {
          headers: { Authorization: `Bearer ${backendToken}` },
          signal: AbortSignal.timeout(1500),
        },
      );
      if (response.ok) {
        backendReady = true;
        return;
      }
    } catch {
      // The process is still starting; poll again.
    }
    await delay(250);
  }
  throw new Error("The local backend did not become ready in time.");
}

function showStartupFailure(reason) {
  if (quitting) return;
  quitting = true;
  const log = tailLog();
  const detail = log ? `\n\nLast log lines:\n${log}` : "";
  const choice = dialog.showMessageBoxSync({
    type: "error",
    title: "DocuRebuild could not start",
    message: "The local workspace service did not start.",
    detail: `${reason}${detail}`,
    buttons: ["Open log folder", "Quit"],
    defaultId: 1,
    cancelId: 1,
    noLink: true,
  });
  if (choice === 0 && logDirectory) {
    void shell.openPath(logDirectory);
  }
  app.quit();
}

function readWindowState() {
  try {
    const value = JSON.parse(
      fs.readFileSync(path.join(app.getPath("userData"), WINDOW_STATE_FILE), "utf8"),
    );
    if (
      Number.isFinite(value.width) &&
      Number.isFinite(value.height) &&
      Number.isFinite(value.x) &&
      Number.isFinite(value.y)
    ) {
      return value;
    }
  } catch {
    // First launch or a damaged file: use the default geometry.
  }
  return null;
}

function saveWindowState(window) {
  if (!window || window.isDestroyed()) return;
  try {
    const bounds = window.getNormalBounds();
    fs.writeFileSync(
      path.join(app.getPath("userData"), WINDOW_STATE_FILE),
      JSON.stringify({ ...bounds, maximized: window.isMaximized() }),
      "utf8",
    );
  } catch {
    // A failed window-state write must never prevent quitting.
  }
}

function visibleBounds(state) {
  if (!state) return null;
  const margin = 64;
  const display = screen.getAllDisplays().find((candidate) => {
    const area = candidate.workArea;
    return (
      state.x + margin < area.x + area.width &&
      state.x + state.width - margin > area.x &&
      state.y + margin < area.y + area.height &&
      state.y + state.height - margin > area.y
    );
  });
  if (!display) return null;
  return {
    x: state.x,
    y: state.y,
    width: Math.max(1024, Math.min(state.width, display.workArea.width)),
    height: Math.max(700, Math.min(state.height, display.workArea.height)),
  };
}

function installSecurityHandlers() {
  session.defaultSession.setPermissionRequestHandler((_contents, permission, done) => {
    // The editor only needs to write sanitized clipboard content from a user
    // gesture. Camera, microphone, geolocation and notifications stay denied.
    done(permission === "clipboard-sanitized-write");
  });
  session.defaultSession.setPermissionCheckHandler(
    (_contents, permission) => permission === "clipboard-sanitized-write",
  );

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const headers = details.responseHeaders || {};
    headers["Content-Security-Policy"] = [
      [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "media-src 'self' blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
      ].join("; "),
    ];
    callback({ responseHeaders: headers });
  });

  session.defaultSession.on("will-download", (_event, item) => {
    item.setSaveDialogOptions({
      title: "Save DocuRebuild export",
      defaultPath: path.join(app.getPath("downloads"), item.getFilename()),
    });
  });
}

/**
 * Attach the launch token to subresource requests that cannot set headers.
 *
 * Page thumbnails, document figures and CSS images are loaded by <img> tags,
 * which never send an Authorization header. The renderer's own fetch calls
 * already carry the token, so this only fills the gap and never duplicates it.
 * The token stays in the shell process; it is not exposed in URLs or storage.
 */
function installApiAuthorization(origin) {
  if (!backendToken) return;
  const filter = { urls: [`${origin}/api/*`] };
  session.defaultSession.webRequest.onBeforeSendHeaders(filter, (details, callback) => {
    const headers = details.requestHeaders || {};
    const hasAuthorization = Object.keys(headers).some(
      (name) => name.toLowerCase() === "authorization",
    );
    if (!hasAuthorization) {
      headers.Authorization = `Bearer ${backendToken}`;
    }
    callback({ requestHeaders: headers });
  });
}

function windowBackgroundColor() {
  // Pre-paint colour only: avoid a white flash before the saved theme applies.
  return nativeTheme.shouldUseDarkColors ? "#0c0e17" : "#f6f6f4";
}

function createWindow() {
  const state = readWindowState();
  const bounds = visibleBounds(state);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    backgroundColor: windowBackgroundColor(),
    icon: path.join(getResourceRoot(), "icon.ico"),
    title: "DocuRebuild",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
      devTools: process.env.DOCUREBUILD_DEVTOOLS === "1",
    },
  });

  nativeTheme.on("updated", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setBackgroundColor(windowBackgroundColor());
    }
  });

  if (bounds) mainWindow.setBounds(bounds);
  if (state && state.maximized) mainWindow.maximize();

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("close", () => saveWindowState(mainWindow));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  const origin = `http://127.0.0.1:${backendPort}`;
  const isAppUrl = (target) => {
    try {
      // Compare parsed origins, not string prefixes: a URL such as
      // http://127.0.0.1:<port>@attacker.example shares the prefix but would
      // navigate the privileged window to another site.
      return new URL(target).origin === origin;
    } catch {
      return false;
    }
  };

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^(https?:|mailto:)/i.test(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!isAppUrl(url)) {
      event.preventDefault();
      if (/^(https?:|mailto:)/i.test(url)) void shell.openExternal(url);
    }
  });
  mainWindow.webContents.on("will-redirect", (event, url) => {
    if (!isAppUrl(url)) {
      event.preventDefault();
      if (/^(https?:|mailto:)/i.test(url)) void shell.openExternal(url);
    }
  });

  void mainWindow.loadURL(`${origin}/`);

  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    if (!quitting && details.reason !== "clean-exit") {
      showStartupFailure(`The interface process stopped (${details.reason}).`);
    }
  });

  if (process.env.DOCUREBUILD_DEVTOOLS === "1") {
    mainWindow.webContents.openDevTools({ mode: "detach" });
  }
}

ipcMain.on("docurebuild:config", (event) => {
  event.returnValue = {
    apiToken: backendToken,
    origin: backendPort ? `http://127.0.0.1:${backendPort}` : "",
    platform: "desktop",
    version: app.getVersion(),
  };
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null);
    installSecurityHandlers();
    try {
      await startBackend();
      installApiAuthorization(`http://127.0.0.1:${backendPort}`);
      createWindow();
    } catch (error) {
      showStartupFailure(error instanceof Error ? error.message : String(error));
    }
  });

  app.on("window-all-closed", () => {
    app.quit();
  });

  app.on("before-quit", () => {
    quitting = true;
    saveWindowState(mainWindow);
    stopBackend();
  });

  app.on("activate", () => {
    if (mainWindow) mainWindow.focus();
  });
}
