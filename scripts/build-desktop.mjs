/**
 * Build the complete desktop payload: web client, Python sidecar and OCR
 * runtime. electron-builder then wraps `dist/desktop` into an installer.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { prepareTesseract } from "./prepare-tesseract.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist", "desktop");
const skip = new Set(process.argv.slice(2));
const isWindows = process.platform === "win32";

function log(message) {
  process.stdout.write(`[desktop] ${message}\n`);
}

function run(command, args, options = {}) {
  log(`${path.basename(command)} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    shell: isWindows && command.toLowerCase().endsWith(".cmd"),
    ...options,
  });
  if (result.status !== 0) {
    throw new Error(`${command} failed with exit code ${result.status}`);
  }
}

function venvPython() {
  return path.join(
    root,
    "backend",
    ".venv",
    isWindows ? "Scripts" : "bin",
    isWindows ? "python.exe" : "python",
  );
}

function ensureBackendToolchain() {
  let python = venvPython();
  if (!fs.existsSync(python)) {
    log("creating the backend virtual environment");
    const base = isWindows ? "python" : "python3";
    run(base, ["-m", "venv", path.join(root, "backend", ".venv")]);
    python = venvPython();
  }

  const probe = spawnSync(python, ["-c", "import PyInstaller"], {
    cwd: root,
    stdio: "ignore",
  });
  if (probe.status !== 0) {
    log("installing the desktop build dependencies");
    run(python, [
      "-m",
      "pip",
      "install",
      "--disable-pip-version-check",
      "-r",
      path.join(root, "backend", "requirements-desktop.txt"),
    ]);
  }
  return python;
}

function copyWebClient() {
  const source = path.join(root, "apps", "web", "dist");
  if (!fs.existsSync(path.join(source, "index.html"))) {
    throw new Error("The web build is missing. Run the web build first.");
  }
  const target = path.join(dist, "web");
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(source, target, { recursive: true });
  log(`copied web client to ${target}`);
}

function buildBackend(python) {
  const target = path.join(dist, "backend");
  fs.rmSync(target, { recursive: true, force: true });
  run(python, [
    "-m",
    "PyInstaller",
    path.join(root, "backend", "pyinstaller.spec"),
    "--noconfirm",
    "--clean",
    "--log-level",
    "WARN",
    "--distpath",
    dist,
    "--workpath",
    path.join(root, "backend", "build", "pyinstaller"),
  ]);
}

function verify() {
  const expected = [
    path.join(dist, "backend", "docurebuild-backend.exe"),
    path.join(dist, "web", "index.html"),
    path.join(dist, "tesseract", "tesseract.exe"),
    path.join(dist, "tesseract", "tessdata", "eng.traineddata"),
    path.join(dist, "tesseract", "tessdata", "mya.traineddata"),
  ];
  if (process.platform !== "win32") {
    expected[0] = path.join(dist, "backend", "docurebuild-backend");
  }
  for (const entry of expected) {
    if (!fs.existsSync(entry)) {
      throw new Error(`Expected desktop file is missing: ${entry}`);
    }
  }
  log("desktop payload verified");
}

async function main() {
  fs.mkdirSync(dist, { recursive: true });

  if (!skip.has("--skip-web")) {
    run(isWindows ? "npm.cmd" : "npm", ["run", "build", "-w", "@docurebuild/web"]);
  }
  copyWebClient();

  if (!skip.has("--skip-backend")) {
    const python = ensureBackendToolchain();
    buildBackend(python);
  }

  if (!skip.has("--skip-tesseract")) {
    await prepareTesseract();
  }

  verify();
  log(`ready at ${dist}`);
}

main().catch((error) => {
  process.stderr.write(`[desktop] ${error instanceof Error ? error.message : error}\n`);
  process.exitCode = 1;
});
