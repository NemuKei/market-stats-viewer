[CmdletBinding()]
param(
    [switch]$RunLint,
    [switch]$UpdateData,
    [switch]$UpdateTcdData,
    [switch]$UpdateEventsData,
    [switch]$UpdateEventSignalsData,
    [switch]$RunApp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Script
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Script
}

function Require-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "'$CommandName' is not installed or not in PATH."
    }
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandName,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $CommandName @Arguments
    if ($LASTEXITCODE -ne 0) {
        $joined = ($Arguments -join " ")
        throw "Command failed: $CommandName $joined"
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
    Require-Command -CommandName "uv"

    Invoke-Step -Name "Create or refresh virtual environment" -Script {
        if (Test-Path ".venv") {
            Write-Host ".venv already exists. Skipping create step."
        }
        else {
            Invoke-Native "uv" "venv"
        }
    }

    Invoke-Step -Name "Sync dependencies" -Script {
        Invoke-Native "uv" "sync"
    }

    if ($RunLint) {
        Invoke-Step -Name "Run lint (ruff)" -Script {
            Invoke-Native "uv" "run" "ruff" "check" "."
        }
    }

    if ($UpdateData) {
        Invoke-Step -Name "Update stay statistics data" -Script {
            Invoke-Native "uv" "run" "python" "-m" "scripts.update_data"
        }
    }

    if ($UpdateTcdData) {
        Invoke-Step -Name "Update TCD data" -Script {
            Invoke-Native "uv" "run" "python" "-m" "scripts.update_tcd_data"
        }
    }

    if ($UpdateEventsData) {
        Invoke-Step -Name "Update events data" -Script {
            Invoke-Native "uv" "run" "python" "-m" "scripts.update_events_data"
        }
    }

    if ($UpdateEventSignalsData) {
        Invoke-Step -Name "Update event signals data" -Script {
            Invoke-Native "uv" "run" "python" "-m" "scripts.update_event_signals_data"
        }
    }

    if ($RunApp) {
        Invoke-Step -Name "Start Streamlit app" -Script {
            Invoke-Native "uv" "run" "streamlit" "run" "app.py"
        }
    }

    Write-Host ""
    Write-Host "Setup completed." -ForegroundColor Green
}
finally {
    Pop-Location
}
