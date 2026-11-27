/**
 * Editor performance drill for the packaged Electron shell.
 *
 * Launches the built desktop application against a disposable data folder,
 * creates a project through the real preload-token API, opens the workspace,
 * types a long document through the DevTools input pipeline and measures
 * typing, autosave, reopen and export latency. The window is then closed and
 * the remaining shell/sidecar processes are counted.
 *
 * Usage (repository root):
 *   node scripts/performance-editor-drill.mjs \
 *     --out docs/performance/editor-drill.json
 */

import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

function parseArgs(argv) {
  const options = {
    app: path.join(root, "dist", "desktop-installer", "win-unpacked", "DocuRebuild.exe"),
    resources: path.join(root, "dist", "desktop"),
    out: path.join(root, "docs", "performance", "editor-drill.json"),
    chunks: 120,
    chunkSize: 1200,
    keep: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--app") options.app = path.resolve(argv[++index]);
    else if (arg === "--resources") options.resources = path.resolve(argv[++index]);
    else if (arg === "--out") options.out = path.resolve(argv[++index]);
    else if (arg === "--chunks") options.chunks = Number(argv[++index]);
    else if (arg === "--chunk-size") options.chunkSize = Number(argv[++index]);
    else if (arg === "--keep") options.keep = true;
  }
  return options;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = spawn("node", [
      "-e",
      "const net=require('net');const s=net.createServer();s.listen(0,'127.0.0.1',()=>{console.log(s.address().port);s.close();});",
    ]);
    let output = "";
    server.stdout.on("data", (chunk) => {
      output += chunk;
    });
    server.on("error", reject);
    server.on("exit", () => resolve(Number(output.trim())));
  });
}

function processRows(imageName) {
  try {
    const output = execFileSync(
      "tasklist",
      ["/FI", `IMAGENAME eq ${imageName}`, "/FO", "CSV", "/NH"],
      { encoding: "utf8" },
    );
    return output
      .split(/\r?\n/)
      .filter((line) => line.startsWith('"'))
      .map((line) => {
        const [name, pid, , , memory] = line.split('","');
        return {
          name: name.replace(/^"|"$/g, ""),
          pid: Number(pid),
          workingSetMb: Number(memory?.replace(/[^0-9]/g, "")) / 1024 || null,
        };
      });
  } catch {
    return [];
  }
}

class Cdp {
  constructor(url) {
    this.url = url;
    this.id = 0;
    this.pending = new Map();
    this.ws = null;
  }

  async connect() {
    this.ws = new WebSocket(this.url);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id || !this.pending.has(message.id)) return;
      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
    });
  }

  send(method, params = {}) {
    this.id += 1;
    const id = this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(
        result.exceptionDetails.exception?.description ||
          result.exceptionDetails.text ||
          "Evaluation failed",
      );
    }
    return result.result.value;
  }

  close() {
    this.ws?.close();
  }
}

async function waitForPage(port, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await response.json();
      const page = targets.find((item) => item.type === "page");
      if (page) return page;
    } catch {
      // The debugger endpoint is not open yet.
    }
    await sleep(200);
  }
  throw new Error("The application did not expose a DevTools page");
}

async function waitFor(cdp, expression, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await cdp.evaluate(expression)) return true;
    await sleep(25);
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

