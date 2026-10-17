# Збірка через PyInstaller:
#   .\build.ps1          -> dist\KeyboardLayoutSwitcher.exe (один файл)
#   .\build.ps1 -OneDir  -> dist\KeyboardLayoutSwitcher\ (папка; швидший старт, один процес, менше RAM)
param([switch]$OneDir)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m pip install --quiet --upgrade -r requirements-dev.txt

New-Item -ItemType Directory -Force build | Out-Null
& $py -c "import icon; icon.write_ico('build/app.ico')"

$exclude = "unittest", "pydoc", "doctest", "pdb", "xmlrpc", "sqlite3", "asyncio",
           "multiprocessing", "ssl", "lzma", "bz2", "http", "urllib.request"
$excludeArgs = $exclude | ForEach-Object { "--exclude-module", $_ }

$mode = if ($OneDir) { "--onedir" } else { "--onefile" }
& $py -m PyInstaller --noconfirm --clean $mode --windowed `
    --name KeyboardLayoutSwitcher --icon build\app.ico @excludeArgs main.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$out = if ($OneDir) { "dist\KeyboardLayoutSwitcher" } else { "dist\KeyboardLayoutSwitcher.exe" }
$size = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum
"Готово: {0} ({1:N1} MB)" -f (Resolve-Path $out), ($size / 1MB)
