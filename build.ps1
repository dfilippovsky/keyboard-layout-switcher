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
$out = if ($OneDir) { "dist\KeyboardLayoutSwitcher" } else { "dist\KeyboardLayoutSwitcher.exe" }

# config.ini поруч з exe. У режимі -OneDir PyInstaller видаляє всю папку, тож на час
# збірки зберігаємо копію (окрему для кожного режиму) і повертаємо її навіть при помилці.
$cfgDir = if ($OneDir) { $out } else { "dist" }
$cfg = Join-Path $cfgDir "config.ini"
$cfgBackup = "build\config.{0}.ini.bak" -f $(if ($OneDir) { "onedir" } else { "onefile" })

function Restore-Config {
    # Копію видаляємо лише після того, як конфіг на місці
    if ((Test-Path $cfgBackup) -and -not (Test-Path $cfg)) {
        New-Item -ItemType Directory -Force $cfgDir | Out-Null
        Copy-Item $cfgBackup $cfg
    }
    Remove-Item $cfgBackup -ErrorAction SilentlyContinue
}

# Копія, що лишилася від перерваної збірки: якщо конфіг зник, це його єдина версія,
# а якщо конфіг на місці — копія застаріла.
Restore-Config
if (Test-Path $cfg) { Copy-Item $cfg $cfgBackup -Force }
try {
    & $py -m PyInstaller --noconfirm --clean $mode --windowed `
        --name KeyboardLayoutSwitcher --icon build\app.ico --add-data "langdata;langdata" `
        @excludeArgs main.py
    $code = $LASTEXITCODE
} finally {
    Restore-Config
}
if ($code) { exit $code }

# Дописуємо ключі нової версії (решта вмісту зберігається; якщо файлу не було —
# створюється з налаштуваннями за замовчуванням)
& $py -c "import sys, config; config.Config.load(sys.argv[1])" $cfg
if ($LASTEXITCODE) { exit $LASTEXITCODE }
"config.ini: {0}" -f (Resolve-Path $cfg)

$size = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum
"Готово: {0} ({1:N1} MB)" -f (Resolve-Path $out), ($size / 1MB)
