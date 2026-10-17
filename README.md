<a id="english"></a>

# Keyboard Layout Switcher

**🇺🇦 [Українська версія ↓](#ukrainian)**

A tiny Windows tray app. Typed something in the wrong keyboard layout
(`ghbdsn` instead of `привіт`)? Press the hotkey — the text is converted to the next
layout and the active window switches to that layout.

- **With a selection** — the selected text is converted. When reselecting is enabled
  (`reselect`, on by default) and the text is up to 5000 characters long, it stays
  selected, so pressing the hotkey again moves it to the next layout in the cycle
  (with two layouts, it reverts the change).
- **Without a selection** — the last word before the caret is converted
  (up to the preceding whitespace; punctuation such as `,` `.` `;` `[` counts as part of the
  word, because in another layout those keys are letters, e.g. `б` `ю` `ж` `х` in Ukrainian).

Works with any installed layouts (EN/UK/DE/PL/…): character tables are built from the
system layouts, nothing is hard-coded. The target is the next layout in the Windows list
after the one the text was typed in.

The icon is [`languages`](https://lucide.dev/icons/languages) from Lucide (ISC).
In the tray it adapts to the light/dark taskbar theme, turns grey when disabled, and
briefly flashes blue each time the hotkey is handled.

## Running

Only Python 3.10+ with the standard library (ctypes + tkinter) is required; there are no
third-party dependencies.

```powershell
.venv\Scripts\pythonw.exe main.py
```

Or build the exe (see below) and run `KeyboardLayoutSwitcher.exe`.

## Tray

- **Double-click** — settings window.
- **Right-click** — menu: Enabled, Settings…, Open config.ini, Reload config.ini, Exit.

## Settings

The settings window has: the hotkey (click the field and press the combination),
enable/disable, layout switching, reselecting converted text, **start with Windows**,
and the copy timeout.

Everything is stored in `config.ini` next to `main.py` / the exe (created on first run):

| Key               | Default  | Description |
|-------------------|----------|-------------|
| `hotkey`          | `Pause`  | Combination: `Ctrl`/`Alt`/`Shift`/`Win` + key. Examples: `Shift+Pause`, `Ctrl+Alt+Space`, `Alt+F12`, `Win+VKE8`. |
| `enabled`         | `true`   | React to the hotkey. |
| `switch_layout`   | `true`   | Switch the active window's layout after converting. |
| `reselect`        | `true`   | Select the converted text again after converting a selection (skipped for text longer than 5000 characters). |
| `copy_timeout_ms` | `250`    | How long to wait for the app to put text on the clipboard after `Ctrl+C`. Increase for slow apps. |

After editing the file manually, use “Reload config.ini” in the tray menu. The app writes
the file atomically (via a temporary `config.ini.tmp`), so a failed write never corrupts
the existing file.

Key names: `A`–`Z`, `0`–`9`, `F1`–`F24`, `Pause`, `Space`, `Tab`, `Enter`, `Esc`,
`Backspace`, `Insert`, `Delete`, `Home`, `End`, `PageUp`, `PageDown`, `Left`/`Up`/`Right`/`Down`,
`CapsLock`, `ScrollLock`, `PrintScreen`, `Apps`, `Num0`–`Num9`, `NumPlus`, `NumMinus`,
`NumMul`, `NumDiv`, `NumDecimal`, `` ` `` `-` `=` `[` `]` `\` `;` `'` `,` `.` `/`,
or any virtual-key code as `VKxx` (hex).

Autostart is the `KeyboardLayoutSwitcher` value under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (no admin rights needed).

### Diagnostics

Errors are written to `layout_switcher.log` next to the app. For a detailed log of every
hotkey press, run with the `KLS_DEBUG=1` environment variable:

```powershell
$env:KLS_DEBUG = "1"; .venv\Scripts\python.exe main.py
```

## Building the exe

```powershell
.\build.ps1           # dist\KeyboardLayoutSwitcher.exe — single file (~12 MB)
.\build.ps1 -OneDir   # dist\KeyboardLayoutSwitcher\ — folder: faster start, one process
```

The script uses `.venv` if present, installs PyInstaller from `requirements-dev.txt`
and generates `app.ico` from the same icon.

### Single file or folder

Same app, the only difference is packaging and startup:

|                  | Single file (default)                                  | Folder (`-OneDir`)                          |
|------------------|--------------------------------------------------------|---------------------------------------------|
| Output           | one `KeyboardLayoutSwitcher.exe` (~12 MB)              | folder with the exe and `_internal\` (Python, Tcl/Tk) |
| Startup          | unpacks itself into `%TEMP%\_MEIxxxxx` every time      | starts right away, nothing to unpack        |
| Processes        | two: bootloader (~10 MB) + the app                     | one                                         |
| Start time       | slower                                                 | faster                                      |
| Leftovers in TEMP| removed on exit; left behind if the process is killed  | none                                        |
| Antivirus        | more often suspicious of self-extracting exes          | less often                                  |
| Distribution     | one file — easy to copy/share                          | the whole folder has to be moved            |

In both cases `config.ini` and the log live next to the exe, and autostart points to the exe.

For an app that sits in the tray all the time and starts with Windows, `-OneDir` is a bit
better (less RAM, faster start). Use the single file when easy sharing matters more.

Resources: ~25 MB RAM in the background (onefile additionally keeps a ~10 MB bootloader
process), 0% CPU — no keyboard hooks or polling, just `RegisterHotKey`. Tk is loaded
only when the settings window is opened for the first time.

## How it works

1. `RegisterHotKey` → wait until the modifiers are released.
2. Save the clipboard contents, send `Ctrl+C`.
3. Got text — that's the selection. Nothing — `Ctrl+Shift+Left` (repeated until whitespace
   is reached) + `Ctrl+C` to grab the last word.
   If “a line + line break” was copied, it may be either a selection or an editor copying
   the whole line without a selection (VS Code, JetBrains, etc.). Then `Shift+Left` +
   `Ctrl+C` tells them apart: with a selection the line comes back without the line break;
   without one — a single character. `Shift+Right` restores the original state. If
   `Shift+Left` changed nothing (caret or reversed selection at the start of the field),
   the same check is done with `Shift+Right`.
4. Detect the text's layout, convert it key by key (`ToUnicodeEx`) to the next layout and
   type the result as Unicode `SendInput` events (multi-line/long text is pasted via the
   clipboard).
5. Restore the clipboard (marked “do not add to Win+V history”) and switch the window's
   layout (`WM_INPUTLANGCHANGEREQUEST`).

Data-loss protection: the conversion is aborted without changing any text (a system sound
plays and the reason is logged) if:

- the clipboard is busy or holds a format that cannot be saved and restored
  (e.g. owner-display); bitmaps and metafiles are preserved;
- a copy fails while searching for the word, or no word boundary is found within 8 steps;
- the “selection or line copy” check is ambiguous (a one-character line);
- the text could not be put on the clipboard before pasting;
- the narrowed selection does not match the expected text.

## Limitations

- Does not work in windows running as administrator unless the app itself runs elevated
  (Windows UIPI restriction).
- Intermediate text copied via `Ctrl+C` may end up in the clipboard history (Win+V).
- Consoles/terminals with non-standard `Ctrl+C`/`Ctrl+Shift+Left` are not supported.

---

<a id="ukrainian"></a>

# Keyboard Layout Switcher — українською

**🇬🇧 [English version ↑](#english)**

Маленька програма для Windows, що живе в треї. Набрали текст не в тій розкладці
(`ghbdsn` замість `привіт`)? Натисніть гарячу клавішу — і текст конвертується
в наступну розкладку, а розкладка активного вікна перемкнеться на неї.

- **Є виділення** — конвертується виділений текст. Якщо увімкнено повторне виділення
  (`reselect`, за замовчуванням увімкнено) і текст не довший за 5000 символів, він
  лишається виділеним, тож повторне натискання переводить його в наступну розкладку
  по колу (для двох розкладок — повертає як було).
- **Немає виділення** — конвертується останнє слово перед курсором
  (до пробілу; розділові знаки на кшталт `,` `.` `;` `[` вважаються частиною слова,
  бо в іншій розкладці це літери `б` `ю` `ж` `х`).

Працює з будь-якими встановленими розкладками (EN/UK/DE/PL/…): таблиці символів
будуються з системних розкладок, нічого не зашито. Напрям — наступна розкладка
в списку Windows після тієї, в якій набрано текст.

Іконка — [`languages`](https://lucide.dev/icons/languages) з Lucide (ISC),
в треї підлаштовується під світлу/темну тему панелі задач, сіра — коли вимкнено,
і коротко блимає синім щоразу, коли гаряча клавіша оброблена.

## Запуск

Потрібен лише Python 3.10+ зі стандартною бібліотекою (ctypes + tkinter), сторонніх
залежностей немає.

```powershell
.venv\Scripts\pythonw.exe main.py
```

Або зберіть exe (див. нижче) і запускайте `KeyboardLayoutSwitcher.exe`.

## Трей

- **Подвійний клік** — вікно налаштувань.
- **Правий клік** — меню: Увімкнено, Налаштування…, Відкрити config.ini,
  Перечитати config.ini, Вихід.

## Налаштування

Вікно налаштувань: гаряча клавіша (клацніть у поле й натисніть комбінацію),
увімкнення, перемикання розкладки, повторне виділення, **запуск разом з Windows**,
затримка очікування копіювання.

Усе зберігається в `config.ini` поруч із `main.py` / exe (створюється при першому запуску):

| Ключ              | За замовчуванням | Опис |
|-------------------|------------------|------|
| `hotkey`          | `Pause`          | Комбінація: `Ctrl`/`Alt`/`Shift`/`Win` + клавіша. Приклади: `Shift+Pause`, `Ctrl+Alt+Space`, `Alt+F12`, `Win+VKE8`. |
| `enabled`         | `true`           | Реагувати на гарячу клавішу. |
| `switch_layout`   | `true`           | Після конвертації перемикати розкладку активного вікна. |
| `reselect`        | `true`           | Після конвертації виділеного тексту виділяти його знову (для тексту довшого за 5000 символів пропускається). |
| `copy_timeout_ms` | `250`            | Скільки чекати, поки програма віддасть текст на `Ctrl+C`. Збільште для повільних програм. |

Після ручного редагування — меню трею «Перечитати config.ini». Програма записує файл
атомарно (через тимчасовий `config.ini.tmp`), тож збій запису не пошкодить чинний файл.

Назви клавіш: `A`–`Z`, `0`–`9`, `F1`–`F24`, `Pause`, `Space`, `Tab`, `Enter`, `Esc`,
`Backspace`, `Insert`, `Delete`, `Home`, `End`, `PageUp`, `PageDown`, `Left`/`Up`/`Right`/`Down`,
`CapsLock`, `ScrollLock`, `PrintScreen`, `Apps`, `Num0`–`Num9`, `NumPlus`, `NumMinus`,
`NumMul`, `NumDiv`, `NumDecimal`, `` ` `` `-` `=` `[` `]` `\` `;` `'` `,` `.` `/`,
або будь-який віртуальний код як `VKxx` (hex).

Автозапуск — значення `KeyboardLayoutSwitcher` у
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` (без прав адміністратора).

### Діагностика

Помилки пишуться в `layout_switcher.log` поруч із програмою. Детальний лог кожного
натискання — запустіть зі змінною середовища `KLS_DEBUG=1`:

```powershell
$env:KLS_DEBUG = "1"; .venv\Scripts\python.exe main.py
```

## Збірка exe

```powershell
.\build.ps1           # dist\KeyboardLayoutSwitcher.exe — один файл (~12 MB)
.\build.ps1 -OneDir   # dist\KeyboardLayoutSwitcher\ — папка: швидший старт, один процес
```

Скрипт використовує `.venv`, якщо він є, ставить PyInstaller з `requirements-dev.txt`
і генерує `app.ico` з тієї ж іконки.

### Один файл чи папка

Програма та сама, різниця лише в упаковці та запуску:

|                     | Один файл (за замовчуванням)                     | Папка (`-OneDir`)                         |
|---------------------|--------------------------------------------------|-------------------------------------------|
| Результат           | один `KeyboardLayoutSwitcher.exe` (~12 MB)       | папка з exe і `_internal\` (Python, Tcl/Tk) |
| Запуск              | щоразу розпаковує себе в `%TEMP%\_MEIxxxxx`      | запускається одразу, без розпаковки       |
| Процеси             | два: завантажувач (~10 MB) + програма            | один                                      |
| Старт               | повільніший                                      | швидший                                   |
| Слід у TEMP         | прибирається при виході; лишається, якщо процес вбити | немає                                |
| Антивіруси          | частіше насторожено ставляться до самопакованих exe | рідше                                  |
| Поширення           | один файл — зручно скопіювати/передати           | треба переносити всю папку                |

В обох варіантах `config.ini` і лог лежать поруч з exe, автозапуск вказує на exe.

Для програми, що постійно висить у треї й стартує з Windows, трохи вигідніший `-OneDir`
(менше RAM, швидший старт). Один файл — коли важливіше, щоб його було легко передати.

Ресурси: у фоні ~25 MB RAM (onefile додатково тримає процес-завантажувач ~10 MB),
0% CPU — жодних хуків клавіатури чи опитування, лише `RegisterHotKey`. Tk підвантажується
тільки при першому відкритті налаштувань.

## Як це працює

1. `RegisterHotKey` → чекаємо, поки відпустите модифікатори.
2. Зберігаємо вміст буфера обміну, надсилаємо `Ctrl+C`.
3. Є текст — це виділення. Немає — `Ctrl+Shift+Left` (кілька разів, доки не зустрінеться
   пробіл) + `Ctrl+C`, щоб взяти останнє слово.
   Якщо скопійовано «рядок + перенос», це може бути і виділення, і копіювання рядка
   без виділення (VS Code, JetBrains тощо). Тоді `Shift+Left` + `Ctrl+C` перевіряє:
   було виділення — скопіюється рядок без переносу; не було — один символ.
   `Shift+Right` повертає все як було. Якщо `Shift+Left` нічого не змінив (курсор
   або зворотне виділення на початку поля), так само перевіряється `Shift+Right`.
4. Визначаємо розкладку тексту, конвертуємо по фізичних клавішах (`ToUnicodeEx`)
   у наступну, друкуємо результат юнікод-подіями `SendInput` (багаторядковий/довгий
   текст — вставкою через буфер).
5. Відновлюємо буфер обміну (з позначкою «не додавати в журнал Win+V») і перемикаємо
   розкладку вікна (`WM_INPUTLANGCHANGEREQUEST`).

Захист від втрати даних: конвертація переривається без зміни тексту (лунає системний
звук, причина пишеться в лог), якщо:

- буфер зайнятий або містить формат, який не вдається зберегти й відновити
  (наприклад, owner-display); растрові зображення та метафайли зберігаються;
- копіювання зірвалося посеред пошуку слова або межу слова не знайдено за 8 кроків;
- перевірка «виділення чи копія рядка» дала неоднозначний результат
  (рядок з одного символу);
- текст не записався в буфер перед вставкою;
- звужене виділення не збіглося з очікуваним.

## Обмеження

- Не працює у вікнах, запущених від адміністратора, якщо сама програма запущена без
  цих прав (обмеження Windows UIPI).
- Проміжний текст, скопійований через `Ctrl+C`, може потрапити в журнал буфера (Win+V).
- Консолі/термінали з нестандартними `Ctrl+C`/`Ctrl+Shift+Left` не підтримуються.
