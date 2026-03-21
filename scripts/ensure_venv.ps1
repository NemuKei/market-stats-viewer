param(
    [string]$VenvDir = ".venv"
)

$venvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[ensure_venv] create $VenvDir"
    py -m venv $VenvDir
}

if (-not (Test-Path $venvPython)) {
    throw "[ensure_venv] python not found in $VenvDir"
}

Write-Host "[ensure_venv] ready: $venvPython"
