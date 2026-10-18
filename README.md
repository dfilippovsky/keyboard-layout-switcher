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

### Auto-correct while typing

Like Punto Switcher: you don't even need the hotkey. Type `ghbdsn`, press `Space`, and the
word becomes `привіт ` and the window switches to the Ukrainian layout. It works the other
way too (`руддщ` → `hello`).

- **How a word is recognised.** The app keeps the keys of the current word. When you press
  `Space`, it compares how the word looks in the current layout and in the others. The word
  is retyped only if two things hold: what you typed is not a word, and in another layout it
  becomes one. A word counts if it is in the dictionary (the 30 000 most frequent words) or
  its letter trigrams look like that language. Case and punctuation are kept:
  `Ghbdsn` → `Привіт`, `lj,ht?` → `добре,`.
- **Short words** (`z`, `nf`, `yt`) are too ambiguous on their own (`plan b`), so they are
  fixed only together with the next word that gets fixed: `nf yt ghbqle` → `та не прийду`.
- **Undo:** press the layout hotkey (`Pause`) right after a correction. The text and layout
  go back, and the word is added to `autocorrect_exceptions.txt` next to the app, so it is
  never touched again. You can edit that file by hand: one word per line.
- **Words that keep their layout** (call signs, codes, numbers: `N01`, `NK701`,
  `EVAK1101`). The list is in `autocorrect_words.txt` next to the app, one word per line,
  case does not matter (tray menu → **Words that keep their layout…**; changes apply right
  away, no restart). Such a word typed in the wrong layout is fixed **before the space**:
  as soon as a digit appears and it is clear that this is a listed word, not an ordinary
  one. Type `Т0` and it becomes `N0`, the layout switches to English, and you keep typing
  in it. `ТЛ7` → `NK7`, `УМФЛ1` → `EVAK1`. It is enough that some listed word starts with
  what you typed: `N28` is fixed because `N20`…`N29` start that way. Digits can come from
  the NumPad too. A word without digits is fixed once it is typed in full, but only if no
  ordinary word of the current language starts that way; otherwise it is fixed at the
  space. Punctuation around the word stays as typed
  (`Т01,` → `N01,`). Fixing before the space needs layout switching (`switch_layout`);
  with it off, a listed word is fixed at the space. Undo works the same way, with the
  hotkey right after the fix, but the word is not added to `autocorrect_exceptions.txt`.
- **When it stays out of the way:** after arrows, `Home`/`End`, `Enter`, `Tab`, a mouse
  click, a shortcut (`Ctrl+…`), switching windows or layouts, or text inserted by other
  programs, it does nothing until the next word. It also skips fullscreen apps and games,
  the app's own windows, and programs listed in `autocorrect_exclude`.
- **Languages:** English and Ukrainian (data in `langdata/`). Layouts of other languages
  are left alone.
- **Privacy:** keystrokes are read through Raw Input, without keyboard hooks. Only the
  current word and a few short words before it are kept in memory, and the text is never
  written anywhere, the debug log included.

Turn it on or off in the tray menu or the settings (`autocorrect`).

### More tools

Each of these has its own hotkey and works on the selection or the last word, just like
the layout conversion, including reselecting the result:

| Default hotkey | Action | Tray flash |
|----------------|--------|------------|
| `Pause`        | Convert to the next keyboard layout | blue |
| `Alt+Pause`    | **Change case** in a cycle: `lower` → `UPPER` → `Title` → `camelCase` → `snake_case` → `kebab-case` | green |
| `Ctrl+Pause`   | **Transliterate** Ukrainian into Latin using the official system (Cabinet of Ministers Resolution No. 55, 2010): `Привіт` → `Pryvit`, `Згорани` → `Zghorany`, `Знам'янка` → `Znamianka` | purple |
| `Shift+Pause`  | **Ukrainian typography** (plugin `ua_typography`): `'` → `ʼ` inside words, `"…"` → `«…»` (nested `„…“`), ` - ` → ` — ` with a non-breaking space before it, `...` → `…`, repeated spaces → one | pink |

