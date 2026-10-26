"""Frozen entry point for the packaged standalone OneStats backend (the Tauri sidecar).

Kept tiny on purpose: all orchestration lives in onestats.standalone.launcher. PyInstaller freezes
this into `onestats-server.exe`, which the desktop app launches on startup.
"""

from __future__ import annotations

import multiprocessing
import sys

from onestats.standalone.launcher import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # safe no-op; guards against spawn recursion if ever used
    sys.exit(main())
