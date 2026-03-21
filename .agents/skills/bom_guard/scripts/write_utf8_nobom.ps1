param(
  [Parameter(Mandatory=$true)][string]$Path,
  [Parameter(Mandatory=$true)][string]$Content
)

$dir = Split-Path -Path $Path -Parent
if ($dir -and -not (Test-Path $dir)) {
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($Path, $Content, $enc)
Write-Output "written:utf8-no-bom:$Path"