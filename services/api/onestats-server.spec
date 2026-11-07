# PyInstaller spec for the standalone OneStats backend sidecar (onestats-server).
#
# Produces a windowed (no console) ONEDIR build: a folder `dist/onestats-server/` containing
# onestats-server.exe plus its dependencies. Onedir (not onefile) is deliberate: a onefile exe
# unpacks to a temp folder and re-executes at runtime, which fails intermittently when the exe is
# spawned by a GUI process with no console (and trips antivirus on the extracted DLLs). Onedir has no
# runtime extraction, so it starts reliably when the desktop app launches it.
#
# It bundles the FastAPI app, the Alembic migrations (as data, loaded dynamically), and the runtime
# deps (uvicorn, psycopg, alembic, reportlab, cryptography). Build:
#   cd services/api && ./.venv/Scripts/python -m PyInstaller onestats-server.spec --noconfirm
# Output: services/api/dist/onestats-server/onestats-server.exe
#
# This bundles only free, open-source runtime dependencies — no paid services.

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
HERE = Path(SPECPATH)  # noqa: F821 - SPECPATH is injected by PyInstaller

# Alembic migrations are imported dynamically by Alembic at runtime, so PyInstaller won't follow them.
# Ship the whole migrations tree as data under the same package path the launcher resolves.
migrations_src = HERE / "onestats" / "db" / "migrations"
datas = [(str(migrations_src), "onestats/db/migrations")]
binaries = []
hiddenimports = collect_submodules("onestats")

# Pull data/binaries/submodules for packages that load things dynamically.
# pytesseract + PIL power Research Centre OCR: PIL loads its image-format plugins (incl. the MPO
# plugin the OCR preprocessing depends on) dynamically, and pytesseract is imported lazily, so both
# are collected explicitly to be sure the packaged backend can run OCR rather than silently falling
# back to manual transcription. The Tesseract binary itself stays external (optional on the host).
for pkg in ("uvicorn", "psycopg", "psycopg_binary", "alembic", "reportlab", "pytesseract", "PIL"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Belt-and-braces hidden imports for uvicorn's dynamically-selected implementations.
hiddenimports += [
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl", "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan", "uvicorn.lifespan.on",
    "anyio._backends._asyncio",
]

a = Analysis(
    ["onestats_server_main.py"],
    pathex=[str(HERE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyInstaller"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ONEDIR: a thin EXE (exclude_binaries) + a COLLECT folder holding the deps on disk — no runtime
# extraction, so it launches reliably when spawned by the GUI app.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="onestats-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # no console window when launched as a sidecar
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="onestats-server",
)
