"""Дії програми та плагіни.

Дія — те, що можна запустити гарячою клавішею, з меню трею (а згодом — з командної
палітри): вбудовані (розкладка, регістр, транслітерація) і дії з плагінів.

Плагін — файл plugins/*.py поруч із програмою (файли, що починаються з «_», не
завантажуються). У ньому має бути функція register(api):

    def register(api):
        api.text_action("upper", "ВЕЛИКІ ЛІТЕРИ", str.upper, hotkey="Ctrl+Alt+U")
        api.action("hello", {"uk": "Привітання", "en": "Greeting"},
                   lambda ctx: ctx.notify({"uk": "Привіт!", "en": "Hello!"}))

Назви й тексти можна давати рядком або словником {"uk": ..., "en": ...} — тоді
показується той, що відповідає мові інтерфейсу (api.language / ctx.language).

Ідентифікатор дії — «<файл>.<id>» (напр. «example.upper»); за ним гарячу клавішу можна
перевизначити в секції [plugins] config.ini.
"""
import dataclasses
import importlib.util
import logging
import os
import re
import sys
from typing import Callable, Optional, Union

import i18n
from i18n import tr

log = logging.getLogger("kls")

_ID_RE = re.compile(r"[a-z0-9_-]+$")
DEFAULT_COLOR = (0xF5, 0x9E, 0x0B)   # колір іконки в треї для дій плагінів — бурштиновий


@dataclasses.dataclass
class Action:
    key: str                          # «layout», «example.upper»
    title: Union[str, dict]           # назва в меню / палітрі: рядок або {"uk": ..., "en": ...}
    run: Callable                     # run(fg) — виконати для вікна fg
    hotkey: str = ""                  # комбінація за замовчуванням (порожньо — немає)
    menu: bool = True                 # показувати в меню трею «Дії»
    color: tuple = DEFAULT_COLOR      # чим блимає іконка в треї
    description: str = ""
    plugin: Optional[str] = None      # ім'я файлу плагіна; None — вбудована дія
    num: int = 0                      # номер (id гарячої клавіші й пункту меню), задає App

    @property
    def label(self):
        """Назва поточною мовою інтерфейсу."""
        return i18n.pick(self.title)


class Context:
    """Що отримує дія плагіна, зареєстрована через api.action()."""

    def __init__(self, app, fg):
        self._app = app
        self.window = fg              # HWND вікна, для якого виконується дія

    @property
    def language(self):
        """Мова інтерфейсу: "uk" або "en"."""
        return i18n.language()

    def notify(self, text, title=None):
        """Сповіщення з трею; text і title — рядок або {"uk": ..., "en": ...}."""
        self._app.notify(i18n.pick(text), title=i18n.pick(title))

    def edit_text(self, transform):
        """Замінити виділений текст (або останнє слово перед курсором) на transform(текст),
        як це роблять вбудовані дії. True — текст оброблено."""
        return self._app.edit_text(transform)

    def type_text(self, text):
        """Надрукувати текст у позиції курсора."""
        self._app.type_text(text)


class PluginAPI:
    """Об'єкт, який отримує register(api) у плагіні."""

    def __init__(self, registry, plugin, app):
        self._registry = registry
        self._plugin = plugin
        self._app = app
        self.log = logging.getLogger("kls.plugin." + plugin)

    @property
    def language(self):
        """Мова інтерфейсу: "uk" або "en". Плагіни перечитуються разом із config.ini,
        але назви краще давати словником — вони змінюються одразу зі зміною мови."""
        return i18n.language()

    def text_action(self, id, title, transform, hotkey="", menu=True, description="", color=None):
        """Дія над виділеним текстом (або словом перед курсором): transform(str) -> str."""
        if not callable(transform):
            raise TypeError(tr("plugin.transform"))
        return self._add(id, title, lambda fg: self._app.edit_text(transform),
                         hotkey, menu, description, color)

    def action(self, id, title, func, hotkey="", menu=True, description="", color=None):
        """Довільна дія: func(ctx), де ctx — Context (вікно, сповіщення, робота з текстом)."""
        if not callable(func):
            raise TypeError(tr("plugin.func"))
        return self._add(id, title, lambda fg: func(Context(self._app, fg)),
                         hotkey, menu, description, color)

    def _add(self, id, title, run, hotkey, menu, description, color):
        if not isinstance(id, str) or not _ID_RE.match(id):
            raise ValueError(tr("plugin.bad_id", id))
        if isinstance(title, dict):
            title = {str(lang): str(text) for lang, text in title.items() if text}
        elif title:
            title = str(title)
        if not title:
            raise ValueError(tr("plugin.no_title", id))
        action = Action("%s.%s" % (self._plugin, id), title, run, hotkey or "", bool(menu),
                        _check_color(id, color), description, self._plugin)
        self._registry.add(action)
        return action


def _check_color(id, color):
    """(r, g, b) з цілих 0–255; None — колір за замовчуванням. Перевіряємо одразу при
    реєстрації, щоб помилка лишилася помилкою плагіна, а не впала при малюванні іконки."""
    if color is None:
        return DEFAULT_COLOR
    try:
        rgb = tuple(color)
    except TypeError:
        rgb = ()
    if len(rgb) != 3 or not all(type(c) is int and 0 <= c <= 255 for c in rgb):
        raise ValueError(tr("plugin.bad_color", id, color))
    return rgb


class Registry:
    def __init__(self):
        self.actions = []             # у порядку реєстрації

    def add(self, action):
        if self.get(action.key):
            raise ValueError(tr("plugin.duplicate", action.key))
        self.actions.append(action)

    def get(self, key):
        return next((a for a in self.actions if a.key == key), None)

    def plugin_actions(self):
        return [a for a in self.actions if a.plugin]


def plugins_dir(base):
    return os.path.join(base, "plugins")


def load_plugins(registry, directory, app):
    """Завантажити plugins/*.py. Повертає список (файл, помилка) для тих, що не вдалися;
    дії плагіна, що впав посеред register(), не реєструються."""
    failed = []
    if not os.path.isdir(directory):
        return failed
    for name in sorted(os.listdir(directory)):
        stem, ext = os.path.splitext(name)
        if ext.lower() != ".py" or name.startswith("_"):
            continue
        plugin = stem.lower()
        try:
            if not _ID_RE.match(plugin):
                raise ValueError(tr("plugin.bad_file"))
            spec = importlib.util.spec_from_file_location("kls_plugin_" + plugin.replace("-", "_"),
                                                          os.path.join(directory, name))
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise ValueError(tr("plugin.no_register"))
            staged = Registry()
            register(PluginAPI(staged, plugin, app))
            for action in staged.actions:
                registry.add(action)
            log.info("plugin %s: %d action(s)", plugin, len(staged.actions))
        except Exception as e:
            log.exception("plugin %s failed", name)
            failed.append((name, "%s: %s" % (type(e).__name__, e)))
    return failed
