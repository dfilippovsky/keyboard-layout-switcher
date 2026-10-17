"""Налаштування у config.ini поруч із програмою + автозапуск через реєстр."""
import configparser
import os
import sys
import winreg
from dataclasses import dataclass, asdict

APP_NAME = "KeyboardLayoutSwitcher"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.ini")

_TEMPLATE = """\
; Keyboard Layout Switcher — налаштування.
; Можна редагувати вручну, після чого в меню трею вибрати «Перечитати config.ini».

[general]
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
"""

HOTKEY_FIELDS = ("hotkey", "case_hotkey", "translit_hotkey")


@dataclass
class Config:
    hotkey: str = "Pause"
    case_hotkey: str = "Alt+Pause"
    translit_hotkey: str = "Ctrl+Pause"
    enabled: bool = True
    switch_layout: bool = True
    reselect: bool = True
    copy_timeout_ms: int = 250
    eye_breaks: bool = True
    eye_break_minutes: int = 20
    eye_break_popup_seconds: int = 5

    @classmethod
    def load(cls):
        cfg = cls()
        if not os.path.exists(CONFIG_PATH):
            cfg.save()
            return cfg
        cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
        cp.read(CONFIG_PATH, encoding="utf-8-sig")
        sec = cp["general"] if cp.has_section("general") else {}
        cfg.hotkey = sec.get("hotkey", cfg.hotkey).strip() or cfg.hotkey
        for key in ("case_hotkey", "translit_hotkey"):  # порожнє значення = вимкнено
            setattr(cfg, key, sec.get(key, getattr(cfg, key)).strip())
        for key in ("enabled", "switch_layout", "reselect", "eye_breaks"):
            try:
                setattr(cfg, key, cp.getboolean("general", key, fallback=getattr(cfg, key)))
            except ValueError:
                pass
        for key, lo, hi in (("copy_timeout_ms", 50, 5000), ("eye_break_minutes", 1, 240),
                            ("eye_break_popup_seconds", 0, 120)):
            try:
                setattr(cfg, key, max(lo, min(hi, cp.getint("general", key, fallback=getattr(cfg, key)))))
            except ValueError:
                pass
        return cfg

    def save(self):
        """Атомарний запис: тимчасовий файл + os.replace, тож при збої старий
        config.ini лишається цілим."""
        values = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in asdict(self).items()}
        tmp = CONFIG_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(_TEMPLATE.format(**values))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG_PATH)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


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
