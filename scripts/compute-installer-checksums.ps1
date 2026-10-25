<#
.SYNOPSIS
  Compute SHA-256 checksums for built OneStats Windows installers (Phase 17).

.DESCRIPTION
  After `tauri build` produces the installers, run this to generate a SHA256SUMS.txt alongside them so
  users can verify the download/USB copy. Point -Path at the bundle output directory.

.EXAMPLE
  pwsh ./scripts/compute-installer-checksums.ps1 -Path apps/desktop/src-tauri/target/release/bundle
#>
param(
  [string]$Path = "apps/desktop/src-tauri/target/release/bundle"
)

if (-not (Test-Path $Path)) {
  Write-Error "Bundle path not found: $Path. Build the installers first (tauri build)."
  exit 1
}

$installers = Get-ChildItem -Path $Path -Recurse -Include *.exe, *.msi | Sort-Object FullName
if (-not $installers) {
  Write-Error "No .exe/.msi installers found under $Path."
  exit 1
}

$outFile = Join-Path $Path "SHA256SUMS.txt"
$lines = foreach ($f in $installers) {
  $hash = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash.ToLower()
  "{0}  {1}" -f $hash, $f.Name
}
$lines | Set-Content -Path $outFile -Encoding utf8
Write-Host "Wrote $outFile"
$lines | ForEach-Object { Write-Host $_ }
