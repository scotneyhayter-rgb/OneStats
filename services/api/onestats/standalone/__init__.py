"""Standalone (single-PC) packaging support for the OneStats desktop app.

This subpackage contains the self-starting backend launcher used when OneStats runs as a normal
Windows desktop application: the Tauri app spawns the packaged backend as a sidecar, which brings up
the local database connection, applies migrations and serves the API on the loopback interface — with
no terminal, no manually-started Python and no developer tools. See docs/75-standalone-windows.md.
"""
