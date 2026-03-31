param(
    [string]$SkillRoot = ".agents/skills"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

$ensureVenv = Join-Path $scriptDir "ensure_venv.ps1"
& $ensureVenv | Out-Host

$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "python not found: $venvPython"
}

$validator = Join-Path $scriptDir "quick_validate_skill.py"
if (-not (Test-Path $validator)) {
    throw "quick_validate_skill.py not found: $validator"
}

$env:PYTHONUTF8 = "1"
& $venvPython -c "import yaml" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyYAML is required in .venv. Run: .\.venv\Scripts\python.exe -m pip install PyYAML"
    exit 1
}

$skillRootPath = if ([System.IO.Path]::IsPathRooted($SkillRoot)) {
    $SkillRoot
} else {
    Join-Path $repoRoot $SkillRoot
}

if (-not (Test-Path $skillRootPath)) {
    throw "skill root not found: $skillRootPath"
}

$legacyUnderscoreNames = @(
    "sidebiz_sync"
)

$ok = 0
$warn = 0
$fail = 0

$skills = Get-ChildItem -Path $skillRootPath -Directory | Sort-Object Name
foreach ($skill in $skills) {
    $output = & $venvPython $validator $skill.FullName 2>&1
    $message = ($output | ForEach-Object { "$_" }) -join "`n"

    if ($LASTEXITCODE -eq 0) {
        Write-Host ("[OK] {0}: {1}" -f $skill.Name, $message)
        $ok++
        continue
    }

    if (($legacyUnderscoreNames -contains $skill.Name) -and ($message -match "should be hyphen-case")) {
        Write-Host ("[WARN] {0}: legacy underscore name allowed for now" -f $skill.Name) -ForegroundColor Yellow
        $warn++
        continue
    }

    Write-Host ("[FAIL] {0}: {1}" -f $skill.Name, $message) -ForegroundColor Red
    $fail++
}

Write-Host ""
Write-Host ("Summary: OK={0} WARN={1} FAIL={2}" -f $ok, $warn, $fail)

if ($warn -gt 0) {
    Write-Host "Legacy underscore skill names remain. Migrate them only in a dedicated rename task." -ForegroundColor Yellow
}

if ($fail -gt 0) {
    exit 1
}
