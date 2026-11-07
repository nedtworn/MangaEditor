# Packages Manga Editör as a standalone Windows application.
# Output: dist\MangaEditor\MangaEditor.exe (the whole folder is portable)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name MangaEditor `
    --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtMultimedia --exclude-module tkinter `
    run.py
# Do not print "OK" if PyInstaller fails (e.g. the exe is locked because it is running).
if ($LASTEXITCODE -ne 0) { Write-Error "Derleme BAŞARISIZ (çıkış kodu $LASTEXITCODE). Çalışan MangaEditor.exe'yi kapatıp tekrar deneyin."; exit 1 }
Write-Host "Tamam: dist\MangaEditor\MangaEditor.exe ($((Get-Item dist\MangaEditor\MangaEditor.exe).LastWriteTime))"
