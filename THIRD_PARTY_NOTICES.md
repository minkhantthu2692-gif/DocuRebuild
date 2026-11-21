# Third-party notices

DocuRebuild is distributed under the GNU Affero General Public License, version
3 or later (see `LICENSE`). The application bundles or links the components
below. Their licenses apply to those components, not to the project's own code.

This file lists the components that ship inside the desktop build. Build-time
only tools are listed separately because they are not redistributed.

## Application runtime

| Component | Version | License |
| --- | --- | --- |
| Electron | 45.4.1 | MIT |
| Chromium (inside Electron) | as shipped by Electron | BSD-3-Clause plus component licenses |
| Node.js runtime (inside Electron) | as shipped by Electron | MIT |

Electron's own license files, including `LICENSES.chromium.html`, are installed
next to the application executable by electron-builder.

## Web client

| Component | License |
| --- | --- |
| React, React DOM | MIT |
| React Router | MIT |
| TanStack Query | MIT |
| i18next, react-i18next | MIT |
| Tiptap (core, react, starter-kit, table, text-align, mathematics, placeholder) | MIT |
| ProseMirror (via Tiptap) | MIT |
| KaTeX | MIT |
| Radix UI primitives | MIT |
| lucide-react | ISC |
| Sonner | MIT |
| class-variance-authority, clsx, tailwind-merge | MIT |
| Tailwind CSS (compiled output) | MIT |

## Backend

| Component | Version | License |
| --- | --- | --- |
| FastAPI | 0.115.6 | MIT |
| Starlette | 0.41.3 | BSD-3-Clause |
| Uvicorn | 0.34.0 | BSD-3-Clause |
| SQLAlchemy | 2.0.36 | MIT |
| Alembic | 1.14.0 | MIT |
| Pydantic, pydantic-settings | 2.10.4 / 2.7.0 | MIT |
| python-multipart | 0.0.20 | Apache-2.0 |
| Pillow | 11.1.0 | MIT-CMU (HPND) |
| **PyMuPDF (MuPDF)** | **1.28.2** | **AGPL-3.0** |
| python-docx | 1.2.0 | MIT |
| latex2mathml | 3.81.1 | MIT |
| mathml2omml | 0.0.2 | MIT |
| cryptography | 44.0.0 | Apache-2.0 or BSD-3-Clause |
| platformdirs | 4.3.6 | MIT |
| greenlet | 3.5.6 | MIT |
| h11 | 0.16.0 | MIT |
| httptools | 0.9.0 | MIT |
| watchfiles | 1.3.0 | MIT |
| websockets | 17.4 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| Mako | 1.4.3 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| cffi | 2.1.1 | MIT |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| colorama | 0.4.6 | BSD-3-Clause |
| typing-extensions, annotated-types, idna, anyio, click | as pinned by the above | MIT / BSD-3-Clause / Apache-2.0 |

PyMuPDF is the reason DocuRebuild itself is AGPL-3.0: PyMuPDF is AGPL-3.0, and
an application that links it must be distributed under the same license. The
complete corresponding source for this build is the repository this file ships
with.

## OCR engine and data

| Component | Version | License |
| --- | --- | --- |
| Tesseract OCR (UB Mannheim Windows build) | 5.4.0.20240606 | Apache-2.0 |
| Leptonica | 1.84.1 | BSD-2-Clause |
| `eng.traineddata` | as shipped with Tesseract 5.4.0 | Apache-2.0 |
| `mya.traineddata` | `tessdata_fast` main | Apache-2.0 |
| `osd.traineddata` | as shipped with Tesseract 5.4.0 | Apache-2.0 |

The Tesseract Apache-2.0 license text is installed with the application at
`tesseract/LICENSE-tesseract.txt`, alongside the engine and its language data.

## Build-time only (not redistributed)

| Component | License |
| --- | --- |
| PyInstaller | GPL-2.0-or-later with the bootloader exception |
| electron-builder | MIT |
| 7-Zip standalone tools (used to unpack the Tesseract installer) | LGPL-2.1-or-later, unRAR restriction |
| Vite, TypeScript, ESLint, Vitest, Tailwind CLI | MIT |

## AI providers

DocuRebuild does not bundle any AI model or provider SDK. A user who configures
an AI connection talks to a provider they chose, under that provider's own terms
and pricing. Local Ollama models are downloaded by the user through Ollama.
