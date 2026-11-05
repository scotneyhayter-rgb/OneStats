"""Release-manifest generator (scripts/build-release-manifest.py).

Runs the script as a subprocess (it is a standalone tool, not part of the onestats package) and asserts
it produces a correct Tauri `latest.json` + rich manifest: real GitHub download URL, embedded signature,
accurate checksum, and the safety behaviour that an unsigned / unhosted run is flagged (non-zero exit)
so it can never be published silently (docs/74 §9).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build-release-manifest.py"
TAURI_CONF = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"


def _desktop_version() -> str:
    return str(json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"])


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    # check=False: the tests assert on returncode/stderr themselves (the script exits non-zero on
    # bad input), so a raised CalledProcessError would defeat the point.
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], check=False, capture_output=True, text=True)


def _make_installer(tmp_path: pathlib.Path) -> pathlib.Path:
    installer = tmp_path / "OneStats_1.0.0_x64-setup.exe"
    installer.write_bytes(b"fake installer bytes \x00\x01\x02")
    return installer


def test_signed_github_manifest_is_complete(tmp_path):
    installer = _make_installer(tmp_path)
    sig = tmp_path / "OneStats_1.0.0_x64-setup.exe.sig"
    sig.write_text("dUPDATER_SIGNATURE_abc123\n", encoding="utf-8")
    out = tmp_path / "release"

    r = _run(["--installer", str(installer), "--github-repo", "acme/onestats",
              "--sig-file", str(sig), "--out", str(out)])
    assert r.returncode == 0, r.stderr + r.stdout

    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["version"] == _desktop_version()
    plat = latest["platforms"]["windows-x86_64"]
    assert plat["url"] == "https://github.com/acme/onestats/releases/latest/download/" + installer.name
    assert plat["signature"] == "dUPDATER_SIGNATURE_abc123"  # trimmed, from the .sig file

    manifest = json.loads((out / "onestats-release.json").read_text(encoding="utf-8"))
    assert manifest["checksums"]["sha256"] == hashlib.sha256(installer.read_bytes()).hexdigest()
    assert manifest["signing"] == "signed"
    # Checksums side-car names the installer.
    assert installer.name in (out / "SHA256SUMS.txt").read_text(encoding="utf-8")


def test_inline_signature_and_explicit_base_url(tmp_path):
    installer = _make_installer(tmp_path)
    out = tmp_path / "release"
    r = _run(["--installer", str(installer), "--base-url", "https://dl.example.org/onestats/",
              "--signature", "sig-literal", "--out", str(out)])
    assert r.returncode == 0, r.stderr + r.stdout
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    plat = latest["platforms"]["windows-x86_64"]
    assert plat["url"] == "https://dl.example.org/onestats/" + installer.name
    assert plat["signature"] == "sig-literal"


def test_unsigned_run_is_flagged_and_keeps_placeholder(tmp_path):
    installer = _make_installer(tmp_path)
    out = tmp_path / "release"
    r = _run(["--installer", str(installer), "--github-repo", "acme/onestats", "--out", str(out)])
    # Non-zero: an unsigned manifest must not be published silently.
    assert r.returncode == 3, r.stdout
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["platforms"]["windows-x86_64"]["signature"] == "PLACEHOLDER_TAURI_SIGNATURE"


def test_rejects_insecure_base_url(tmp_path):
    installer = _make_installer(tmp_path)
    out = tmp_path / "release"
    r = _run(["--installer", str(installer), "--base-url", "http://insecure.example/",
              "--signature", "s", "--out", str(out)])
    assert r.returncode != 0
    assert "https" in (r.stderr + r.stdout).lower()


def test_rejects_malformed_github_repo(tmp_path):
    installer = _make_installer(tmp_path)
    out = tmp_path / "release"
    r = _run(["--installer", str(installer), "--github-repo", "not-a-repo",
              "--signature", "s", "--out", str(out)])
    assert r.returncode != 0
    assert "OWNER/REPO" in (r.stderr + r.stdout)


def test_missing_installer_errors(tmp_path):
    r = _run(["--installer", str(tmp_path / "nope.exe"), "--github-repo", "acme/onestats",
              "--signature", "s", "--out", str(tmp_path / "release")])
    assert r.returncode != 0
    assert "installer not found" in (r.stderr + r.stdout).lower()
