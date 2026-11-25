$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install --python '.venv/Scripts/python.exe' -r requirements.lock
} else {
    & '.venv/Scripts/python.exe' -m ensurepip --upgrade
    & '.venv/Scripts/python.exe' -m pip install -r requirements.lock
}
if ($LASTEXITCODE -ne 0) { throw 'Could not install dependencies.' }
Write-Host 'Ready. Start with: .\run.ps1'
