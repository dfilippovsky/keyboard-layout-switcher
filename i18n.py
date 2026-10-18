"""Мова інтерфейсу: українська або англійська.

tr("ключ", *args) — рядок поточною мовою (з підстановкою % args). Мову задає
set_language("auto" | "uk" | "en"); «auto» — як інтерфейс Windows (українська, якщо
Windows українською, інакше англійська). pick() вибирає з {"uk": ..., "en": ...} —
так плагіни задають назви дій кількома мовами.
"""
import ctypes

LANGUAGES = ("uk", "en")
_LANG_UKRAINIAN = 0x22  # PRIMARYLANGID для української

_STRINGS = {
    "uk": {
        # дії
        "action.layout": "Розкладка",
        "action.case": "Регістр",
        "action.translit": "Транслітерація",
        # трей
        "tray.disabled": " (вимкнено)",
        "tray.busy": " (клавіша зайнята)",
        "menu.actions": "Дії",
        "menu.enabled": "Увімкнено",
        "menu.autocorrect": "Автовиправлення розкладки під час набору",
        "menu.eyes": "Нагадування 20-20-20 для очей",
        "menu.work": "Нагадування про перерву в роботі",
        "menu.settings": "Налаштування…",
        "menu.open_ini": "Відкрити config.ini",
        "menu.reload": "Перечитати config.ini і плагіни",
        "menu.plugins": "Відкрити папку плагінів",
        "menu.exit": "Вихід",
        # сповіщення й помилки
        "warn.hotkeys": "Не вдалося зареєструвати: %s. Змініть комбінації в налаштуваннях.",
        "warn.plugins": "Не завантажилися плагіни: %s (подробиці в layout_switcher.log).",
        "err.autostart": "Не вдалося змінити автозапуск: %s",
        "err.save": "Не вдалося зберегти %s: %s",
        "err.hotkey": "Некоректна гаряча клавіша «%s»: %s",
        "err.hotkey_twice": "Комбінацію «%s» призначено двом діям.",
        "err.hotkey_taken": ("Комбінацію «%s» не вдалося зареєструвати — можливо, її вже "
                             "використовує інша програма або система."),
        "err.action": "Помилка в дії «%s» (плагін %s): %s",
        "already_running": "Keyboard Layout Switcher вже запущено (дивіться трей).",
        "eye.title": "Перерва для очей",
        "eye.text": "Подивіться 20 секунд на щось далеко (≈6 м) - очі відпочинуть.",
        "work.title": "Час на перерву",
        "work.text": "Ти вже %s без перерви. Встань, пройдися, розімнися кілька хвилин.",
        # розбір гарячих клавіш
        "hotkey.empty_part": "порожня частина в «%s»",
        "hotkey.bad_modifier": "невідомий модифікатор «%s»",
        "hotkey.bad_key": "невідома клавіша «%s»",
        # плагіни
        "plugin.transform": "transform має бути функцією str -> str",
        "plugin.func": "func має бути функцією func(ctx)",
        "plugin.bad_id": "id дії «%s»: лише малі латинські літери, цифри, _ і -",
        "plugin.no_title": "дія «%s» без назви",
        "plugin.bad_color": "дія «%s»: color має бути (r, g, b) з цілих 0–255, а не %r",
        "plugin.duplicate": "дію «%s» вже зареєстровано",
        "plugin.bad_file": "ім'я файлу: лише латинські літери, цифри, _ і -",
        "plugin.no_register": "немає функції register(api)",
        # файл винятків автовиправлення
        "exceptions.header": ("# Слова, які автовиправлення розкладки не чіпає (по одному в рядку).\n"
                              "# Додаються самі, коли виправлення скасовують гарячою клавішею.\n"),
        # вікно налаштувань
        "ui.hotkeys": "Гарячі клавіші",
        "ui.hk_layout": "Розкладка:",
        "ui.hk_case": "Регістр (aA, camelCase…):",
        "ui.hk_translit": "Транслітерація (Привіт → Pryvit):",
        "ui.hk_hint": "Клацніть у поле й натисніть комбінацію; Backspace — вимкнути\n"
                      "(для регістру й транслітерації)",
        "ui.plugins": "Плагіни",
        "ui.plugins_hint": "Backspace — вимкнути",
        "ui.enabled": "Увімкнено (гарячі клавіші й автовиправлення)",
        "ui.switch": "Перемикати розкладку після конвертації",
        "ui.reselect": "Виділяти перетворений текст (повторне натискання — далі по колу)",
        "ui.autocorrect": "Автовиправлення розкладки під час набору (ghbdsn → привіт)",
        "ui.autostart": "Запускати разом з Windows",
        "ui.exclude": "Не виправляти в програмах:",
        "ui.exclude_hint": "Імена exe через кому, напр. WindowsTerminal.exe, code.exe.\n"
                           "Скасувати виправлення — одразу натиснути гарячу клавішу розкладки.",
        "ui.timeout": "Очікування Ctrl+C, мс:",
        "ui.eyes": "Нагадувати дати відпочити очам (20-20-20) кожні",
        "ui.min": "хв",
        "ui.popup": "Сповіщення закривається через",
        "ui.popup_unit": "с (0 — як вирішить Windows)",
        "ui.eyes_hint": "Не з'являється в повноекранному режимі, «Не турбувати» і під час дзвінків",
        "ui.work": "Нагадувати про перерву після",
        "ui.work_unit": "хв роботи без перерви",
        "ui.work_hint": "Перерва — 5 хв без клавіатури й миші або сон; далі нагадує кожні 30 хв",
        "ui.language": "Мова інтерфейсу:",
        "ui.language_auto": "Як у Windows",
        "ui.layouts": "Розкладки в системі (по колу): ",
        "ui.error": "Помилка",
        "ui.not_numbers": "Затримка, інтервали й час показу мають бути числами.",
        "ui.save": "Зберегти",
        "ui.cancel": "Скасувати",
    },
    "en": {
        "action.layout": "Layout",
        "action.case": "Case",
        "action.translit": "Transliteration",
        "tray.disabled": " (disabled)",
        "tray.busy": " (hotkey taken)",
        "menu.actions": "Actions",
        "menu.enabled": "Enabled",
        "menu.autocorrect": "Auto-correct layout while typing",
        "menu.eyes": "20-20-20 eye breaks",
        "menu.work": "Work break reminders",
        "menu.settings": "Settings…",
        "menu.open_ini": "Open config.ini",
        "menu.reload": "Reload config.ini and plugins",
        "menu.plugins": "Open plugins folder",
        "menu.exit": "Exit",
        "warn.hotkeys": "Could not register: %s. Change the combinations in the settings.",
        "warn.plugins": "Plugins failed to load: %s (details in layout_switcher.log).",
        "err.autostart": "Could not change autostart: %s",
        "err.save": "Could not save %s: %s",
        "err.hotkey": "Invalid hotkey “%s”: %s",
        "err.hotkey_twice": "The combination “%s” is assigned to two actions.",
        "err.hotkey_taken": ("Could not register the combination “%s” — another program or "
                             "the system may already be using it."),
        "err.action": "Error in action “%s” (plugin %s): %s",
        "already_running": "Keyboard Layout Switcher is already running (see the tray).",
        "eye.title": "Eye break",
        "eye.text": "Look at something far away (≈6 m) for 20 seconds - your eyes will rest.",
        "work.title": "Time for a break",
        "work.text": "You've been working for %s without a break. Stand up, walk around, stretch "
                     "for a few minutes.",
        "hotkey.empty_part": "empty part in “%s”",
        "hotkey.bad_modifier": "unknown modifier “%s”",
        "hotkey.bad_key": "unknown key “%s”",
        "plugin.transform": "transform must be a function str -> str",
        "plugin.func": "func must be a function func(ctx)",
        "plugin.bad_id": "action id “%s”: only lowercase Latin letters, digits, _ and -",
        "plugin.no_title": "action “%s” has no title",
        "plugin.bad_color": "action “%s”: color must be (r, g, b) of integers 0–255, not %r",
        "plugin.duplicate": "action “%s” is already registered",
        "plugin.bad_file": "file name: only Latin letters, digits, _ and -",
        "plugin.no_register": "no register(api) function",
        "exceptions.header": ("# Words that layout auto-correct leaves alone (one per line).\n"
                              "# Added automatically when a correction is undone with the hotkey.\n"),
        "ui.hotkeys": "Hotkeys",
        "ui.hk_layout": "Layout:",
        "ui.hk_case": "Case (aA, camelCase…):",
        "ui.hk_translit": "Transliteration (Привіт → Pryvit):",
        "ui.hk_hint": "Click a field and press a combination; Backspace turns it off\n"
                      "(for case and transliteration)",
        "ui.plugins": "Plugins",
        "ui.plugins_hint": "Backspace turns it off",
        "ui.enabled": "Enabled (hotkeys and auto-correct)",
        "ui.switch": "Switch the layout after converting",
        "ui.reselect": "Select the converted text (press again for the next option)",
        "ui.autocorrect": "Auto-correct layout while typing (ghbdsn → привіт)",
        "ui.autostart": "Start with Windows",
        "ui.exclude": "Don't correct in programs:",
        "ui.exclude_hint": "Exe names separated by commas, e.g. WindowsTerminal.exe, code.exe.\n"
                           "To undo a correction, press the layout hotkey right away.",
        "ui.timeout": "Ctrl+C timeout, ms:",
        "ui.eyes": "Remind me to rest my eyes (20-20-20) every",
        "ui.min": "min",
        "ui.popup": "Notification closes after",
        "ui.popup_unit": "s (0 — let Windows decide)",
        "ui.eyes_hint": "Not shown in fullscreen, Do Not Disturb or during calls",
        "ui.work": "Remind me to take a break after",
        "ui.work_unit": "min of work without a break",
        "ui.work_hint": "A break is 5 min without keyboard and mouse, or sleep; then every 30 min",
        "ui.language": "Interface language:",
        "ui.language_auto": "Same as Windows",
        "ui.layouts": "Layouts in the system (in order): ",
        "ui.error": "Error",
        "ui.not_numbers": "The timeout, intervals and display time must be numbers.",
        "ui.save": "Save",
        "ui.cancel": "Cancel",
    },
}

