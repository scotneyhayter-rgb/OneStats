# PyInstaller spec for the standalone OneStats backend sidecar (onestats-server.exe).
#
# Produces a single-file, windowed (no console) executable the Tauri app launches on startup. It
# bundles the FastAPI app, the Alembic migrations (as data, since they are loaded dynamically), and
# the runtime deps (uvicorn, psycopg, alembic, reportlab, cryptography). Build:
#   cd services/api && ./.venv/Scripts/python -m PyInstaller onestats-server.spec --noconfirm
# Output: services/api/dist/onestats-server.exe
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
for pkg in ("uvicorn", "psycopg", "psycopg_binary", "alembic", "reportlab"):
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="onestats-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # no console window when launched as a sidecar
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
