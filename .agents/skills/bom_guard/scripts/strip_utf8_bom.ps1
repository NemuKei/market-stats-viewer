param(
  [Parameter(Mandatory=$true)][string]$Path
)

if (-not (Test-Path $Path)) {
  throw "file not found: $Path"
}

$bytes = [System.IO.File]::ReadAllBytes($Path)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
  $newBytes = New-Object byte[] ($bytes.Length - 3)
  [Array]::Copy($bytes, 3, $newBytes, 0, $newBytes.Length)
  [System.IO.File]::WriteAllBytes($Path, $newBytes)
  Write-Output "bom-removed:$Path"
} else {
  Write-Output "no-bom:$Path"
}