Plugins add more actions (see [Plugins](#plugins)). All actions are also in the tray menu
under **Actions**.

Case changing works out the current style and moves to the next one. Pressing the hotkey
again on the result keeps going round from the original text, so `kebab-case` → `lower`
puts the spaces back.

You don't have to release the modifier between steps, just like `Alt+Tab`: hold `Alt` and
press `Pause` as many times as you need (`Alt` + `Pause` `Pause` `Pause`). Each press is
applied right away and the tray icon blinks. This works for every hotkey that has a modifier,
layout conversion included. While the modifier is held, the app releases it *logically*
(otherwise the target app would receive `Ctrl+Alt+C` instead of `Ctrl+C`). It tracks the
physical key state through Raw Input, only for as long as the modifier is held, and
temporarily catches the bare key (`Pause`) so it does not reach the app. If you stop pressing
for 10 seconds, holding ends and the modifier state is restored.

<a id="plugins"></a>

### Plugins

A plugin is a Python file in the `plugins\` folder next to the app (tray menu →
**Open plugins folder**). Each file registers its actions, and each action gets an optional
hotkey and a tray menu item:

```python
# plugins\my_tools.py
def register(api):
    # Acts on the selection, or the word before the caret, like the built-in actions
    api.text_action("upper", "UPPER CASE", str.upper, hotkey="Ctrl+Alt+U")
    # Any code: ctx.window, ctx.notify(), ctx.edit_text(), ctx.type_text()
    api.action("hello", "Say hello", lambda ctx: ctx.notify("Hello!"))
    # Titles and texts in several languages: shown in the interface language
    api.text_action("lower", {"uk": "малі літери", "en": "lower case"}, str.lower)
```

- The full action id is `<file>.<id>`, e.g. `my_tools.upper`. A hotkey can be overridden or
  turned off (empty value) in the `[plugins]` section of `config.ini` or in the settings
  window. Only overrides are stored there, so a plugin's new default hotkey is picked up
  automatically.
- Files starting with `_` are not loaded. [`plugins\_template.py`](plugins/_template.py)
  describes the whole API: copy it under a new name.
- A title (and the text of `ctx.notify()`) is a string or a `{"uk": ..., "en": ...}`
  dictionary. The variant in the interface language is shown (English if it is missing),
  and it changes together with the language. `api.language` / `ctx.language` give the
  current one (`"uk"` or `"en"`).
- Bundled plugins: `ua_typography` (`Shift+Pause`, see above) and `lines` (sort lines,
  remove duplicates, reverse, number them; menu only).
- After adding or changing a plugin, use **Reload config.ini and plugins** in the tray menu.
  If a plugin fails to load or one of its actions raises an error, a tray notification
  says which one, and the details go to `layout_switcher.log`. The other plugins keep working.
- Plugins run inside the app with its rights. Install only plugins you trust.
- In the built exe, a plugin can use only the parts of the Python standard library that are
  bundled: everything the app uses, plus `json`, `csv`, `html`, `textwrap`,
  `unicodedata`, `difflib`, `datetime`, `random`, `secrets`, `uuid`, `hashlib`, `base64`,
  `statistics`, `decimal`, `urllib.request`/`http.client`/`ssl` (HTTPS requests),
  `webbrowser` and a few more (see `$forPlugins` in `build.ps1`). Run from source, the
  whole standard library is available.

**Eye breaks (20-20-20).** Every 20 minutes of screen time a quiet notification reminds you
to look at something about 6 m away for 20 seconds. It closes by itself after 5 seconds
(`eye_break_popup_seconds`). It does not show up while a fullscreen app, presentation or
Do Not Disturb is active, or while the microphone or camera is in use (a call). In those cases
it waits until they end. If you step away from the computer for 5 minutes (or it sleeps),
the countdown starts over. You can turn it on or off from the tray menu.

**Work breaks.** After 2 hours of continuous work (`work_break_minutes`) a notification says
“Ти вже 2 години без перерви” (“You've been working for 2 hours without a break”). Continuous
work is measured from idle data: 5 minutes without keyboard or mouse input, or sleep, counts
as a break and restarts the count. If you keep working, it reminds you again every 30 minutes.
It follows the same quiet rules as eye breaks (fullscreen, Do Not Disturb, calls). It stays
until Windows hides it, and it has its own icon and color so you can tell it from eye breaks.

The icon is [`languages`](https://lucide.dev/icons/languages) from Lucide (ISC); the eye
break notification uses [`hat-glasses`](https://lucide.dev/icons/hat-glasses) in a blue circle, the work
break one uses [`weight-tilde`](https://lucide.dev/icons/weight-tilde) in an orange circle.
In the tray it adapts to the light/dark taskbar theme, turns grey when disabled, and
briefly flashes in the action's color each time a hotkey is handled.

## Running

Only Python 3.10+ with the standard library (ctypes + tkinter) is required; there are no
third-party dependencies.

```powershell
.venv\Scripts\pythonw.exe main.py
```

Or build the exe (see below) and run `KeyboardLayoutSwitcher.exe`.

## Tray

- **Double-click** — settings window.
- **Right-click** — menu: **Actions** (every action with its hotkey; it runs on the window
  that was active before you clicked the tray), Enabled, Auto-correct layout while typing,
  20-20-20 eye breaks, Work break reminders, Settings…, Open config.ini, Reload config.ini and plugins,
  Open plugins folder, Exit.

The app finds the previously active window through a `WinEvent` foreground notification,
which is not a keyboard hook.

## Settings

The settings window has: the **interface language** (Ukrainian, English, or the same as
Windows), three hotkeys and the hotkeys of plugin actions (click a field
and press the combination; `Backspace` clears it and turns the action off; the layout
hotkey cannot be cleared),
enable/disable, layout switching, reselecting converted text, auto-correct while typing
and the programs where it is off, **start with Windows**, the copy timeout, eye break
reminders with their interval, and work break reminders with their threshold.

Everything is stored in `config.ini` next to `main.py` / the exe (created on first run):

| Key               | Default  | Description |
|-------------------|----------|-------------|
| `language`        | `auto`   | Interface language: `uk`, `en` or `auto` (Ukrainian if Windows is in Ukrainian, otherwise English). New comments in `config.ini` are written in this language. Existing comments are kept as they are when the file is updated, and change language only when the settings are saved (the file is then rewritten). |
| `hotkey`          | `Pause`  | Layout conversion. Combination: `Ctrl`/`Alt`/`Shift`/`Win` + key. Examples: `Shift+Pause`, `Ctrl+Alt+Space`, `Alt+F12`, `Win+VKE8`. |
| `case_hotkey`     | `Alt+Pause` | Case change. Empty — off. |
| `translit_hotkey` | `Ctrl+Pause` | Transliteration. Empty — off. |
| `enabled`         | `true`   | React to the hotkeys and auto-correct (master switch). |
| `switch_layout`   | `true`   | Switch the active window's layout after converting (and after auto-correct). |
| `autocorrect`     | `true`   | Auto-correct words typed in the wrong layout after `Space`. |
| `autocorrect_exclude` | *(empty)* | Programs where auto-correct is off: exe names separated by commas, e.g. `WindowsTerminal.exe, code.exe`. |
| `reselect`        | `true`   | Select the converted text again after converting a selection (skipped for text longer than 5000 characters). |
| `copy_timeout_ms` | `250`    | How long to wait for the app to put text on the clipboard after `Ctrl+C`. Increase for slow apps. |
| `eye_breaks`      | `true`   | 20-20-20 eye break reminders. |
| `eye_break_minutes` | `20`   | Reminder interval in minutes (1–240). |
| `eye_break_popup_seconds` | `5` | How long the notification stays before closing itself, in seconds (0–120; `0` lets Windows decide). |
| `work_breaks`     | `true`   | Remind to take a break after long continuous work. |
| `work_break_minutes` | `120` | Minutes of continuous work before the reminder (15–480); then every 30 minutes. |

The `[plugins]` section holds plugin hotkey overrides: `<action id> = <combination>` (an
empty value turns the hotkey off), e.g. `lines.sort = Ctrl+Alt+S`.

After editing the file manually, use “Reload config.ini and plugins” in the tray menu. The app writes
the file atomically (via a temporary `config.ini.tmp`), so a failed write never corrupts
the existing file. If `config.ini` comes from an older version and is missing some keys,
they are appended to the `[general]` section on load. Nothing else in the file changes:
values, your comments, extra keys and sections stay as they are. Saving from the settings
window or the tray menu rewrites the file from the template (the `[plugins]` section is
kept).

Key names: `A`–`Z`, `0`–`9`, `F1`–`F24`, `Pause`, `Space`, `Tab`, `Enter`, `Esc`,
`Backspace`, `Insert`, `Delete`, `Home`, `End`, `PageUp`, `PageDown`, `Left`/`Up`/`Right`/`Down`,
`CapsLock`, `ScrollLock`, `PrintScreen`, `Apps`, `Num0`–`Num9`, `NumPlus`, `NumMinus`,
`NumMul`, `NumDiv`, `NumDecimal`, `` ` `` `-` `=` `[` `]` `\` `;` `'` `,` `.` `/`,
or any virtual-key code as `VKxx` (hex). With `Ctrl` held, most keyboards send `Pause`
as `Break`, and `Ctrl+Pause` catches both.

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
.\build.ps1           # dist\KeyboardLayoutSwitcher.exe — single file (~13 MB)
.\build.ps1 -OneDir   # dist\KeyboardLayoutSwitcher\ — folder: faster start, one process
```

The script uses `.venv` if present, installs PyInstaller from `requirements-dev.txt`,
generates `app.ico` from the same icon, bundles `langdata\` and the standard library
modules meant for plugins into the exe, and copies `plugins\*.py` next to it. Your own
plugins there are left alone. The bundled ones are overwritten with the repository version,
so to change one, copy it under a different name first.

The language data for auto-correct (`langdata\*.txt.gz`) is generated by
`python tools\build_langdata.py [en uk …]` from the
[FrequencyWords](https://github.com/hermitdave/FrequencyWords) lists (© Hermit Dave,
data under CC BY-SA 4.0, built from OpenSubtitles). To add a language, add its alphabet to
`ALPHABETS` in the script and its script (Latin/Cyrillic/…) to `_SCRIPTS` in
`autocorrect.py`.

### Single file or folder

Same app, the only difference is packaging and startup:

|                  | Single file (default)                                  | Folder (`-OneDir`)                          |
|------------------|--------------------------------------------------------|---------------------------------------------|
| Output           | one `KeyboardLayoutSwitcher.exe` (~13 MB)              | folder with the exe and `_internal\` (Python, Tcl/Tk) |
| Startup          | unpacks itself into `%TEMP%\_MEIxxxxx` every time      | starts right away, nothing to unpack        |
| Processes        | two: bootloader (~10 MB) + the app                     | one                                         |
| Start time       | slower                                                 | faster                                      |
| Leftovers in TEMP| removed on exit; left behind if the process is killed  | none                                        |
| Antivirus        | more often suspicious of self-extracting exes          | less often                                  |
| Distribution     | one file — easy to copy/share                          | the whole folder has to be moved            |

In both cases `config.ini`, `autocorrect_exceptions.txt`, `autocorrect_words.txt`, `plugins\` and the log live next
to the exe, and autostart points to the exe. `build.ps1` keeps your files there, for
`-OneDir` too, where PyInstaller recreates the whole folder. It also adds the keys of the new
version to `config.ini`; if there is no file yet, it creates one with the defaults. While
building, a copy of these files is kept in `build\`. It is put back even if the build fails,
and a copy left behind by an interrupted build is restored on the next run.

For an app that sits in the tray all the time and starts with Windows, `-OneDir` is a bit
better (less RAM, faster start). Use the single file when easy sharing matters more.

Resources: ~25 MB RAM in the background (onefile additionally keeps a ~10 MB bootloader
process), plus ~10 MB for the language data when auto-correct is on. CPU use is next to
zero: there are no keyboard hooks or polling, just `RegisterHotKey` and one timer check per
minute for breaks. Raw Input is used in three cases. Keyboard events are read only while
auto-correct is on, or while a hotkey modifier is held. Mouse buttons are watched only while
a word is being typed, since a click may move the caret. After 3 minutes without input, the
app waits for the first key press or mouse movement to measure the exact length of the
pause (only the time of that event is used), then stops listening. While you are away there
are no events, so this costs nothing. Tk is loaded only when the settings
window is opened for the first time.

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
- Auto-correct retypes the word with `Backspace` and has to trust that the text before the
  caret is what was typed. In fields with inline autocomplete (a browser address bar) or
  where `Space` accepts a suggestion, add the program to `autocorrect_exclude`. Keys sent by
  remapping tools (e.g. PowerToys Keyboard Manager) count as inserted text, so words typed
  through them are not corrected. Characters typed with dead keys are not handled either.

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

### Автовиправлення під час набору

Як у Punto Switcher, і гаряча клавіша навіть не потрібна. Набираєте `ghbdsn`, тиснете
`Пробіл`, і слово стає `привіт `, а розкладка вікна перемикається на українську. Працює й
навпаки (`руддщ` → `hello`).

- **Як розпізнається слово.** Програма запам'ятовує клавіші поточного слова. Після
  пробілу вона порівнює, як воно виглядає в поточній розкладці та в інших. Передрук буде,
  лише якщо виконуються обидві умови: набране не є словом, а в іншій розкладці виходить
  слово. Словом вважається те, що є в словнику (30 000 найчастіших слів) або чиї трибуквені
  сполучення схожі на цю мову. Регістр і розділові знаки зберігаються:
  `Ghbdsn` → `Привіт`, `lj,ht?` → `добре,`.
- **Короткі слова** (`z`, `nf`, `yt`) самі по собі надто неоднозначні (`plan b`), тому
  виправляються лише разом із наступним словом, яке теж виправилося:
  `nf yt ghbqle` → `та не прийду`.
- **Скасувати:** одразу після виправлення натисніть гарячу клавішу розкладки (`Pause`).
  Текст і розкладка повернуться, а слово запишеться в `autocorrect_exceptions.txt` поруч
  із програмою, і більше його не чіпатимуть. Файл можна редагувати вручну: одне слово в рядку.
- **Слова, що завжди у своїй розкладці** (позивні, коди, номери: `N01`, `NK701`,
  `EVAK1101`). Список лежить в `autocorrect_words.txt` поруч із програмою, по одному слову
  в рядку, великі й малі літери не розрізняються (меню трею →
  **Слова, що завжди у своїй розкладці…**; зміни діють одразу, без перезапуску). Таке
  слово, набране не в тій розкладці, виправляється ще **до пробілу**: щойно з'являється
  цифра, і стає ясно, що це слово зі списку, а не звичайне. Набрали `Т0`: воно стає `N0`,
  розкладка перемикається на англійську, і далі ви друкуєте вже в ній. `ТЛ7` → `NK7`,
  `УМФЛ1` → `EVAK1`. Досить, щоб із набраного починалося якесь слово зі списку: `N28`
  виправиться, бо так починаються `N20`…`N29`. Цифри можна набирати й на NumPad. Слово
  без цифр виправляється, коли воно набране повністю, але лише якщо в поточній мові так
  не починається жодне звичайне слово; інакше — на пробілі. Розділові знаки навколо слова лишаються як є (`Т01,` → `N01,`).
  Без пробілу це працює лише з перемиканням розкладки (`switch_layout`); якщо воно
  вимкнене, слово зі списку виправляється на пробілі. Скасовується так само, гарячою
  клавішею одразу після виправлення, але до `autocorrect_exceptions.txt` слово не потрапляє.
- **Коли не втручається:** після стрілок, `Home`/`End`, `Enter`, `Tab`, кліку мишею,
  комбінацій (`Ctrl+…`), перемикання вікна чи розкладки, а також тексту, вставленого
  іншими програмами, — до наступного слова нічого не робить. Не працює в повноекранних
  програмах та іграх, у вікнах самої програми і в програмах з `autocorrect_exclude`.
- **Мови:** англійська й українська (дані в `langdata/`). Розкладки інших мов
  автовиправлення не чіпає.
- **Приватність:** натискання читаються через Raw Input, без хуків клавіатури. У пам'яті
  тримаються лише поточне слово й кілька коротких перед ним. Текст ніде не записується,
  навіть у детальний лог.

Вмикається й вимикається в меню трею або в налаштуваннях (`autocorrect`).

### Інші інструменти

Кожен має свою гарячу клавішу й працює з виділенням або останнім словом так само, як
конвертація розкладки, зокрема з повторним виділенням результату:

| Клавіша за замовчуванням | Дія | Колір у треї |
|--------------------------|-----|--------------|
| `Pause`      | Конвертація в наступну розкладку | синій |
| `Alt+Pause`  | **Регістр** по колу: `lower` → `UPPER` → `Title` → `camelCase` → `snake_case` → `kebab-case` | зелений |
| `Ctrl+Pause` | **Транслітерація** українського тексту латиницею за офіційною системою (постанова КМУ № 55 від 2010 р.): `Привіт` → `Pryvit`, `Згорани` → `Zghorany`, `Знам'янка` → `Znamianka` | фіолетовий |
| `Shift+Pause` | **Українська типографіка** (плагін `ua_typography`): `'` → `ʼ` усередині слів, `"…"` → `«…»` (вкладені `„…“`), ` - ` → ` — ` з нерозривним пробілом перед ним, `...` → `…`, кілька пробілів → один | рожевий |

Плагіни додають інші дії (див. [Плагіни](#plugins-uk)). Усі дії є й у меню трею, у пункті
**Дії**.

Регістр визначає поточний стиль тексту й переходить до наступного. Повторні натискання
на результаті йдуть далі по колу від початкового тексту, тож `kebab-case` → `lower`
повертає пробіли.

Модифікатор між кроками відпускати не треба, як з `Alt+Tab`: тримайте `Alt` і натискайте
`Pause` скільки потрібно (`Alt` + `Pause` `Pause` `Pause`). Кожне натискання застосовується
одразу, іконка в треї блимає. Так працюють усі гарячі клавіші з модифікатором, зокрема
конвертація розкладки. Поки модифікатор утримується, програма *логічно* його відпускає
(інакше програма отримала б `Ctrl+Alt+C` замість `Ctrl+C`). Фізичний стан клавіш вона
стежить через Raw Input лише на час утримання, а саму клавішу (`Pause`) тимчасово
перехоплює, щоб та не дійшла до програми. Якщо 10 секунд нічого не натискати, утримання
завершується, а стан модифікатора повертається.

<a id="plugins-uk"></a>

### Плагіни

Плагін — це Python-файл у папці `plugins\` поруч із програмою (меню трею → **Відкрити папку
плагінів**). Кожен файл реєструє свої дії, і кожна дія отримує необов'язкову гарячу
клавішу та пункт у меню трею:

```python
# plugins\my_tools.py
def register(api):
    # Працює з виділенням або словом перед курсором, як вбудовані дії
    api.text_action("upper", "ВЕЛИКІ ЛІТЕРИ", str.upper, hotkey="Ctrl+Alt+U")
    # Довільний код: ctx.window, ctx.notify(), ctx.edit_text(), ctx.type_text()
    api.action("hello", "Привітання", lambda ctx: ctx.notify("Привіт!"))
    # Назви й тексти кількома мовами: показується мовою інтерфейсу
    api.text_action("lower", {"uk": "малі літери", "en": "lower case"}, str.lower)
```

- Повний ідентифікатор дії — `<файл>.<id>`, наприклад `my_tools.upper`. Гарячу клавішу можна
  перевизначити або вимкнути (порожнім значенням) у секції `[plugins]` файлу `config.ini`
  чи у вікні налаштувань. Там зберігаються лише перевизначення, тож нову типову клавішу
  плагіна буде підхоплено автоматично.
- Файли, що починаються з `_`, не завантажуються. У [`plugins\_template.py`](plugins/_template.py)
  описано весь API: скопіюйте його під новим ім'ям.
- Назва (і текст `ctx.notify()`) — рядок або словник `{"uk": ..., "en": ...}`. Показується
  варіант мовою інтерфейсу (якщо його немає — англійський), і він змінюється разом із
  мовою. Поточну мову дають `api.language` / `ctx.language` (`"uk"` або `"en"`).
- Плагіни в комплекті: `ua_typography` (`Shift+Pause`, див. вище) і `lines` (упорядкувати
  рядки, прибрати повтори, розвернути, пронумерувати; лише з меню).
- Після додавання чи зміни плагіна — меню трею **Перечитати config.ini і плагіни**. Якщо
  плагін не завантажився або його дія впала з помилкою, сповіщення в треї скаже, який саме,
  а подробиці підуть у `layout_switcher.log`. Решта плагінів працює далі.
- Плагіни виконуються всередині програми з її правами. Ставте лише ті, яким довіряєте.
- У зібраному exe плагіну доступна лише та частина стандартної бібліотеки Python, яка є
  в exe: усе, чим користується сама програма, плюс `json`, `csv`, `html`, `textwrap`,
  `unicodedata`, `difflib`, `datetime`, `random`, `secrets`, `uuid`, `hashlib`, `base64`,
  `statistics`, `decimal`, `urllib.request`/`http.client`/`ssl` (HTTPS-запити),
  `webbrowser` та ще кілька модулів (див. `$forPlugins` у `build.ps1`). Під час запуску
  з вихідного коду доступна вся стандартна бібліотека.

**Перерви для очей (20-20-20).** Кожні 20 хвилин роботи за екраном тихе сповіщення
нагадує подивитися 20 секунд на щось на відстані ~6 м. Закривається саме через 5 секунд
(`eye_break_popup_seconds`). Не з'являється, поки відкрито повноекранну програму чи
презентацію, увімкнено «Не турбувати» або зайнятий мікрофон чи камера (дзвінок). Тоді
нагадування чекає, доки це закінчиться. Якщо ви відійшли від комп'ютера на 5 хвилин (або
він спав), відлік починається заново. Вмикається й вимикається в меню трею.

**Перерви в роботі.** Після 2 годин безперервної роботи (`work_break_minutes`) сповіщення
нагадує: «Ти вже 2 години без перерви». Безперервну роботу визначаємо за даними про
бездіяльність: 5 хвилин без клавіатури й миші (або сон комп'ютера) вважаються перервою, і
відлік починається заново. Якщо перерви так і не було, нагадування повторюється кожні
30 хвилин. Правила тиші ті самі, що й для очей (повноекранний режим, «Не турбувати»,
дзвінки). Саме не закривається (лише як вирішить Windows) і має власну іконку й колір,
щоб не плутати з нагадуванням для очей.

Іконка сповіщення про перерву — [`hat-glasses`](https://lucide.dev/icons/hat-glasses)
з Lucide (ISC) у синьому колі, про перерву в роботі —
[`weight-tilde`](https://lucide.dev/icons/weight-tilde) у помаранчевому колі.

Іконка програми — [`languages`](https://lucide.dev/icons/languages) з Lucide (ISC),
в треї підлаштовується під світлу/темну тему панелі задач, сіра — коли вимкнено,
і коротко блимає кольором дії щоразу, коли гаряча клавіша оброблена.

## Запуск

Потрібен лише Python 3.10+ зі стандартною бібліотекою (ctypes + tkinter), сторонніх
залежностей немає.

```powershell
.venv\Scripts\pythonw.exe main.py
```

Або зберіть exe (див. нижче) і запускайте `KeyboardLayoutSwitcher.exe`.

## Трей

- **Подвійний клік** — вікно налаштувань.
- **Правий клік** — меню: **Дії** (усі дії з гарячими клавішами; виконуються для вікна,
  яке було активним до кліку по треї), Увімкнено, Автовиправлення розкладки під час набору,
  Нагадування 20-20-20, Нагадування про перерву в роботі, Налаштування…, Відкрити config.ini, Перечитати config.ini і плагіни,
  Відкрити папку плагінів, Вихід.

Попереднє активне вікно програма визначає через сповіщення `WinEvent` про зміну активного
вікна, а не через хук клавіатури.

## Налаштування

Вікно налаштувань: **мова інтерфейсу** (українська, англійська або як у Windows), три
гарячі клавіші й гарячі клавіші дій з плагінів (клацніть у поле
й натисніть комбінацію; `Backspace` очищує клавішу й вимикає дію; клавішу розкладки
очистити не можна),
увімкнення, перемикання розкладки, повторне виділення, автовиправлення під час набору
і програми, де воно вимкнене, **запуск разом з Windows**, затримка очікування копіювання,
нагадування для очей та їхній інтервал, нагадування про перерву в роботі та його поріг.

Усе зберігається в `config.ini` поруч із `main.py` / exe (створюється при першому запуску):

| Ключ              | За замовчуванням | Опис |
|-------------------|------------------|------|
| `language`        | `auto`           | Мова інтерфейсу: `uk`, `en` або `auto` (українська, якщо Windows українською, інакше англійська). Нові коментарі в `config.ini` пишуться цією мовою. Наявні коментарі під час оновлення файлу лишаються як є і змінюють мову лише після збереження налаштувань (тоді файл перезаписується). |
| `hotkey`          | `Pause`          | Конвертація розкладки. Комбінація: `Ctrl`/`Alt`/`Shift`/`Win` + клавіша. Приклади: `Shift+Pause`, `Ctrl+Alt+Space`, `Alt+F12`, `Win+VKE8`. |
| `case_hotkey`     | `Alt+Pause`      | Зміна регістру. Порожньо — вимкнено. |
| `translit_hotkey` | `Ctrl+Pause`     | Транслітерація. Порожньо — вимкнено. |
| `enabled`         | `true`           | Реагувати на гарячі клавіші й автовиправлення (загальний вимикач). |
| `switch_layout`   | `true`           | Після конвертації (і автовиправлення) перемикати розкладку активного вікна. |
| `autocorrect`     | `true`           | Автовиправлення слів, набраних не в тій розкладці, після `Пробілу`. |
| `autocorrect_exclude` | *(порожньо)* | Програми, де автовиправлення вимкнене: імена exe через кому, напр. `WindowsTerminal.exe, code.exe`. |
| `reselect`        | `true`           | Після конвертації виділеного тексту виділяти його знову (для тексту довшого за 5000 символів пропускається). |
| `copy_timeout_ms` | `250`            | Скільки чекати, поки програма віддасть текст на `Ctrl+C`. Збільште для повільних програм. |
| `eye_breaks`      | `true`           | Нагадування 20-20-20 для очей. |
| `eye_break_minutes` | `20`           | Інтервал нагадувань, хв (1–240). |
| `eye_break_popup_seconds` | `5`      | Через скільки секунд сповіщення закривається само (0–120; `0` — як вирішить Windows). |
| `work_breaks`     | `true`           | Нагадування про перерву після тривалої безперервної роботи. |
| `work_break_minutes` | `120`         | Скільки хвилин безперервної роботи до нагадування (15–480); далі — кожні 30 хв. |

У секції `[plugins]` зберігаються перевизначення гарячих клавіш плагінів:
`<id дії> = <комбінація>` (порожнє значення вимикає клавішу), наприклад
`lines.sort = Ctrl+Alt+S`.

Після ручного редагування — меню трею «Перечитати config.ini і плагіни». Програма записує файл
атомарно (через тимчасовий `config.ini.tmp`), тож збій запису не пошкодить чинний файл.
Якщо `config.ini` від старішої версії і в ньому бракує ключів, вони дописуються в секцію
`[general]` при завантаженні. Решта файлу не змінюється: значення, ваші коментарі, зайві
ключі й секції лишаються як є. Збереження з вікна налаштувань чи меню трею переписує файл
за шаблоном (секція `[plugins]` зберігається).

Назви клавіш: `A`–`Z`, `0`–`9`, `F1`–`F24`, `Pause`, `Space`, `Tab`, `Enter`, `Esc`,
`Backspace`, `Insert`, `Delete`, `Home`, `End`, `PageUp`, `PageDown`, `Left`/`Up`/`Right`/`Down`,
`CapsLock`, `ScrollLock`, `PrintScreen`, `Apps`, `Num0`–`Num9`, `NumPlus`, `NumMinus`,
`NumMul`, `NumDiv`, `NumDecimal`, `` ` `` `-` `=` `[` `]` `\` `;` `'` `,` `.` `/`,
або будь-який віртуальний код як `VKxx` (hex). З `Ctrl` більшість клавіатур надсилає
`Pause` як `Break`, тож `Ctrl+Pause` ловить обидва варіанти.

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
.\build.ps1           # dist\KeyboardLayoutSwitcher.exe — один файл (~13 MB)
.\build.ps1 -OneDir   # dist\KeyboardLayoutSwitcher\ — папка: швидший старт, один процес
```

Скрипт використовує `.venv`, якщо він є, ставить PyInstaller з `requirements-dev.txt`,
генерує `app.ico` з тієї ж іконки, вкладає в exe `langdata\` і модулі стандартної
бібліотеки для плагінів, а `plugins\*.py` копіює поруч з exe. Ваші власні плагіни там
лишаються недоторканими. Плагіни з комплекту перезаписуються версією з репозиторію, тож
щоб змінити такий плагін, спершу скопіюйте його під іншим ім'ям.

Мовні дані автовиправлення (`langdata\*.txt.gz`) генерує
`python tools\build_langdata.py [en uk …]` з частотних словників
[FrequencyWords](https://github.com/hermitdave/FrequencyWords) (© Hermit Dave, дані під
CC BY-SA 4.0, зібрані з OpenSubtitles). Щоб додати мову, допишіть її алфавіт в `ALPHABETS`
у скрипті, а письмо (латиниця/кирилиця/…) — в `_SCRIPTS` в `autocorrect.py`.

### Один файл чи папка

Програма та сама, різниця лише в упаковці та запуску:

|                     | Один файл (за замовчуванням)                     | Папка (`-OneDir`)                         |
|---------------------|--------------------------------------------------|-------------------------------------------|
| Результат           | один `KeyboardLayoutSwitcher.exe` (~13 MB)       | папка з exe і `_internal\` (Python, Tcl/Tk) |
| Запуск              | щоразу розпаковує себе в `%TEMP%\_MEIxxxxx`      | запускається одразу, без розпаковки       |
| Процеси             | два: завантажувач (~10 MB) + програма            | один                                      |
| Старт               | повільніший                                      | швидший                                   |
| Слід у TEMP         | прибирається при виході; лишається, якщо процес вбити | немає                                |
| Антивіруси          | частіше насторожено ставляться до самопакованих exe | рідше                                  |
| Поширення           | один файл — зручно скопіювати/передати           | треба переносити всю папку                |

В обох варіантах `config.ini`, `autocorrect_exceptions.txt`, `autocorrect_words.txt`, `plugins\` і лог лежать поруч
з exe, автозапуск вказує на exe. `build.ps1` зберігає ваші файли там, і для `-OneDir` теж,
де PyInstaller перестворює всю папку. У `config.ini` він дописує ключі нової версії; якщо
файлу ще немає — створює його з налаштуваннями за замовчуванням. На час збірки копія цих
файлів лежить у `build\`. Вона повертається навіть тоді, коли збірка падає, а копія, що
лишилася від перерваної збірки, відновлюється при наступному запуску.

Для програми, що постійно висить у треї й стартує з Windows, трохи вигідніший `-OneDir`
(менше RAM, швидший старт). Один файл — коли важливіше, щоб його було легко передати.

Ресурси: у фоні ~25 MB RAM (onefile додатково тримає процес-завантажувач ~10 MB), плюс
~10 MB на мовні дані, коли автовиправлення увімкнене. Процесор майже не навантажується:
жодних хуків клавіатури чи опитування, лише `RegisterHotKey` й одна перевірка таймера на
хвилину для перерв. Raw Input задіяний у трьох випадках. Події клавіатури читаються лише
поки увімкнене автовиправлення або утримується модифікатор гарячої клавіші. Кнопки миші
відстежуються тільки поки набирається слово, бо клік може зсунути курсор. Після 3 хвилин
без введення програма чекає на перше натискання чи рух миші, щоб точно виміряти тривалість
паузи (береться лише час цієї події), і одразу перестає слухати. Поки вас немає, подій
немає, тож це нічого не коштує.
Tk підвантажується тільки при першому відкритті налаштувань.

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
- Автовиправлення передруковує слово через `Backspace` і мусить покладатися на те, що
  перед курсором саме набраний текст. У полях з автодоповненням у рядку (адресний рядок
  браузера) чи там, де `Пробіл` приймає підказку, додайте програму в `autocorrect_exclude`.
  Натискання від програм перепризначення клавіш (наприклад, PowerToys Keyboard Manager)
  вважаються вставленим текстом, тож набрані через них слова не виправляються. Не
  враховуються й символи, набрані через «мертві» клавіші.
