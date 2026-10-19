"""Налаштування у config.ini поруч із програмою + автозапуск через реєстр."""
import codecs
import configparser
import os
import re
import sys
import winreg
from dataclasses import dataclass, asdict, field

import i18n

APP_NAME = "KeyboardLayoutSwitcher"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.ini")

_TEMPLATES = {
    "uk": """\
; Keyboard Layout Switcher — налаштування.
; Можна редагувати вручну, після чого в меню трею вибрати «Перечитати config.ini».

[general]
; Мова інтерфейсу: auto (як у Windows), uk, en
language = {language}
; Гаряча клавіша конвертації розкладки: Ctrl/Alt/Shift/Win + клавіша.
; Приклади: Pause, Shift+Pause, Ctrl+Alt+Space, Alt+F12
hotkey = {hotkey}
; Зміна регістру по колу: lower → UPPER → Title → camelCase → snake_case → kebab-case
; (порожньо — вимкнено)
case_hotkey = {case_hotkey}
; Транслітерація українського тексту латиницею (порожньо — вимкнено)
translit_hotkey = {translit_hotkey}
; Реагувати на гарячі клавіші (true/false)
enabled = {enabled}
; Після конвертації перемикати розкладку активного вікна на цільову
switch_layout = {switch_layout}
; Автовиправлення під час набору: слово, набране не в тій розкладці (ghbdsn), після
; пробілу стає правильним (привіт). Скасувати — одразу натиснути гарячу клавішу розкладки.
autocorrect = {autocorrect}
; Програми, в яких не виправляти, через кому (ім'я exe), напр.: WindowsTerminal.exe, code.exe
autocorrect_exclude = {autocorrect_exclude}
; Після конвертації виділеного тексту виділити його знову (повторне натискання — наступна розкладка)
reselect = {reselect}
; Скільки чекати (мс), поки програма скопіює текст у буфер після Ctrl+C
copy_timeout_ms = {copy_timeout_ms}
; Нагадування 20-20-20: кожні N хвилин подивитися вдалину (true/false)
eye_breaks = {eye_breaks}
; Інтервал нагадувань, хв (1–240)
eye_break_minutes = {eye_break_minutes}
; Через скільки секунд сповіщення закривається само (0 — як вирішить Windows)
eye_break_popup_seconds = {eye_break_popup_seconds}
; Нагадування про перерву після тривалої роботи без перерви (true/false).
; Перервою вважається 5 хв без клавіатури й миші або сон комп'ютера.
work_breaks = {work_breaks}
; Скільки хвилин безперервної роботи до нагадування (15–480); далі — кожні 30 хв
work_break_minutes = {work_break_minutes}
""",
    "en": """\
; Keyboard Layout Switcher — settings.
; You can edit them by hand, then choose “Reload config.ini and plugins” in the tray menu.

[general]
; Interface language: auto (same as Windows), uk, en
language = {language}
; Layout conversion hotkey: Ctrl/Alt/Shift/Win + key.
; Examples: Pause, Shift+Pause, Ctrl+Alt+Space, Alt+F12
hotkey = {hotkey}
; Case cycling: lower → UPPER → Title → camelCase → snake_case → kebab-case
; (empty — off)
case_hotkey = {case_hotkey}
; Transliteration of Ukrainian text into Latin letters (empty — off)
translit_hotkey = {translit_hotkey}
; React to the hotkeys (true/false)
enabled = {enabled}
; After converting, switch the active window's layout to the target one
switch_layout = {switch_layout}
; Auto-correct while typing: a word typed in the wrong layout (ghbdsn) becomes the right
; one (привіт) after a space. To undo, press the layout hotkey right away.
autocorrect = {autocorrect}
; Programs where auto-correct is off, separated by commas (exe name), e.g.: WindowsTerminal.exe, code.exe
autocorrect_exclude = {autocorrect_exclude}
; After converting selected text, select it again (pressing again gives the next layout)
reselect = {reselect}
; How long to wait (ms) for the program to copy text to the clipboard after Ctrl+C
copy_timeout_ms = {copy_timeout_ms}
; 20-20-20 reminders: every N minutes look into the distance (true/false)
eye_breaks = {eye_breaks}
; Reminder interval, min (1–240)
eye_break_minutes = {eye_break_minutes}
; After how many seconds the notification closes by itself (0 — let Windows decide)
eye_break_popup_seconds = {eye_break_popup_seconds}
; Remind to take a break after long work without one (true/false).
; A break is 5 min without keyboard and mouse, or the computer sleeping.
work_breaks = {work_breaks}
; Minutes of continuous work before the reminder (15–480); then every 30 min
work_break_minutes = {work_break_minutes}
""",
}

_PLUGINS_HEADERS = {
    "uk": """
[plugins]
; Гарячі клавіші дій з плагінів (plugins\\*.py): id дії = комбінація; порожньо — вимкнено.
; Дії, яких тут немає, використовують комбінацію, яку задав сам плагін.
""",
    "en": """
[plugins]
; Hotkeys of plugin actions (plugins\\*.py): action id = combination; empty — off.
; Actions not listed here use the combination set by the plugin itself.
""",
}
LANGUAGE_SETTINGS = ("auto",) + i18n.LANGUAGES

HOTKEY_FIELDS = ("hotkey", "case_hotkey", "translit_hotkey")
_SECTION_RE = re.compile(r"\[(?P<name>.+)\]$")
_INLINE_COMMENT_RE = re.compile(r"\s[;#]")


def _section_name(line):
    """Назва секції, якщо рядок — її заголовок (як його бачить configparser
    з inline_comment_prefixes=(";", "#")), інакше None."""
    s = line.strip()
    if not s or s[0] in ";#":
        return None
    m = _SECTION_RE.match(_INLINE_COMMENT_RE.split(s, 1)[0].strip())
    return m.group("name") if m else None


