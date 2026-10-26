#!/usr/bin/env python3
"""Generate an OneStats release manifest + checksums for a built desktop package.

Part of the controlled release workflow (docs/74-update-system.md). This produces the machine-readable
release metadata the update system needs; it does NOT sign, upload or publish anything. Signing
(Tauri updater signature + optional Windows Authenticode) and hosting are separate, approval-gated
steps — this script leaves clearly-marked placeholders so a release can be staged for review first.

Usage:
  python scripts/build-release-manifest.py \
      --installer path/to/OneStats_x.y.z_x64-setup.exe \
      --channel stable \
      [--notes docs/RELEASE_NOTES.md] [--out dist/release]

It never embeds secrets, signing keys or connection strings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAURI_CONF = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
VERSION_PY = ROOT / "services" / "api" / "onestats" / "core" / "version.py"


def _read_desktop_version() -> str:
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    return str(conf["version"])


def _read_server_contract() -> dict[str, object]:
    """Pull the compatibility contract constants from core/version.py without importing it."""
    text = VERSION_PY.read_text(encoding="utf-8")

    def grab(name: str, default: str | None = None) -> str | None:
        m = re.search(rf'^{name}\s*[:=].*?["\']([^"\']+)["\']', text, re.MULTILINE)
        if m:
            return m.group(1)
        m2 = re.search(rf"^{name}\s*[:=]\s*(\d+)", text, re.MULTILINE)
        return m2.group(1) if m2 else default

    return {
        "server_version": grab("SERVER_VERSION"),
        "api_version": int(grab("API_VERSION", "1") or 1),
        "db_schema_head": grab("DB_SCHEMA_HEAD"),
        "db_schema_level": int(grab("DB_SCHEMA_LEVEL", "0") or 0),
        "min_desktop_version": grab("MIN_DESKTOP_VERSION"),
        "min_server_for_desktop": grab("MIN_SERVER_FOR_DESKTOP"),
    }


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _notes(notes_path: pathlib.Path | None, version: str) -> str:
    if notes_path and notes_path.exists():
        return notes_path.read_text(encoding="utf-8")[:4000]
    return f"OneStats {version}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build an OneStats release manifest + checksums.")
    ap.add_argument("--installer", required=True, help="Path to the built installer (.exe/.msi).")
    ap.add_argument("--channel", default="stable", choices=["stable", "testing"])
    ap.add_argument("--arch", default="x64")
    ap.add_argument("--notes", default=str(ROOT / "docs" / "RELEASE_NOTES.md"))
    ap.add_argument("--min-prior", default=None, help="Minimum prior desktop version that may upgrade to this one.")
    ap.add_argument("--out", default=str(ROOT / "dist" / "release"))
    args = ap.parse_args(argv)

    installer = pathlib.Path(args.installer)
    if not installer.exists():
        print(f"ERROR: installer not found: {installer}", file=sys.stderr)
        return 2

    version = _read_desktop_version()
    contract = _read_server_contract()
    checksum = _sha256(installer)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes = _notes(pathlib.Path(args.notes), version)

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Rich OneStats release manifest (our own metadata, incl. compatibility requirements).
    manifest = {
        "product": "OneStats Desktop",
        "version": version,
        "channel": args.channel,
        "arch": args.arch,
        "release_date": now,
        "installer_file": installer.name,
        "checksums": {"sha256": checksum},
        "size_bytes": installer.stat().st_size,
        "notes": notes,
        "compatibility": {
            "min_prior_desktop_version": args.min_prior,
            "required_server_min_version": contract["min_server_for_desktop"],
            "required_db_schema_head": contract["db_schema_head"],
            "required_db_schema_level": contract["db_schema_level"],
            "api_version": contract["api_version"],
        },
        # Filled by the signing step (approval-gated); verification fails until present in production.
        "signature": None,
        "signing": "PLACEHOLDER — run the Tauri updater signer; never commit private keys.",
    }
    (out_dir / "onestats-release.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 2) Tauri-updater latest.json skeleton (signature + download URL filled by signing/hosting steps).
    latest = {
        "version": version,
        "notes": notes.splitlines()[0] if notes else f"OneStats {version}",
        "pub_date": now,
        "platforms": {
            "windows-x86_64": {
                "signature": "PLACEHOLDER_TAURI_SIGNATURE",
                "url": "https://RELEASES.EXAMPLE/CONFIGURE_HOSTING/" + installer.name,
            }
        },
    }
    (out_dir / "latest.json").write_text(json.dumps(latest, indent=2), encoding="utf-8")

    # 3) Plain checksums file.
    (out_dir / "SHA256SUMS.txt").write_text(f"{checksum}  {installer.name}\n", encoding="utf-8")

    print(f"Wrote release metadata to {out_dir}")
    print(f"  version={version} channel={args.channel} sha256={checksum[:16]}…")
    print("  NOTE: signature and download URL are placeholders — signing & hosting are separate,")
    print("        approval-gated steps (see docs/74-update-system.md). Do not publish unsigned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
