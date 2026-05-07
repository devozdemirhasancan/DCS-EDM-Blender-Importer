<#
.SYNOPSIS
    Build a zip of the dcs_edm_importer add-on, ready for Blender install.

.DESCRIPTION
    Blender's "Edit -> Preferences -> Add-ons -> Install..." dialog accepts
    either a single .py file or a .zip whose root directory matches the
    add-on package name. This script produces such a zip.

    Output: build/dcs_edm_importer-<version>.zip

.EXAMPLE
    PS> .\build.ps1
    Created: build/dcs_edm_importer-0.2.0.zip
#>

[CmdletBinding()]
param(
    [string]$OutputDir = "build"
)

$ErrorActionPreference = "Stop"

$pkgRoot = Join-Path $PSScriptRoot "dcs_edm_importer"
if (-not (Test-Path $pkgRoot)) {
    Write-Error "Package directory '$pkgRoot' not found."
    exit 1
}

# Read the version tuple from __init__.py without executing Python.
$initFile = Join-Path $pkgRoot "__init__.py"
$initContents = Get-Content -Raw -Path $initFile
if ($initContents -match '"version":\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)') {
    $version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
} else {
    $version = "dev"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$zipPath = Join-Path $OutputDir "dcs_edm_importer-$version.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

# Stage the package without __pycache__ folders or compiled .pyc files
# (Blender re-compiles on first run, so these would just bloat the zip).
$staging = Join-Path $env:TEMP ("dcs_edm_importer_stage_" + [Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $staging | Out-Null
$dest = Join-Path $staging "dcs_edm_importer"
Copy-Item -Path $pkgRoot -Destination $dest -Recurse
Get-ChildItem -Path $dest -Recurse -Force | Where-Object {
    $_.Name -eq "__pycache__" -or $_.Name -like "*.pyc"
} | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Compress.
Compress-Archive -Path (Join-Path $staging "dcs_edm_importer") -DestinationPath $zipPath -Force
Remove-Item $staging -Recurse -Force

Write-Host "Created: $zipPath" -ForegroundColor Green
Write-Host ""
Write-Host "Install in Blender:" -ForegroundColor Cyan
Write-Host "  1. Edit -> Preferences -> Add-ons -> Install..."
Write-Host "  2. Pick:  $zipPath"
Write-Host "  3. Enable the 'DCS World EDM Importer' check-box."
