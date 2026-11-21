/**
 * Build the bundled OCR runtime without administrator rights.
 *
 * The official Tesseract for Windows build is an NSIS installer. Winget can
 * download it, but installing it system-wide needs elevation, so this script
 * extracts the already-downloaded installer with standalone 7-Zip tools into
 * the application resources. Only the engine, its shared libraries and the
 * English/Burmese language data are kept.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const destination = path.join(root, "dist", "desktop", "tesseract");
const cache = path.join(root, "dist", ".cache", "tesseract");
const tools = path.join(root, "dist", ".cache", "7zip");

const TESSERACT_VERSION = "5.4.0.20240606";
const TESSERACT_URL = `https://github.com/UB-Mannheim/tesseract/releases/download/v${TESSERACT_VERSION}/tesseract-ocr-w64-setup-${TESSERACT_VERSION}.exe`;
const SEVEN_ZIPR_URL = "https://www.7-zip.org/a/7zr.exe";
const SEVEN_ZIP_FULL_URL = "https://www.7-zip.org/a/7z2501-x64.exe";
const MYA_URL =
  "https://github.com/tesseract-ocr/tessdata_fast/raw/main/mya.traineddata";
const APACHE_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt";

function log(message) {
  process.stdout.write(`[tesseract] ${message}\n`);
}

async function download(url, target) {
  if (fs.existsSync(target) && fs.statSync(target).size > 0) {
    log(`cached ${path.basename(target)}`);
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  log(`downloading ${url}`);
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok || !response.body) {
    throw new Error(`Download failed (${response.status}): ${url}`);
  }
  const temporary = `${target}.part`;
  await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(temporary));
  fs.renameSync(temporary, target);
  log(`saved ${path.basename(target)} (${fs.statSync(target).size} bytes)`);
}

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`${command} failed with exit code ${result.status}`);
  }
}

function copy(source, target) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
}

export async function prepareTesseract() {
  const engine = path.join(destination, "tesseract.exe");
  const languages = path.join(destination, "tessdata");
  const license = path.join(destination, "LICENSE-tesseract.txt");
  if (
    fs.existsSync(engine) &&
    fs.existsSync(path.join(languages, "eng.traineddata")) &&
    fs.existsSync(path.join(languages, "mya.traineddata")) &&
    fs.existsSync(license)
  ) {
    log("bundled runtime already present");
    return engine;
  }

  const setup = path.join(cache, "tesseract-setup.exe");
  const zipr = path.join(tools, "7zr.exe");
  const zipFull = path.join(tools, "7z-full.exe");
  const sevenZip = path.join(tools, "full", "7z.exe");
  const extracted = path.join(cache, "extracted");

  await download(TESSERACT_URL, setup);
  await download(SEVEN_ZIPR_URL, zipr);
  await download(SEVEN_ZIP_FULL_URL, zipFull);

  if (!fs.existsSync(sevenZip)) {
    log("unpacking 7-Zip tools");
    run(zipr, ["x", zipFull, `-o${path.join(tools, "full")}`, "-y"]);
  }

  if (!fs.existsSync(extracted)) {
    log("extracting Tesseract");
    run(sevenZip, ["x", setup, `-o${extracted}`, "-y"]);
  }

  fs.mkdirSync(destination, { recursive: true });
  copy(path.join(extracted, "tesseract.exe"), engine);
  for (const entry of fs.readdirSync(extracted)) {
    if (entry.toLowerCase().endsWith(".dll")) {
      copy(path.join(extracted, entry), path.join(destination, entry));
    }
  }
  copy(
    path.join(extracted, "tessdata", "eng.traineddata"),
    path.join(languages, "eng.traineddata"),
  );
  copy(
    path.join(extracted, "tessdata", "osd.traineddata"),
    path.join(languages, "osd.traineddata"),
  );
  const pdfFont = path.join(extracted, "tessdata", "pdf.ttf");
  if (fs.existsSync(pdfFont)) {
    copy(pdfFont, path.join(languages, "pdf.ttf"));
  }

  const mya = path.join(languages, "mya.traineddata");
  await download(MYA_URL, mya);

  // The installer already ships the Apache-2.0 text, so the build does not need
  // a second network request for it.
  const bundledLicense = path.join(extracted, "doc", "LICENSE");
  if (fs.existsSync(bundledLicense)) {
    copy(bundledLicense, license);
  } else {
    await download(APACHE_LICENSE_URL, license);
  }

  const version = spawnSync(engine, ["--version"], { encoding: "utf8" });
  if (version.status !== 0) {
    throw new Error("The extracted Tesseract executable could not run.");
  }
  log(version.stdout.split("\n")[0].trim());

  const listed = spawnSync(
    engine,
    ["--tessdata-dir", languages, "--list-langs"],
    { encoding: "utf8" },
  );
  if (listed.status !== 0) {
    throw new Error(`Tesseract could not read its language data: ${listed.stderr}`);
  }
  const available = listed.stdout.split(/\r?\n/).filter(Boolean);
  for (const language of ["eng", "mya", "osd"]) {
    if (!available.includes(language)) {
      throw new Error(`The bundled Tesseract is missing ${language}.`);
    }
  }
  log(`languages: ${available.join(", ")}`);
  return engine;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await prepareTesseract();
}
