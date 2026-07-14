# Construye GatoGuard.exe (portable, un solo archivo) con PyInstaller.
# Uso:  ./build.ps1
$ErrorActionPreference = "Stop"

pip install pyinstaller | Out-Null

pyinstaller --noconfirm --clean --onefile --windowed `
    --name GatoGuard `
    --add-data "es_50k.txt;." `
    --add-data "en_50k.txt;." `
    --collect-submodules pystray `
    --hidden-import win32timezone `
    gatoguard.py

Write-Host "`nListo -> dist/GatoGuard.exe" -ForegroundColor Green
