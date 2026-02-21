---
name: bom-guard
description: UTF-8 BOM の混入を防止・除去する。Windows 環境でのファイル書込時に使う。
---

# Purpose
UTF-8 BOM (`EF BB BF`) の混入を防止し、BOM 起因のパースエラーを回避する。

# When to use / When NOT to use
- When to use:
  - シェルコマンドでテキストファイルを書き込むとき
  - BOM 混入の疑いがあるファイルを修復するとき
- When NOT to use:
  - Claude Code の Edit / Write ツールで書き込むとき（BOM は付かない）
  - バイナリファイル、または BOM が明示的に必要なファイル

# Procedure
1. ファイル編集は Edit / Write ツールを優先する（BOM 問題を回避できる）。
2. シェル経由の書込が必要な場合は `scripts/write_utf8_nobom.ps1` を使う。
3. BOM 混入の確認が必要なら `Format-Hex -Path <file> | Select-Object -First 1` で先頭バイトを検査。
4. BOM が検出された場合は `scripts/strip_utf8_bom.ps1` で除去する。

# Commands
```powershell
# UTF-8 (no BOM) で書込
powershell -ExecutionPolicy Bypass -File scripts/write_utf8_nobom.ps1 -Path <file> -Content "<text>"

# BOM 除去
powershell -ExecutionPolicy Bypass -File scripts/strip_utf8_bom.ps1 -Path <file>

# 先頭バイト確認
Format-Hex -Path <file> | Select-Object -First 1
```

# Validation
- 先頭バイトに `EF BB BF` がないこと。