_current = "uk"


def system_language():
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return "en"
    return "uk" if langid & 0x3FF == _LANG_UKRAINIAN else "en"


def resolve(setting):
    """'auto' | 'uk' | 'en' -> 'uk' | 'en'."""
    return setting if setting in LANGUAGES else system_language()


def set_language(setting):
    global _current
    _current = resolve(setting)


def language():
    return _current


def tr(key, *args):
    text = _STRINGS[_current].get(key) or _STRINGS["uk"][key]
    return text % args if args else text


def translations(key):
    """{"uk": ..., "en": ...} для ключа — назва, що змінюється разом із мовою."""
    return {lang: _STRINGS[lang][key] for lang in LANGUAGES}


def pick(value):
    """Рядок поточною мовою з {"uk": ..., "en": ...} (або сам рядок)."""
    if isinstance(value, dict):
        for lang in (_current, "en", "uk"):
            if value.get(lang):
                return str(value[lang])
        return str(next(iter(value.values()), ""))
    return value


def _plural_uk(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def format_duration(seconds):
    """«2 години 30 хвилин» / «2 hours 30 minutes» (українською — у знахідному відмінку)."""
    hours, minutes = divmod(int(seconds // 60), 60)
    if _current == "uk":
        h = "%d %s" % (hours, _plural_uk(hours, "годину", "години", "годин"))
        m = "%d %s" % (minutes, _plural_uk(minutes, "хвилину", "хвилини", "хвилин"))
    else:
        h = "%d hour%s" % (hours, "" if hours == 1 else "s")
        m = "%d minute%s" % (minutes, "" if minutes == 1 else "s")
    return " ".join(([h] if hours else []) + ([m] if minutes or not hours else []))
