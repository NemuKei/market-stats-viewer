---
name: bom-guard
description: Prevent UTF-8 BOM issues on Windows PowerShell 5.1. Use when writing or rewriting text files via shell commands and you need guaranteed UTF-8 without BOM.
---

# Purpose
Prevent accidental UTF-8 BOM insertion and provide a deterministic no-BOM write workflow.

# When to use / When NOT to use
- When to use:
  - Writing text files from PowerShell commands
  - Repairing files that may start with BOM (`EF BB BF`)
  - Avoiding parser failures caused by BOM in config/rule files
- When NOT to use:
  - Binary files
  - Files that explicitly require BOM

# Inputs
- Target file path
- Text content or existing file to normalize

# Outputs
- UTF-8 (no BOM) file
- Optional BOM-removal result message

# Procedure
1. Prefer `apply_patch` for in-repo edits.
2. If shell write is required, use `scripts/write_utf8_nobom.ps1`.
3. Verify header bytes via `Format-Hex | Select-Object -First 1` when needed.
4. If BOM exists (`EF BB BF`), run `scripts/strip_utf8_bom.ps1`.

# Commands
```powershell
# Write text as UTF-8 without BOM
powershell -ExecutionPolicy Bypass -File scripts/write_utf8_nobom.ps1 -Path docs/example.md -Content "hello"

# Strip BOM if present
powershell -ExecutionPolicy Bypass -File scripts/strip_utf8_bom.ps1 -Path docs/example.md

# Check first bytes
Format-Hex -Path docs/example.md | Select-Object -First 1
```

# Validation
- `Format-Hex | Select-Object -First 1` does not show `EF BB BF`.
- File content is preserved after normalization.