function textChunk(index, size) {
  const words = [];
  let length = 0;
  let cursor = 0;
  while (length < size) {
    const word = `reconstruction${(index * 131 + cursor) % 997}`;
    words.push(word);
    length += word.length + 1;
    cursor += 1;
  }
  return words.join(" ");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (!fs.existsSync(options.app)) {
    throw new Error(`Application not found: ${options.app}`);
  }
  const workRoot = fs.mkdtempSync(path.join(os.tmpdir(), "docurebuild-editor-"));
  for (const name of ["appdata", "localappdata", "data", "logs"]) {
    fs.mkdirSync(path.join(workRoot, name), { recursive: true });
  }
  const port = await freePort();
  const environment = {
    ...process.env,
    APPDATA: path.join(workRoot, "appdata"),
    LOCALAPPDATA: path.join(workRoot, "localappdata"),
    DOCUREBUILD_DATA_DIR: path.join(workRoot, "data"),
    DOCUREBUILD_LOG_DIR: path.join(workRoot, "logs"),
    DOCUREBUILD_DESKTOP_RESOURCES: options.resources,
  };

  const started = Date.now();
  const child = spawn(options.app, [`--remote-debugging-port=${port}`], {
    env: environment,
    stdio: "ignore",
  });
  const result = {
    machine: {
      os: `${os.platform()} ${os.release()}`,
      cpu: os.cpus()[0]?.model ?? "unknown",
      logical_cores: os.cpus().length,
      ram_gb: Math.round(os.totalmem() / 1024 ** 3),
      app: path.relative(root, options.app).replaceAll("\\", "/"),
      recorded_at: new Date().toISOString(),
    },
    startup: {},
    typing: {},
    autosave: {},
    reopen: {},
    export: {},
    memory: {},
    shutdown: {},
  };

  let cdp = null;
  try {
    const page = await waitForPage(port);
    cdp = new Cdp(page.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send("Runtime.enable");
    await cdp.send("Performance.enable");
    await waitFor(cdp, "document.readyState === 'complete' && !!window.docurebuild", 90000);
    result.startup.shell_ready_seconds = (Date.now() - started) / 1000;
    result.startup.backend_port = new URL(page.url).port;
    result.startup.shell_processes = processRows("DocuRebuild.exe");
    result.startup.backend_processes = processRows("docurebuild-backend.exe");

    const project = await cdp.evaluate(`(async () => {
      const token = window.docurebuild.apiToken;
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({ name: "Editor performance", description: "" }),
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    })()`);
    const projectId = project.id;

    const navigationStarted = Date.now();
    await cdp.evaluate(`
      history.pushState({}, "", "/projects/${projectId}");
      window.dispatchEvent(new PopStateEvent("popstate"));
      true;
    `);
    await waitFor(cdp, "!!document.querySelector('.ProseMirror')", 60000);
    result.startup.workspace_ready_seconds = (Date.now() - navigationStarted) / 1000;

    await cdp.evaluate(`
      (() => {
        const editor = document.querySelector('.ProseMirror');
        editor.focus();
        const selection = window.getSelection();
        selection.selectAllChildren(editor);
        selection.collapseToEnd();
        return true;
      })()
    `);

    const metrics = async () => {
      const { metrics: values } = await cdp.send("Performance.getMetrics");
      const map = Object.fromEntries(values.map((entry) => [entry.name, entry.value]));
      const dom = await cdp.send("Memory.getDOMCounters");
      return {
        js_heap_used_mb: Math.round((map.JSHeapUsedSize / 1024 ** 2) * 10) / 10,
        js_heap_total_mb: Math.round((map.JSHeapTotalSize / 1024 ** 2) * 10) / 10,
        nodes: dom.nodes,
        documents: dom.documents,
        listeners: dom.jsEventListeners,
      };
    };

    result.memory.before_typing = await metrics();
    const samples = [];
    let expected = 0;
    let longest = 0;
    let total = 0;
    for (let index = 0; index < options.chunks; index += 1) {
      const chunk = textChunk(index, options.chunkSize);
      expected += chunk.length + 1;
      const before = Date.now();
      await cdp.send("Input.insertText", { text: `${chunk} ` });
      let length = 0;
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
        length = await cdp.evaluate(
          "(document.querySelector('.ProseMirror')?.textContent ?? '').length",
        );
        if (length >= expected - 2) break;
        await sleep(5);
      }
      const elapsed = Date.now() - before;
      total += elapsed;
      longest = Math.max(longest, elapsed);
      samples.push(elapsed);
      if ((index + 1) % 20 === 0) {
        result.memory[`after_${index + 1}_chunks`] = await metrics();
      }
    }
    result.typing = {
      chunks: options.chunks,
      chunk_size: options.chunkSize,
      characters: expected,
      total_seconds: Math.round((total / 1000) * 100) / 100,
      median_ms: Math.round(samples.sort((a, b) => a - b)[Math.floor(samples.length / 2)]),
      p95_ms: Math.round(samples[Math.floor(samples.length * 0.95)]),
      longest_ms: longest,
      editor_characters: await cdp.evaluate(
        "(document.querySelector('.ProseMirror')?.textContent ?? '').length",
      ),
    };
    result.memory.after_typing = await metrics();

    // Autosave: the editor waits 900 ms after the last change before saving.
    const autosaveStarted = Date.now();
    let savedCharacters = 0;
    const autosaveDeadline = Date.now() + 30000;
    while (Date.now() < autosaveDeadline) {
      savedCharacters = await cdp.evaluate(`(async () => {
        const token = window.docurebuild.apiToken;
        const response = await fetch("/api/projects/${projectId}/document", {
          headers: { Authorization: "Bearer " + token },
        });
        if (!response.ok) return 0;
        return (await response.json()).plain_text.length;
      })()`);
      if (savedCharacters >= expected - 10) break;
      await sleep(100);
    }
    result.autosave = {
      seconds_after_last_input: Math.round(((Date.now() - autosaveStarted) / 1000) * 100) / 100,
      stored_characters: savedCharacters,
      expected_characters: expected,
      saved: savedCharacters >= expected - 10,
    };

    // Reopen: a full page reload refetches the stored document.
    const reopenStarted = Date.now();
    await cdp.send("Page.enable");
    await cdp.send("Page.reload", { ignoreCache: false });
    await waitFor(cdp, "!!document.querySelector('.ProseMirror')", 60000);
    await waitFor(
      cdp,
      `(document.querySelector('.ProseMirror')?.textContent ?? '').length >= ${expected - 10}`,
      60000,
    );
    result.reopen = {
      seconds: Math.round(((Date.now() - reopenStarted) / 1000) * 100) / 100,
      editor_characters: await cdp.evaluate(
        "(document.querySelector('.ProseMirror')?.textContent ?? '').length",
      ),
    };
    result.memory.after_reopen = await metrics();

    for (const format of ["markdown", "docx", "pdf"]) {
      const exported = await cdp.evaluate(`(async () => {
        const token = window.docurebuild.apiToken;
        const started = performance.now();
        const response = await fetch("/api/projects/${projectId}/document/export?format=${format}", {
          headers: { Authorization: "Bearer " + token },
        });
        const body = await response.blob();
        return { ok: response.ok, bytes: body.size, ms: performance.now() - started };
      })()`);
      result.export[format] = {
        bytes: exported.bytes,
        milliseconds: Math.round(exported.ms),
        ok: exported.ok,
      };
    }

    const shutdownStarted = Date.now();
    await cdp.evaluate("window.close(); true").catch(() => {});
    const exited = await Promise.race([
      new Promise((resolve) => child.once("exit", () => resolve(true))),
      sleep(15000).then(() => false),
    ]);
    await sleep(2500);
    result.shutdown = {
      window_close_seconds: Math.round(((Date.now() - shutdownStarted) / 1000) * 100) / 100,
      shell_exited: exited,
      remaining_shell_processes: processRows("DocuRebuild.exe").length,
      remaining_backend_processes: processRows("docurebuild-backend.exe").length,
      remaining_tesseract_processes: processRows("tesseract.exe").length,
    };

    if (options.keep) {
      result.disposable_root = workRoot;
    }
    fs.mkdirSync(path.dirname(options.out), { recursive: true });
    fs.writeFileSync(options.out, `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify(result, null, 2));
    console.log(`[editor-drill] wrote ${options.out}`);
  } finally {
    cdp?.close();
    if (child.exitCode === null) {
      child.kill();
      await sleep(1500);
    }
    if (!options.keep) {
      fs.rmSync(workRoot, { recursive: true, force: true });
    } else {
      console.log(`[editor-drill] kept ${workRoot}`);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
