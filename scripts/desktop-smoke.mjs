#!/usr/bin/env node
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");

function parseArgs(argv) {
  const options = {
    app: null,
    resources: null,
    out: path.join(repoRoot, "docs", "smoke", "desktop-smoke.json"),
    timeoutMs: 600000,
    requireOcr: true,
    keep: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--app") {
      options.app = path.resolve(argv[++index]);
    } else if (argument === "--resources") {
      options.resources = path.resolve(argv[++index]);
    } else if (argument === "--out") {
      options.out = path.resolve(argv[++index]);
    } else if (argument === "--timeout") {
      options.timeoutMs = Number(argv[++index]) * 1000;
    } else if (argument === "--allow-embedded-ocr") {
      options.requireOcr = false;
    } else if (argument === "--keep") {
      options.keep = true;
    } else if (argument === "--help" || argument === "-h") {
      console.log(
        [
          "Usage: node scripts/desktop-smoke.mjs [options]",
          "",
          "  --app <path>            Packaged DocuRebuild.exe (default: dist/desktop-installer/win-unpacked)",
          "  --resources <path>      Override DOCUREBUILD_DESKTOP_RESOURCES",
          "  --out <path>            JSON report path (default: docs/smoke/desktop-smoke.json)",
          "  --timeout <seconds>     Overall run timeout (default: 600)",
          "  --allow-embedded-ocr    Accept pdf-text when bundled Tesseract is unavailable",
          "  --keep                  Keep the disposable data directory",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${argument}`);
    }
  }

  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs <= 0) {
    throw new Error("--timeout must be a positive number of seconds");
  }
  return options;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function findDefaultApp() {
  const unpacked = path.join(
    repoRoot,
    "dist",
    "desktop-installer",
    "win-unpacked",
    "DocuRebuild.exe",
  );
  if (fs.existsSync(unpacked)) return unpacked;

  if (process.env.LOCALAPPDATA) {
    const installed = path.join(
      process.env.LOCALAPPDATA,
      "Programs",
      "DocuRebuild",
      "DocuRebuild.exe",
    );
    if (fs.existsSync(installed)) return installed;
  }

  throw new Error(
    "Packaged app not found. Run `npm run desktop:pack` or pass `--app <path>`.",
  );
}

function resolveResources(appPath, requested) {
  if (requested) return path.resolve(requested);

  const packaged = path.join(path.dirname(appPath), "resources");
  const backend = path.join(
    packaged,
    "backend",
    process.platform === "win32" ? "docurebuild-backend.exe" : "docurebuild-backend",
  );
  if (fs.existsSync(backend)) return packaged;

  const fallback = path.join(repoRoot, "dist", "desktop");
  if (fs.existsSync(path.join(fallback, "backend"))) return fallback;
  return packaged;
}

function createWorkRoot() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "docurebuild-smoke-"));
  const directories = {
    root,
    appData: path.join(root, "appdata"),
    localAppData: path.join(root, "localappdata"),
    temp: path.join(root, "temp"),
    data: path.join(root, "data"),
    electronLog: path.join(root, "electron.log"),
  };
  for (const directory of [
    directories.appData,
    directories.localAppData,
    directories.temp,
    directories.data,
  ]) {
    fs.mkdirSync(directory, { recursive: true });
  }
  return directories;
}

function escapePdfText(value) {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\(/g, "\\(")
    .replace(/\)/g, "\\)");
}

function buildSmokePdf() {
  const lines = [
    { size: 22, y: 720, text: "DocuRebuild desktop smoke test" },
    {
      size: 13,
      y: 680,
      text: "This page verifies project import, source rendering, OCR review",
    },
    { size: 13, y: 660, text: "and insertion into the document editor." },
    { size: 13, y: 620, text: "The quick brown fox jumps over the lazy dog." },
    {
      size: 13,
      y: 600,
      text: "Local-first reconstruction keeps every original page unchanged.",
    },
    { size: 13, y: 560, text: "Smoke marker: DOCUREBUILD_SMOKE_SOURCE_PAGE" },
  ];
  const content = lines
    .map(
      (line) =>
        `BT /F1 ${line.size} Tf 1 0 0 1 72 ${line.y} Tm (${escapePdfText(line.text)}) Tj ET`,
    )
    .join("\n");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(content, "latin1")} >>\nstream\n${content}\nendstream`,
  ];

  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  for (let index = 0; index < objects.length; index += 1) {
    offsets.push(Buffer.byteLength(pdf, "latin1"));
    pdf += `${index + 1} 0 obj\n${objects[index]}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let index = 1; index < offsets.length; index += 1) {
    pdf += `${String(offsets[index]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

class Cdp {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.handlers = [];
    this.socket = null;
  }

  async connect() {
    if (typeof WebSocket === "undefined") {
      throw new Error(
        "This smoke suite needs a Node.js runtime with a global WebSocket (Node 22+).",
      );
    }

    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        clearTimeout(pending.timer);
        if (message.error) {
          pending.reject(
            new Error(`${pending.method}: ${message.error.message ?? "CDP error"}`),
          );
        } else {
          pending.resolve(message.result);
        }
        return;
      }
      for (const handler of this.handlers) handler(message);
    });
    socket.addEventListener("close", () => {
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timer);
        pending.reject(new Error("DevTools connection closed"));
      }
      this.pending.clear();
    });

    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Timed out connecting to the DevTools WebSocket")),
        15000,
      );
      socket.addEventListener(
        "open",
        () => {
          clearTimeout(timer);
          resolve();
        },
        { once: true },
      );
      socket.addEventListener(
        "error",
        () => {
          clearTimeout(timer);
          reject(new Error("DevTools WebSocket connection failed"));
        },
        { once: true },
      );
    });
  }

  send(method, params = {}) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error("DevTools connection is not open"));
    }
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Timed out sending ${method}`));
      }, 30000);
      this.pending.set(id, { resolve, reject, timer, method });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  onEvent(handler) {
    this.handlers.push(handler);
  }

  async evaluate(expression) {
    const response = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (response.exceptionDetails) {
      const detail =
        response.exceptionDetails.exception?.description ??
        response.exceptionDetails.text ??
        "Evaluation failed";
      throw new Error(detail);
    }
    return response.result?.value;
  }

  close() {
    if (this.socket) {
      try {
        this.socket.close();
      } catch {
        this.socket = null;
      }
    }
  }
}

async function waitUntil(check, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  const suffix = lastError ? `: ${lastError.message}` : "";
  throw new Error(
    `Timed out after ${Math.round(timeoutMs / 1000)}s waiting for ${label}${suffix}`,
  );
}

function waitForEval(cdp, expression, timeoutMs, label) {
  return waitUntil(() => cdp.evaluate(expression), timeoutMs, label);
}

function getProcessSnapshot() {
  const command =
    "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress";
  const output = execFileSync(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", command],
    {
      encoding: "utf8",
      windowsHide: true,
      maxBuffer: 16 * 1024 * 1024,
    },
  ).trim();
  if (!output || output === "null") return [];
  const parsed = JSON.parse(output);
  return Array.isArray(parsed) ? parsed : [parsed];
}

function descendantPids(snapshot, rootPid) {
  const children = new Map();
  for (const processInfo of snapshot) {
    const parent = Number(processInfo.ParentProcessId);
    const child = Number(processInfo.ProcessId);
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(child);
  }
  const result = [];
  const queue = [Number(rootPid)];
  while (queue.length > 0) {
    const parent = queue.shift();
    for (const child of children.get(parent) ?? []) {
      result.push(child);
      queue.push(child);
    }
  }
  return result;
}

function killProcessTree(pid) {
  try {
    execFileSync("taskkill.exe", ["/pid", String(pid), "/t", "/f"], {
      stdio: "ignore",
      windowsHide: true,
    });
  } catch {
    return;
  }
}

function waitForChildExit(child, timeoutMs) {
  return new Promise((resolve) => {
    if (child.exitCode !== null) {
      resolve(true);
      return;
    }
    const timer = setTimeout(() => {
      child.removeListener("exit", onExit);
      resolve(false);
    }, timeoutMs);
    const onExit = () => {
      clearTimeout(timer);
      resolve(true);
    };
    child.once("exit", onExit);
  });
}

async function waitForCdpTarget(port, timeoutMs, child) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `The Electron process exited before DevTools was available (code ${child.exitCode}).`,
      );
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      if (response.ok) {
        const targets = await response.json();
        const page = targets.find(
          (target) => target.type === "page" && target.webSocketDebuggerUrl,
        );
        if (page) return page;
      }
    } catch (error) {
      lastError = error;
    }
    await sleep(500);
  }
  const suffix = lastError ? `: ${lastError.message}` : "";
  throw new Error(`Timed out waiting for the Electron DevTools target${suffix}`);
}

function apiExpression(method, apiPath, body) {
  const bodyExpression =
    body === undefined ? "undefined" : JSON.stringify(JSON.stringify(body));
  const contentTypeLine =
    body === undefined ? "" : 'headers["Content-Type"] = "application/json";';
  return `(async () => {
    const token = window.docurebuild?.apiToken;
    if (!token) throw new Error("The preload bridge token is unavailable");
    const headers = { Authorization: "Bearer " + token };
    ${contentTypeLine}
    const response = await fetch(${JSON.stringify(apiPath)}, {
      method: ${JSON.stringify(method)},
      headers,
      body: ${bodyExpression},
    });
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!response.ok) {
      throw new Error(${JSON.stringify(method)} + " " + ${JSON.stringify(apiPath)} + " -> " + response.status + " " + text.slice(0, 500));
    }
    return data;
  })()`;
}

function apiJson(cdp, method, apiPath, body) {
  return cdp.evaluate(apiExpression(method, apiPath, body));
}

function binaryExpression(method, apiPath, wantText) {
  return `(async () => {
    const token = window.docurebuild?.apiToken;
    if (!token) throw new Error("The preload bridge token is unavailable");
    const response = await fetch(${JSON.stringify(apiPath)}, {
      method: ${JSON.stringify(method)},
      headers: { Authorization: "Bearer " + token },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(${JSON.stringify(method)} + " " + ${JSON.stringify(apiPath)} + " -> " + response.status + " " + text.slice(0, 500));
    }
    const buffer = await response.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    const head = Array.from(bytes.slice(0, 8));
    let binary = "";
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
    }
    return {
      status: response.status,
      content_type: response.headers.get("content-type"),
      size: bytes.length,
      head,
      text: ${wantText ? 'new TextDecoder("utf-8").decode(bytes)' : '""'},
      base64: btoa(binary),
    };
  })()`;
}

function apiBinary(cdp, method, apiPath, wantText = false) {
  return cdp.evaluate(binaryExpression(method, apiPath, wantText));
}

function restoreExpression(base64, filename) {
  return `(async () => {
    const token = window.docurebuild?.apiToken;
    if (!token) throw new Error("The preload bridge token is unavailable");
    const binary = atob(${JSON.stringify(base64)});
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    const form = new FormData();
    form.append("file", new File([bytes], ${JSON.stringify(filename)}, { type: "application/zip" }));
    const response = await fetch("/api/projects/restore", {
      method: "POST",
      headers: { Authorization: "Bearer " + token },
      body: form,
    });
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!response.ok) {
      throw new Error("POST /api/projects/restore -> " + response.status + " " + text.slice(0, 500));
    }
    return data;
  })()`;
}

async function setImportFile(cdp, fixturePath) {
  const documentInfo = await cdp.send("DOM.getDocument", {
    depth: -1,
    pierce: true,
  });
  const { nodeId } = await cdp.send("DOM.querySelector", {
    nodeId: documentInfo.root.nodeId,
    selector: '[data-testid="import-input"]',
  });
  if (!nodeId) throw new Error("The import file input was not found");
  await cdp.send("DOM.setFileInputFiles", {
    nodeId,
    files: [fixturePath],
  });
}

async function startUiImport(cdp, projectId, fixturePath) {
  await setImportFile(cdp, fixturePath);
  try {
    return await waitUntil(
      async () => {
        const jobs = await apiJson(
          cdp,
          "GET",
          `/api/projects/${projectId}/imports`,
        );
        return jobs.length > 0 ? jobs : null;
      },
      5000,
      "import job creation",
    );
  } catch {
    await cdp.evaluate(`(() => {
      const input = document.querySelector('[data-testid="import-input"]');
      if (!input) return false;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    })()`);
    return waitUntil(
      async () => {
        const jobs = await apiJson(
          cdp,
          "GET",
          `/api/projects/${projectId}/imports`,
        );
        return jobs.length > 0 ? jobs : null;
      },
      15000,
      "import job creation after change event",
    );
  }
}

function readLogTail(filePath, maxLines = 80) {
  try {
    if (!fs.existsSync(filePath)) return [];
    const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
    return lines.slice(-maxLines).filter((line) => line.length > 0);
  } catch {
    return [];
  }
}

function displayPath(target) {
  const relative = path.relative(repoRoot, target);
  if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join("/");
  }
  return path.basename(target);
}

function sanitizeErrorText(value, workRoot) {
  return String(value)
    .split(repoRoot)
    .join("<repo>")
    .split(workRoot)
    .join("<work>")
    .split(os.tmpdir())
    .join("<temp>");
}

function collectLogTails(directories) {
  const candidates = [
    {
      label: "backend",
      path: path.join(directories.appData, "DocuRebuild", "logs", "backend.log"),
    },
    {
      label: "backend_local",
      path: path.join(
        directories.localAppData,
        "DocuRebuild",
        "logs",
        "backend.log",
      ),
    },
    { label: "electron", path: directories.electronLog },
  ];
  const tails = {};
  for (const candidate of candidates) {
    const tail = readLogTail(candidate.path);
    if (tail.length > 0) tails[candidate.label] = tail;
  }
  return tails;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const appPath = options.app ?? findDefaultApp();
  const resources = resolveResources(appPath, options.resources);
  const directories = createWorkRoot();
  const fixturePath = path.join(directories.root, "smoke.pdf");
  fs.writeFileSync(fixturePath, buildSmokePdf());

  const startedAt = Date.now();
  const report = {
    schema_version: 1,
    recorded_at: new Date(startedAt).toISOString(),
    result: "running",
    duration_ms: 0,
    machine: {
      platform: process.platform,
      release: os.release(),
      arch: process.arch,
      cpu: os.cpus()[0]?.model ?? "unknown",
      logical_cores: os.cpus().length,
      memory_gb: Math.round((os.totalmem() / 1024 ** 3) * 10) / 10,
      node: process.version,
    },
    app: {
      path: displayPath(appPath),
      resources: displayPath(resources),
      version: null,
      platform: null,
      sidecar_pids: [],
    },
    checks: {},
    steps: [],
    diagnostics: {
      console_errors: [],
      uncaught_exceptions: [],
      log_tails: {},
    },
  };

  const consoleErrors = [];
  const uncaughtExceptions = [];
  let child = null;
  let cdp = null;
  let logFd = null;
  let currentStep = "startup";

  const step = async (name, action) => {
    currentStep = name;
    const stepStarted = Date.now();
    try {
      const value = await action();
      report.steps.push({
        name,
        status: "passed",
        duration_ms: Date.now() - stepStarted,
      });
      console.log(`[smoke] pass ${name}`);
      return value;
    } catch (error) {
      report.steps.push({
        name,
        status: "failed",
        duration_ms: Date.now() - stepStarted,
        error: error.message,
      });
      throw error;
    }
  };

  try {
    const debugPort = 9300 + Math.floor(Math.random() * 300);
    const environment = {
      ...process.env,
      APPDATA: directories.appData,
      LOCALAPPDATA: directories.localAppData,
      TEMP: directories.temp,
      TMP: directories.temp,
      DOCUREBUILD_DATA_DIR: directories.data,
    };
    const packagedResources = path.join(path.dirname(appPath), "resources");
    if (resources !== packagedResources) {
      environment.DOCUREBUILD_DESKTOP_RESOURCES = resources;
    }

    logFd = fs.openSync(directories.electronLog, "a");
    child = spawn(appPath, [`--remote-debugging-port=${debugPort}`], {
      cwd: path.dirname(appPath),
      env: environment,
      stdio: ["ignore", logFd, logFd],
      windowsHide: false,
    });

    const target = await waitForCdpTarget(debugPort, 45000, child);
    cdp = new Cdp(target.webSocketDebuggerUrl);
    await cdp.connect();
    cdp.onEvent((message) => {
      if (message.method === "Runtime.exceptionThrown") {
        const details = message.params?.exceptionDetails;
        uncaughtExceptions.push(
          details?.exception?.description ?? details?.text ?? "Uncaught exception",
        );
      } else if (
        message.method === "Log.entryAdded" &&
        message.params?.entry?.level === "error"
      ) {
        consoleErrors.push(message.params.entry.text);
      } else if (
        message.method === "Runtime.consoleAPICalled" &&
        message.params?.type === "error"
      ) {
        consoleErrors.push(
          (message.params.args ?? [])
            .map((argument) => argument.value ?? argument.description ?? "")
            .join(" "),
        );
      }
    });
    await cdp.send("Runtime.enable");
    await cdp.send("Log.enable");
    await cdp.send("Page.enable");
    await cdp.send("DOM.enable");
    try {
      await cdp.send("Page.bringToFront");
    } catch {
      console.warn("[smoke] Page.bringToFront was unavailable");
    }
    try {
      await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true });
    } catch {
      console.warn("[smoke] Focus emulation was unavailable");
    }
    await cdp.evaluate("window.focus(); true").catch(() => {});

    await step("launch and authenticate", async () => {
      const bridge = await waitForEval(
        cdp,
        `(() => {
          const value = window.docurebuild;
          return value && value.apiToken
            ? { version: value.version, platform: value.platform, token_present: true }
            : null;
        })()`,
        45000,
        "preload bridge",
      );
      report.app.version = bridge.version;
      report.app.platform = bridge.platform;
      const health = await apiJson(cdp, "GET", "/api/health");
      if (health.status !== "ok") {
        throw new Error(`Unexpected health status: ${health.status}`);
      }
      report.checks.health = {
        status: health.status,
        version: health.version,
        database: health.database,
      };
    });

    const project = await step("create project", async () => {
      const created = await apiJson(cdp, "POST", "/api/projects", {
        name: `Desktop smoke ${Date.now()}`,
      });
      if (!created?.id) throw new Error("Project creation returned no id");
      report.checks.project = {
        id: created.id,
        name: created.name,
      };
      return created;
    });

    await step("open workspace", async () => {
      await cdp.evaluate(
        `window.location.assign(${JSON.stringify(`/projects/${project.id}`)}); true`,
      );
      await waitForEval(
        cdp,
        `Boolean(document.querySelector(".ProseMirror"))`,
        45000,
        "workspace editor",
      );
      await waitForEval(
        cdp,
        `Boolean(document.querySelector('[data-testid="import-input"]'))`,
        45000,
        "import file input",
      );
    });

    const pages = await step("import PDF through the UI", async () => {
      await startUiImport(cdp, project.id, fixturePath);
      const job = await waitUntil(
        async () => {
          const jobs = await apiJson(
            cdp,
            "GET",
            `/api/projects/${project.id}/imports`,
          );
          const latest = jobs[0];
          return latest &&
            ["succeeded", "failed", "cancelled"].includes(latest.status)
            ? latest
            : null;
        },
        180000,
        "import job completion",
      );
      if (job.status !== "succeeded") {
        throw new Error(
          `Import ${job.status}: ${job.error ?? job.error_code ?? "unknown error"}`,
        );
      }
      const importedPages = await waitUntil(
        async () => {
          const list = await apiJson(
            cdp,
            "GET",
            `/api/projects/${project.id}/pages`,
          );
          return list.length > 0 && list.every((page) => page.original_asset_id)
            ? list
            : null;
        },
        60000,
        "imported pages",
      );
      report.checks.import = {
        job_id: job.id,
        status: job.status,
        imported_pages: job.imported_pages,
        pages: importedPages.length,
      };
      return importedPages;
    });

    const page = pages[0];

    await step("render source page", async () => {
      const image = await waitForEval(
        cdp,
        `(() => {
          const image = document.querySelector('[data-testid="source-page-image"]');
          if (!image || !image.complete || image.naturalWidth <= 0) return null;
          return {
            natural_width: image.naturalWidth,
            natural_height: image.naturalHeight,
            alt: image.alt,
          };
        })()`,
        60000,
        "source page image",
      );
      const thumbnailPresent = await cdp.evaluate(
        `document.querySelectorAll('img[alt=""]').length > 0`,
      );
      if (!thumbnailPresent) throw new Error("Page thumbnail did not render");
      report.checks.render = {
        source_width: image.natural_width,
        source_height: image.natural_height,
        thumbnail_present: thumbnailPresent,
      };
    });

    const ocrRun = await step("run OCR and mark blocks reviewed", async () => {
      const started = await apiJson(
        cdp,
        "POST",
        `/api/projects/${project.id}/pages/${page.id}/ocr`,
        { languages: ["eng"] },
      );
      const run = await waitUntil(
        async () => {
          const current = await apiJson(
            cdp,
            "GET",
            `/api/projects/${project.id}/ocr/runs/${started.id}`,
          );
          return ["succeeded", "failed", "cancelled"].includes(current.status)
            ? current
            : null;
        },
        180000,
        "OCR run completion",
      );
      if (run.status !== "succeeded") {
        throw new Error(
          `OCR ${run.status}: ${run.error ?? run.error_code ?? "unknown error"}`,
        );
      }
      if (options.requireOcr && run.engine !== "tesseract") {
        throw new Error(
          `Expected bundled Tesseract, but OCR ran with engine "${run.engine}"`,
        );
      }
      if (!run.text.trim()) throw new Error("OCR returned empty text");
      if (!run.blocks?.length) throw new Error("OCR returned no reviewable blocks");

      for (const block of run.blocks) {
        await apiJson(
          cdp,
          "PATCH",
          `/api/projects/${project.id}/pages/${page.id}/ocr/blocks/${block.id}`,
          { verified: true },
        );
      }
      const reviewed = await apiJson(
        cdp,
        "GET",
        `/api/projects/${project.id}/ocr/runs/${run.id}`,
      );
      if (!reviewed.blocks.every((block) => block.verified)) {
        throw new Error("Not every OCR block was marked reviewed");
      }
      report.checks.ocr = {
        run_id: run.id,
        engine: run.engine,
        engine_version: run.engine_version,
        languages: run.languages,
        blocks: reviewed.blocks.length,
        verified_blocks: reviewed.blocks.filter((block) => block.verified).length,
        mean_confidence: run.mean_confidence,
        text_preview: run.text.slice(0, 200),
      };
      return reviewed;
    });

    await step("review and insert OCR in the dialog", async () => {
      const opened = await cdp.evaluate(`(() => {
        const button = document.querySelector('[data-testid="ocr-open"]');
        if (!button) return false;
        button.click();
        return true;
      })()`);
      if (!opened) throw new Error("The OCR dialog button was not found");
      await waitForEval(
        cdp,
        `Boolean(document.querySelector('[data-testid="ocr-insert"]'))`,
        30000,
        "OCR dialog",
      );
      await waitForEval(
        cdp,
        `(() => {
          const button = document.querySelector('[data-testid="ocr-insert"]');
          return button && !button.disabled ? true : null;
        })()`,
        30000,
        "OCR insert button",
      );
      const clicked = await cdp.evaluate(`(() => {
        const button = document.querySelector('[data-testid="ocr-insert"]');
        if (!button) return false;
        button.click();
        return true;
      })()`);
      if (!clicked) throw new Error("The OCR insert button could not be clicked");
      const editorText = await waitForEval(
        cdp,
        `(() => {
          const editor = document.querySelector(".ProseMirror");
          const text = editor?.innerText ?? "";
          return text.trim().length > 0 ? text : null;
        })()`,
        30000,
        "OCR text insertion",
      );
      report.checks.ocr_insert = {
        run_id: ocrRun.id,
        characters: editorText.length,
      };
    });

    const marker = `DOCUREBUILDSMOKEEDIT${Date.now()}`;
    await step("edit and autosave", async () => {
      await waitForEval(
        cdp,
        `Boolean(document.querySelector('.ProseMirror[contenteditable="true"]'))`,
        30000,
        "editable document",
      );
      await cdp.evaluate(`(() => {
        const editor = document.querySelector(".ProseMirror");
        if (!editor) return false;
        editor.focus();
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(editor);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
        return true;
      })()`);
      await cdp.send("Input.insertText", { text: `\n\n${marker}` });
      const saved = await waitUntil(
        async () => {
          const document = await apiJson(
            cdp,
            "GET",
            `/api/projects/${project.id}/document`,
          );
          return document.plain_text.includes(marker) ? document : null;
        },
        30000,
        "autosave",
      );
      report.checks.edit = {
        marker,
        plain_text_length: saved.plain_text.length,
      };
    });

    await step("reopen and restore saved text", async () => {
      await cdp.send("Page.reload", { ignoreCache: true });
      await waitForEval(
        cdp,
        `Boolean(document.querySelector(".ProseMirror"))`,
        45000,
        "editor after reload",
      );
      const text = await waitForEval(
        cdp,
        `(() => {
          const editor = document.querySelector(".ProseMirror");
          const value = editor?.innerText ?? "";
          return value.includes(${JSON.stringify(marker)}) ? value : null;
        })()`,
        45000,
        "saved marker after reload",
      );
      report.checks.reopen = {
        marker_present: true,
        characters: text.length,
      };
    });

    await step("export Markdown, text, Word and PDF", async () => {
      const exports = {};
      for (const format of ["markdown", "txt", "docx", "pdf"]) {
        const result = await apiBinary(
          cdp,
          "GET",
          `/api/projects/${project.id}/document/export?format=${format}`,
          format === "markdown" || format === "txt",
        );
        if (result.size <= 0) throw new Error(`${format} export is empty`);
        if (
          (format === "markdown" || format === "txt") &&
          !result.text.includes(marker)
        ) {
          throw new Error(`${format} export does not contain the saved marker`);
        }
        if (format === "pdf") {
          const magic = String.fromCharCode(...result.head.slice(0, 4));
          if (magic !== "%PDF") throw new Error("PDF export has no %PDF header");
        }
        if (format === "docx") {
          if (result.head[0] !== 0x50 || result.head[1] !== 0x4b) {
            throw new Error("DOCX export has no ZIP header");
          }
        }
        exports[format] = {
          size: result.size,
          content_type: result.content_type,
          marker_present:
            format === "markdown" || format === "txt"
              ? result.text.includes(marker)
              : null,
        };
      }
      report.checks.exports = exports;
    });

    await step("back up and restore into a new project", async () => {
      const backup = await apiBinary(
        cdp,
        "GET",
        `/api/projects/${project.id}/backup`,
      );
      if (backup.size <= 0) throw new Error("Backup archive is empty");
      if (backup.head[0] !== 0x50 || backup.head[1] !== 0x4b) {
        throw new Error("Backup archive has no ZIP header");
      }
      const restored = await cdp.evaluate(
        restoreExpression(backup.base64, "desktop-smoke-backup.zip"),
      );
      if (!restored?.id) throw new Error("Restore returned no project id");
      if (restored.id === project.id) {
        throw new Error("Restore reused the original project id");
      }
      const restoredPages = await waitUntil(
        async () => {
          const list = await apiJson(
            cdp,
            "GET",
            `/api/projects/${restored.id}/pages`,
          );
          return list.length > 0 ? list : null;
        },
        30000,
        "restored pages",
      );
      const restoredDocument = await waitUntil(
        async () => {
          const document = await apiJson(
            cdp,
            "GET",
            `/api/projects/${restored.id}/document`,
          );
          return document.plain_text.includes(marker) ? document : null;
        },
        30000,
        "restored document text",
      );
      report.checks.backup_restore = {
        backup_bytes: backup.size,
        restored_project_id: restored.id,
        restored_pages: restoredPages.length,
        marker_present: restoredDocument.plain_text.includes(marker),
      };
    });

    await step("close the app and stop the sidecar", async () => {
      const snapshot = getProcessSnapshot();
      const descendants = descendantPids(snapshot, child.pid);
      const sidecars = descendants
        .map((pid) =>
          snapshot.find((processInfo) => Number(processInfo.ProcessId) === pid),
        )
        .filter((processInfo) => {
          if (!processInfo) return false;
          const name = String(processInfo.Name ?? "").toLowerCase();
          const command = String(processInfo.CommandLine ?? "").toLowerCase();
          return (
            name.includes("docurebuild-backend") ||
            command.includes("docurebuild-backend") ||
            command.includes("desktop_server")
          );
        });
      if (sidecars.length === 0) {
        throw new Error("The bundled backend sidecar was not found");
      }
      report.app.sidecar_pids = sidecars.map((processInfo) =>
        Number(processInfo.ProcessId),
      );

      // Closing the window tears down the DevTools socket, so the in-flight
      // evaluate can reject with a connection-closed error. That is the
      // expected outcome of a successful close; the real assertion is that the
      // Electron process (and its sidecar) actually exit below.
      try {
        await cdp.evaluate("window.close(); true");
      } catch (error) {
        const message = String(error?.message ?? error);
        if (!/DevTools connection closed|not open/i.test(message)) {
          throw error;
        }
      }
      const exited = await waitForChildExit(child, 20000);
      if (!exited) throw new Error("The Electron process did not exit");

      await waitUntil(
        async () => {
          const after = getProcessSnapshot();
          const alive = sidecars.filter((processInfo) =>
            after.some(
              (item) =>
                Number(item.ProcessId) === Number(processInfo.ProcessId),
            ),
          );
          return alive.length === 0 ? true : null;
        },
        15000,
        "sidecar shutdown",
      );
      report.checks.shutdown = {
        electron_exit_code: child.exitCode,
        sidecar_pids: report.app.sidecar_pids,
        sidecar_stopped: true,
      };
    });

    report.result = "passed";
  } catch (error) {
    report.result = "failed";
    report.failure = {
      step: currentStep,
      message: sanitizeErrorText(error.message, directories.root),
      stack: error.stack
        ? sanitizeErrorText(error.stack, directories.root)
        : undefined,
    };
    if (cdp) {
      try {
        const screenshot = await cdp.send("Page.captureScreenshot", {
          format: "png",
        });
        if (screenshot?.data) {
          const screenshotPath = path.join(
            path.dirname(options.out),
            "desktop-smoke-failure.png",
          );
          fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
          fs.writeFileSync(
            screenshotPath,
            Buffer.from(screenshot.data, "base64"),
          );
          report.diagnostics.screenshot = displayPath(screenshotPath);
        }
      } catch {
        report.diagnostics.screenshot = null;
      }
    }
  } finally {
    report.recorded_at = new Date().toISOString();
    report.duration_ms = Date.now() - startedAt;
    report.diagnostics.console_errors = consoleErrors.slice(-20);
    report.diagnostics.uncaught_exceptions = uncaughtExceptions.slice(-20);
    report.diagnostics.log_tails = collectLogTails(directories);

    if (cdp) cdp.close();
    if (child && child.exitCode === null) {
      killProcessTree(child.pid);
      await waitForChildExit(child, 5000);
    }
    if (logFd !== null) {
      try {
        fs.closeSync(logFd);
      } catch {
        logFd = null;
      }
    }

    fs.mkdirSync(path.dirname(options.out), { recursive: true });
    fs.writeFileSync(options.out, `${JSON.stringify(report, null, 2)}\n`);
    console.log(`[smoke] report ${options.out}`);

    if (options.keep || report.result !== "passed") {
      console.log(`[smoke] work directory ${directories.root}`);
    } else {
      fs.rmSync(directories.root, { recursive: true, force: true });
    }

    if (report.result !== "passed") {
      console.error(
        `[smoke] failed at "${report.failure?.step}": ${report.failure?.message}`,
      );
      process.exitCode = 1;
    } else {
      console.log(`[smoke] passed in ${Math.round(report.duration_ms / 1000)}s`);
    }
  }
}

main().catch((error) => {
  console.error(`[smoke] fatal: ${error.stack ?? error.message}`);
  process.exitCode = 1;
});
