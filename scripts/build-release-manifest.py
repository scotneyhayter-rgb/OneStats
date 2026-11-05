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
      --github-repo OWNER/REPO \
      --sig-file path/to/OneStats_x.y.z_x64-setup.exe.sig \
      [--notes docs/RELEASE_NOTES.md] [--out dist/release]

`--github-repo OWNER/REPO` points the Tauri `latest.json` download URL at that repo's GitHub
Releases (`https://github.com/OWNER/REPO/releases/latest/download/<installer>`); `--base-url` can
point at any other HTTPS host instead. `--sig-file`/`--signature` embed the Tauri updater signature
(the `.sig` beside the installer, produced by a signed build) so the manifest verifies in production.
Without a signature the manifest is emitted with a clearly-marked placeholder and the script warns —
an unsigned manifest must never be published.

It never embeds secrets, signing keys or connection strings (the signature is a public artifact).
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


def _resolve_base_url(base_url: str | None, github_repo: str | None) -> str | None:
    """Download base URL for the installer. --base-url wins; otherwise derive it from a GitHub repo.

    GitHub's `releases/latest/download/<asset>` always resolves to the newest published release, which
    matches the single `latest.json` the Tauri updater polls. HTTPS is required (security invariant §9).
    """
    if base_url:
        if not base_url.startswith("https://"):
            raise SystemExit("ERROR: --base-url must be an https:// URL (secure distribution only).")
        return base_url.rstrip("/")
    if github_repo:
        repo = github_repo.strip().strip("/")
        if repo.count("/") != 1 or not all(repo.split("/")):
            raise SystemExit("ERROR: --github-repo must be OWNER/REPO.")
        return f"https://github.com/{repo}/releases/latest/download"
    return None


def _resolve_signature(signature: str | None, sig_file: str | None) -> tuple[str, bool]:
    """Return (signature, signed?). The Tauri updater signature is produced by a signed build; it is a
    public verification artifact, never the private key. Absent → a clearly-marked placeholder."""
    if signature:
        return signature.strip(), True
    if sig_file:
        p = pathlib.Path(sig_file)
        if not p.exists():
            raise SystemExit(f"ERROR: --sig-file not found: {p}")
        return p.read_text(encoding="utf-8").strip(), True
    return "PLACEHOLDER_TAURI_SIGNATURE", False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build an OneStats release manifest + checksums.")
    ap.add_argument("--installer", required=True, help="Path to the built installer (.exe/.msi).")
    ap.add_argument("--channel", default="stable", choices=["stable", "testing"])
    ap.add_argument("--arch", default="x64")
    ap.add_argument("--notes", default=str(ROOT / "docs" / "RELEASE_NOTES.md"))
    ap.add_argument("--min-prior", default=None, help="Minimum prior desktop version that may upgrade to this one.")
    ap.add_argument("--github-repo", default=None, help="OWNER/REPO whose GitHub Releases host the artifacts.")
    ap.add_argument("--base-url", default=None,
                    help="HTTPS base URL the installer is downloaded from (overrides --github-repo).")
    sig = ap.add_mutually_exclusive_group()
    sig.add_argument("--signature", default=None, help="Tauri updater signature string (the .sig content).")
    sig.add_argument("--sig-file", default=None, help="Path to the installer's .sig file (Tauri updater signature).")
    ap.add_argument("--out", default=str(ROOT / "dist" / "release"))
    args = ap.parse_args(argv)

    installer = pathlib.Path(args.installer)
    if not installer.exists():
        print(f"ERROR: installer not found: {installer}", file=sys.stderr)
        return 2

    base_url = _resolve_base_url(args.base_url, args.github_repo)
    signature, signed = _resolve_signature(args.signature, args.sig_file)

    version = _read_desktop_version()
    contract = _read_server_contract()
    checksum = _sha256(installer)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes = _notes(pathlib.Path(args.notes), version)
    download_url = f"{base_url}/{installer.name}" if base_url else (
        "https://RELEASES.EXAMPLE/CONFIGURE_HOSTING/" + installer.name)

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
        "download_url": download_url,
        # The Tauri updater signature is a public verification artifact (never the private key).
        "signature": signature if signed else None,
        "signing": "signed" if signed else "PLACEHOLDER — run a signed build; never commit private keys.",
    }
    (out_dir / "onestats-release.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 2) Tauri-updater latest.json (the manifest the desktop updater polls and verifies).
    latest = {
        "version": version,
        "notes": notes.splitlines()[0] if notes else f"OneStats {version}",
        "pub_date": now,
        "platforms": {
            "windows-x86_64": {
                "signature": signature,
                "url": download_url,
            }
        },
    }
    (out_dir / "latest.json").write_text(json.dumps(latest, indent=2), encoding="utf-8")

    # 3) Plain checksums file.
    (out_dir / "SHA256SUMS.txt").write_text(f"{checksum}  {installer.name}\n", encoding="utf-8")

    print(f"Wrote release metadata to {out_dir}")
    print(f"  version={version} channel={args.channel} sha256={checksum[:16]}…")
    print(f"  download_url={download_url}")
    if not signed:
        print("  WARNING: no --signature/--sig-file given — latest.json carries a PLACEHOLDER signature.")
        print("           A signed build produces the .sig; do NOT publish an unsigned manifest (docs/74 §9).")
    if base_url is None:
        print("  WARNING: no --github-repo/--base-url given — download URL is a placeholder. Configure hosting.")
    return 0 if (signed and base_url) else 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
