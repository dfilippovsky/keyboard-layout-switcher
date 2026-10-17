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
           "multiprocessing", "lzma", "bz2"
$excludeArgs = $exclude | ForEach-Object { "--exclude-module", $_ }
# Плагіни (plugins\*.py) отримують лише ті модулі стандартної бібліотеки, що є в exe,
# тож додаємо корисні для них: текст, дати, хеші, JSON, HTTP(S)-запити тощо
$forPlugins = "json", "csv", "html", "textwrap", "unicodedata", "string", "difflib",
              "datetime", "calendar", "random", "secrets", "uuid", "hashlib",
              "base64", "statistics", "fractions", "decimal", "urllib.request", "urllib.parse",
              "http.client", "ssl", "webbrowser"
$hiddenArgs = $forPlugins | ForEach-Object { "--hidden-import", $_ }

$mode = if ($OneDir) { "--onedir" } else { "--onefile" }
$out = if ($OneDir) { "dist\KeyboardLayoutSwitcher" } else { "dist\KeyboardLayoutSwitcher.exe" }

# Файли користувача лежать поруч з exe. У режимі -OneDir PyInstaller видаляє всю папку,
# тож на час збірки зберігаємо їхню копію (окрему для кожного режиму) і повертаємо її
# навіть при помилці.
$appDir = if ($OneDir) { $out } else { "dist" }
$cfg = Join-Path $appDir "config.ini"
$userFiles = "config.ini", "autocorrect_exceptions.txt", "plugins"
$backup = "build\userdata.{0}" -f $(if ($OneDir) { "onedir" } else { "onefile" })

function Restore-UserFiles {
    # Копію видаляємо лише після того, як усе на місці
    foreach ($name in $userFiles) {
        $saved = Join-Path $backup $name
        $target = Join-Path $appDir $name
        if ((Test-Path $saved) -and -not (Test-Path $target)) {
            New-Item -ItemType Directory -Force $appDir | Out-Null
            Copy-Item $saved $target -Recurse
        }
    }
    Remove-Item $backup -Recurse -Force -ErrorAction SilentlyContinue
}

# Копія, що лишилася від перерваної збірки: якщо файлу вже немає, це його єдина версія,
# а якщо він на місці — копія застаріла.
Restore-UserFiles
New-Item -ItemType Directory -Force $backup | Out-Null
foreach ($name in $userFiles) {
    $target = Join-Path $appDir $name
    if (Test-Path $target) { Copy-Item $target (Join-Path $backup $name) -Recurse -Force }
}
try {
    & $py -m PyInstaller --noconfirm --clean $mode --windowed `
        --name KeyboardLayoutSwitcher --icon build\app.ico --add-data "langdata;langdata" `
        @excludeArgs @hiddenArgs main.py
    $code = $LASTEXITCODE
} finally {
    Restore-UserFiles
}
if ($code) { exit $code }

# Плагіни з репозиторію — поруч з exe. Власні плагіни користувача лишаються, а файли
# з репозиторію оновлюються (тож їх краще не редагувати, а копіювати під іншим ім'ям).
$pluginsDir = Join-Path $appDir "plugins"
New-Item -ItemType Directory -Force $pluginsDir | Out-Null
Copy-Item "plugins\*.py" $pluginsDir -Force
"plugins: {0}" -f (Resolve-Path $pluginsDir)

# Дописуємо ключі нової версії (решта вмісту зберігається; якщо файлу не було —
# створюється з налаштуваннями за замовчуванням)
& $py -c "import sys, config; config.Config.load(sys.argv[1])" $cfg
if ($LASTEXITCODE) { exit $LASTEXITCODE }
"config.ini: {0}" -f (Resolve-Path $cfg)

$size = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum
"Готово: {0} ({1:N1} MB)" -f (Resolve-Path $out), ($size / 1MB)