@dataclass
class Config:
    language: str = "auto"       # auto | uk | en
    hotkey: str = "Pause"
    case_hotkey: str = "Alt+Pause"
    translit_hotkey: str = "Ctrl+Pause"
    enabled: bool = True
    switch_layout: bool = True
    autocorrect: bool = True
    autocorrect_exclude: str = ""
    reselect: bool = True
    copy_timeout_ms: int = 250
    eye_breaks: bool = True
    eye_break_minutes: int = 20
    eye_break_popup_seconds: int = 5
    work_breaks: bool = True
    work_break_minutes: int = 120
    # Секція [plugins]: id дії плагіна -> комбінація (перевизначає ту, що задав плагін)
    plugin_hotkeys: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path=CONFIG_PATH):
        """Прочитати config.ini. Якщо файлу немає — створити; якщо в ньому бракує
        ключів (файл від старішої версії) — дописати їх, зберігши наявні значення."""
        cfg = cls()
        if not os.path.exists(path):
            cfg.save(path)
            return cfg
        cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
        cp.read(path, encoding="utf-8-sig")
        sec = cp["general"] if cp.has_section("general") else {}
        cfg.hotkey = sec.get("hotkey", cfg.hotkey).strip() or cfg.hotkey
        language = sec.get("language", cfg.language).strip().lower()
        cfg.language = language if language in LANGUAGE_SETTINGS else cfg.language
        for key in ("case_hotkey", "translit_hotkey", "autocorrect_exclude"):  # порожнє = вимкнено / нічого
            setattr(cfg, key, sec.get(key, getattr(cfg, key)).strip())
        for key in ("enabled", "switch_layout", "autocorrect", "reselect", "eye_breaks", "work_breaks"):
            try:
                setattr(cfg, key, cp.getboolean("general", key, fallback=getattr(cfg, key)))
            except ValueError:
                pass
        for key, lo, hi in (("copy_timeout_ms", 50, 5000), ("eye_break_minutes", 1, 240),
                            ("eye_break_popup_seconds", 0, 120), ("work_break_minutes", 15, 480)):
            try:
                setattr(cfg, key, max(lo, min(hi, cp.getint("general", key, fallback=getattr(cfg, key)))))
            except ValueError:
                pass
        if cp.has_section("plugins"):  # порожнє значення = гарячу клавішу дії вимкнено
            cfg.plugin_hotkeys = {key: value.strip() for key, value in cp.items("plugins")}
        missing = [key for key in asdict(cfg) if key in _GENERAL_KEYS and not cp.has_option("general", key)]
        if missing:
            try:
                _append_missing(path, cfg._values(), missing)
            except OSError:
                pass  # не вдалося дописати (лише для читання) — працюємо зі значеннями за замовчуванням
        return cfg

    def excluded_apps(self):
        """Множина імен exe (у нижньому регістрі), де автовиправлення вимкнене."""
        return {name.strip().lower() for name in self.autocorrect_exclude.split(",") if name.strip()}

    def _values(self):
        return {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in asdict(self).items()}

    def save(self, path=CONFIG_PATH):
        lang = i18n.resolve(self.language)
        text = _TEMPLATES[lang].format(**self._values())
        if self.plugin_hotkeys:
            text += _PLUGINS_HEADERS[lang] + "".join("%s = %s\n" % item for item in sorted(self.plugin_hotkeys.items()))
        write_atomic(path, text)


_GENERAL_KEYS = frozenset(Config.__dataclass_fields__) - {"plugin_hotkeys"}  # ключі секції [general]


def write_atomic(path, text, newline=None):
    """Тимчасовий файл + os.replace, тож при збої старий config.ini лишається цілим."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _key_blocks(values):
    """Рядки шаблону для кожного ключа секції [general]: його коментарі + «ключ = значення»."""
    blocks, comments, in_general = {}, [], False
    for line in _TEMPLATES[i18n.resolve(values["language"])].format(**values).splitlines():
        if line.strip() == "[general]":
            in_general = True
        elif in_general and line.startswith(";"):
            comments.append(line)
        elif in_general and "=" in line:
            blocks[line.split("=", 1)[0].strip()] = comments + [line]
            comments = []
    return blocks


def _append_missing(path, values, missing):
    """Дописати відсутні ключі (з коментарями з шаблону) в кінець секції [general],
    не чіпаючи решти файлу: власні коментарі, зайві ключі й інші секції лишаються як є."""
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    blocks = _key_blocks(values)
    added = [line + nl for key in missing for line in blocks[key]]

    start = next((i for i, line in enumerate(lines) if _section_name(line) == "general"), None)
    if start is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        lines += ([nl] if lines else []) + ["[general]" + nl] + added
    else:
        end = next((i for i in range(start + 1, len(lines)) if _section_name(lines[i]) is not None),
                   len(lines))
        pos = end
        while pos > start + 1 and not lines[pos - 1].strip():
            pos -= 1  # після останнього непорожнього рядка секції, перед порожніми
        if not lines[pos - 1].endswith(("\n", "\r")):
            lines[pos - 1] += nl
        lines[pos:pos] = added
    write_atomic(path, ("﻿" if bom else "") + "".join(lines), newline="")


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return '"%s" "%s"' % (pyw if os.path.exists(pyw) else exe, os.path.abspath(sys.argv[0]))


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, APP_NAME)[0])
    except OSError:
        return False


def set_autostart(on):
    if on:
        # CreateKeyEx створює ключ Run, якщо його ще немає в профілі
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except FileNotFoundError:
        pass  # немає ключа Run або значення — автозапуск і так вимкнений
