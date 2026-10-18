"""Шаблон плагіна. Файли, що починаються з «_», не завантажуються: скопіюйте цей файл
під новим ім'ям (латиницею, напр. my_tools.py), і після «Перечитати config.ini і
плагіни» в меню трею його дії з'являться в меню «Дії» і в налаштуваннях.

Плагін — звичайний Python-модуль із функцією register(api). Доступна стандартна
бібліотека Python (у зібраному exe — та її частина, що в нього потрапила).

api.text_action(id, title, transform, hotkey="", menu=True, description="", color=None)
    Дія над виділеним текстом, а якщо виділення немає — над словом перед курсором
    (як вбудовані «Регістр» і «Транслітерація»): transform(str) -> str.

api.action(id, title, func, hotkey="", menu=True, description="", color=None)
    Довільна дія: func(ctx), де
      ctx.window            — HWND вікна, для якого виконується дія;
      ctx.notify(text)      — сповіщення з трею;
      ctx.edit_text(fn)     — те саме, що text_action, але зсередини дії;
      ctx.type_text(text)   — надрукувати текст у позиції курсора.

id — малі латинські літери, цифри, «_» і «-». Повний ідентифікатор дії —
«<ім'я файлу>.<id>»; під ним гарячу клавішу можна перевизначити в секції [plugins]
config.ini (порожнє значення — вимкнути). hotkey — як у config.ini: «Ctrl+Alt+U»,
«Shift+F12» тощо. color — (r, g, b), яким блимне іконка в треї.

title (і текст для ctx.notify) — рядок або словник {"uk": ..., "en": ...}: показується
варіант мовою інтерфейсу (якщо його немає — англійський). api.language і ctx.language —
поточна мова інтерфейсу ("uk" або "en").

api.log — логер (пише в layout_switcher.log).
"""


def register(api):
    api.text_action("upper", {"uk": "ВЕЛИКІ ЛІТЕРИ", "en": "UPPER CASE"}, str.upper)
    api.action("hello", {"uk": "Привітання", "en": "Greeting"},
               lambda ctx: ctx.notify({"uk": "Привіт від плагіна!", "en": "Hello from a plugin!"}))
