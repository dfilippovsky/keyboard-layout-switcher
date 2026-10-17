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
; Гаряча клавіша: Ctrl/Alt/Shift/Win + клавіша. Приклади: Pause, Shift+Pause, Ctrl+Alt+Space, Alt+F12
hotkey = {hotkey}
; Реагувати на гарячу клавішу (true/false)
enabled = {enabled}
; Після конвертації перемикати розкладку активного вікна на цільову
switch_layout = {switch_layout}
; Після конвертації виділеного тексту виділити його знову (повторне натискання — наступна розкладка)
reselect = {reselect}
; Скільки чекати (мс), поки програма скопіює текст у буфер після Ctrl+C
copy_timeout_ms = {copy_timeout_ms}
; Програми (exe через кому), які без виділення копіюють по Ctrl+C увесь рядок.
; Лише в них однорядковий текст із переносом у кінці не вважається виділенням.
line_copy_apps = {line_copy_apps}
"""

DEFAULT_LINE_COPY_APPS = (
    "code.exe, code - insiders.exe, cursor.exe, windsurf.exe, devenv.exe, sublime_text.exe, "
    "notepad++.exe, idea64.exe, pycharm64.exe, webstorm64.exe, phpstorm64.exe, rider64.exe, "
    "clion64.exe, goland64.exe, rubymine64.exe, datagrip64.exe, studio64.exe"
)


@dataclass
class Config:
    hotkey: str = "Pause"
    enabled: bool = True
    switch_layout: bool = True
    reselect: bool = True
    copy_timeout_ms: int = 250
    line_copy_apps: str = DEFAULT_LINE_COPY_APPS

    def line_copy_app_set(self):
        return {a.strip().lower() for a in self.line_copy_apps.split(",") if a.strip()}

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
        cfg.line_copy_apps = sec.get("line_copy_apps", cfg.line_copy_apps).strip()
        for key in ("enabled", "switch_layout", "reselect"):
            try:
                setattr(cfg, key, cp.getboolean("general", key, fallback=getattr(cfg, key)))
            except ValueError:
                pass
        try:
            cfg.copy_timeout_ms = max(50, min(5000, cp.getint("general", "copy_timeout_ms",
                                                              fallback=cfg.copy_timeout_ms)))
        except ValueError:
            pass
        return cfg

    def save(self):
        values = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in asdict(self).items()}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(_TEMPLATE.format(**values))


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
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass
