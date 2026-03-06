# FNID Portal One-Click Launcher (Windows)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Install dependencies
pip install -e ".[dev]" --quiet 2>$null

# Set PYTHONPATH and launch
$env:PYTHONPATH = "src"
Write-Host "Starting FNID Portal at http://localhost:5000"
flask --app fnid_portal run --debug --host 0.0.0.0 --port 5000
