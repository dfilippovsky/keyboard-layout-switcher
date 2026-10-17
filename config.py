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
"""


@dataclass
class Config:
    hotkey: str = "Pause"
    enabled: bool = True
    switch_layout: bool = True
    reselect: bool = True
    copy_timeout_ms: int = 250

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
