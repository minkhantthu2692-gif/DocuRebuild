# -*- mode: python ; coding: utf-8 -*-
"""Bundle the local API as a windowed desktop sidecar.

The sidecar is one-folder rather than one-file: startup stays fast, the
installer can update individual files, and PyMuPDF's shared libraries keep
their expected layout. Alembic configuration and migrations are copied beside
the application package so ``run_migrations`` finds them at runtime.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

backend_dir = os.path.dirname(os.path.abspath(SPEC))

datas = [
    (os.path.join(backend_dir, "alembic.ini"), "."),
    (os.path.join(backend_dir, "alembic"), "alembic"),
]
datas += collect_data_files("docx")
datas += collect_data_files("latex2mathml")
datas += collect_data_files("mathml2omml")

pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all("pymupdf")
datas += pymupdf_datas
binaries = pymupdf_binaries

hiddenimports = [
    "app.main",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("alembic")
# fontTools loads many table and codec modules lazily, and WOFF2 needs brotli.
hiddenimports += collect_submodules("fontTools")
hiddenimports += ["brotli"]
hiddenimports += pymupdf_hidden

analysis = Analysis(
    [os.path.join(backend_dir, "desktop_server.py")],
    pathex=[backend_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter", "matplotlib", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="docurebuild-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="backend",
)
