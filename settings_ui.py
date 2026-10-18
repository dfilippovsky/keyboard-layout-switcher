"""Вікно налаштувань (tkinter завантажується лише при відкритті)."""
import base64
import logging
import tkinter as tk
from tkinter import messagebox, ttk

import config
import hotkey as hk
import icon
import layouts

log = logging.getLogger(__name__)

_MODIFIER_VKS = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
_CLEAR_VKS = {0x08, 0x2E}  # Backspace/Delete без модифікаторів — вимкнути комбінацію

_HOTKEY_ROWS = (
    ("hotkey", "Розкладка:", False),
    ("case_hotkey", "Регістр (aA, camelCase…):", True),
    ("translit_hotkey", "Транслітерація (Привіт → Pryvit):", True),
)


def _hotkey_entry(frm, row, label, initial, allow_clear):
    """Поле, що «ловить» комбінацію. Повертає функцію, яка дає вибране значення."""
    var = tk.StringVar(value=initial)
    last_valid = [initial]
    ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
    entry = ttk.Entry(frm, textvariable=var, width=26, justify="center")
    entry.grid(row=row, column=1, sticky="ew", pady=2)

    def on_key(event):
        vk = hk.normalize_vk(event.keycode)  # у Tk на Windows це віртуальний код клавіші
        mods = hk.current_mods()
        if vk in _MODIFIER_VKS:
            var.set(hk.format(mods, 0) + "…")
        elif allow_clear and vk in _CLEAR_VKS and not mods:
            var.set("")
            last_valid[0] = ""
        else:
            var.set(hk.format(mods, vk))
            last_valid[0] = var.get()
        return "break"

    def on_key_release(event):
        if event.keycode in _MODIFIER_VKS and var.get().endswith("…") and not hk.current_mods():
            var.set(last_valid[0])
        return "break"

    entry.bind("<KeyPress>", on_key)
    entry.bind("<KeyRelease>", on_key_release)
    entry.bind("<FocusOut>", lambda e: var.set(last_valid[0]))
    return lambda: last_valid[0]


def run(app):
    """Показати вікно й крутити його цикл, доки його не закриють."""
    cfg = app.cfg
    root = tk.Tk()
    app.settings_root = root
    root.report_callback_exception = lambda *exc: log.error("UI error", exc_info=exc)
    root.title("Keyboard Layout Switcher")
    root.resizable(False, False)
    images = [tk.PhotoImage(data=base64.b64encode(icon.png_bytes(s, icon.APP_ICON_COLOR)))
              for s in (32, 16)]
    root.iconphoto(True, *images)

    switch_var = tk.BooleanVar(value=cfg.switch_layout)
    reselect_var = tk.BooleanVar(value=cfg.reselect)
    autocorrect_var = tk.BooleanVar(value=cfg.autocorrect)
    exclude_var = tk.StringVar(value=cfg.autocorrect_exclude)
    enabled_var = tk.BooleanVar(value=cfg.enabled)
    autostart_var = tk.BooleanVar(value=config.autostart_enabled())
    timeout_var = tk.StringVar(value=str(cfg.copy_timeout_ms))
    eyes_var = tk.BooleanVar(value=cfg.eye_breaks)
    eye_minutes_var = tk.StringVar(value=str(cfg.eye_break_minutes))
    eye_popup_var = tk.StringVar(value=str(cfg.eye_break_popup_seconds))
    work_var = tk.BooleanVar(value=cfg.work_breaks)
    work_minutes_var = tk.StringVar(value=str(cfg.work_break_minutes))

    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="Гарячі клавіші", font=("Segoe UI", 9, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
    hotkeys = {field: _hotkey_entry(frm, i, label, getattr(cfg, field), allow_clear)
               for i, (field, label, allow_clear) in enumerate(_HOTKEY_ROWS, start=1)}
    row = 1 + len(_HOTKEY_ROWS)
    ttk.Label(frm, text="Клацніть у поле й натисніть комбінацію; Backspace — вимкнути\n"
                        "(для регістру й транслітерації)",
              foreground="gray").grid(row=row, column=1, sticky="w", pady=(2, 10))

    # Дії з плагінів (plugins\*.py): комбінація з [plugins] або та, що задав плагін
    plugin_actions = [a for a in app.actions.values() if a.plugin]
    plugin_hotkeys = []  # (дія, функція, що дає вибране значення)
    if plugin_actions:
        row += 1
        ttk.Label(frm, text="Плагіни", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for action in plugin_actions:
            row += 1
            plugin_hotkeys.append((action, _hotkey_entry(frm, row, action.title + ":", app.hotkey_text(action), True)))
        row += 1
        ttk.Label(frm, text="Backspace — вимкнути", foreground="gray").grid(
            row=row, column=1, sticky="w", pady=(2, 10))

    checks = (
        (enabled_var, "Увімкнено (гарячі клавіші й автовиправлення)"),
        (switch_var, "Перемикати розкладку після конвертації"),
        (reselect_var, "Виділяти перетворений текст (повторне натискання — далі по колу)"),
        (autocorrect_var, "Автовиправлення розкладки під час набору (ghbdsn → привіт)"),
        (autostart_var, "Запускати разом з Windows"),
    )
    for i, (var, text) in enumerate(checks, start=row + 1):
        ttk.Checkbutton(frm, text=text, variable=var).grid(row=i, column=0, columnspan=2, sticky="w", pady=2)

    row += 1 + len(checks)
    ttk.Label(frm, text="Не виправляти в програмах:").grid(row=row, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(frm, textvariable=exclude_var, width=26).grid(row=row, column=1, sticky="ew", pady=(6, 0))
    ttk.Label(frm, text="Імена exe через кому, напр. WindowsTerminal.exe, code.exe.\n"
                        "Скасувати виправлення — одразу натиснути гарячу клавішу розкладки.",
              foreground="gray").grid(row=row + 1, column=1, sticky="w", pady=(2, 0))

    row += 2
    ttk.Label(frm, text="Очікування Ctrl+C, мс:").grid(row=row, column=0, sticky="w", pady=(10, 0))
    ttk.Spinbox(frm, from_=50, to=5000, increment=50, width=8,
                textvariable=timeout_var).grid(row=row, column=1, sticky="w", pady=(10, 0))

    row += 1
    eyes = ttk.Frame(frm)
    eyes.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ttk.Checkbutton(eyes, text="Нагадувати дати відпочити очам (20-20-20) кожні",
                    variable=eyes_var).pack(side="left")
    ttk.Spinbox(eyes, from_=1, to=240, increment=5, width=5,
                textvariable=eye_minutes_var).pack(side="left", padx=4)
    ttk.Label(eyes, text="хв").pack(side="left")
    popup = ttk.Frame(frm)
    popup.grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(4, 0), padx=(20, 0))
    ttk.Label(popup, text="Сповіщення закривається через").pack(side="left")
    ttk.Spinbox(popup, from_=0, to=120, increment=1, width=5,
                textvariable=eye_popup_var).pack(side="left", padx=4)
    ttk.Label(popup, text="с (0 — як вирішить Windows)").pack(side="left")
    ttk.Label(frm, text="Не з'являється в повноекранному режимі, «Не турбувати» і під час дзвінків",
              foreground="gray").grid(row=row + 2, column=0, columnspan=2, sticky="w", pady=(2, 0))

    row += 3
    work = ttk.Frame(frm)
    work.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
    ttk.Checkbutton(work, text="Нагадувати про перерву після",
                    variable=work_var).pack(side="left")
    ttk.Spinbox(work, from_=15, to=480, increment=15, width=5,
                textvariable=work_minutes_var).pack(side="left", padx=4)
    ttk.Label(work, text="хв роботи без перерви").pack(side="left")
    ttk.Label(frm, text="Перерва — 5 хв без клавіатури й миші або сон; далі нагадує кожні 30 хв",
              foreground="gray").grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(2, 0))

    row += 2
    names = ", ".join(layouts.name(h) for h in layouts.installed())
    ttk.Label(frm, text="Розкладки в системі (по колу): " + names,
              foreground="gray").grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def save():
        try:
            timeout = max(50, min(5000, int(timeout_var.get())))
            eye_minutes = max(1, min(240, int(eye_minutes_var.get())))
            eye_popup = max(0, min(120, int(eye_popup_var.get())))
            work_minutes = max(15, min(480, int(work_minutes_var.get())))
        except ValueError:
            messagebox.showerror("Помилка", "Затримка, інтервали й час показу мають бути числами.", parent=root)
            return
        values = {field: get() for field, get in hotkeys.items()}
        # У config лишаються тільки відмінності від того, що задав плагін (і записи
        # плагінів, яких зараз немає), тож новий хоткей у плагіні підхопиться сам
        overrides = dict(cfg.plugin_hotkeys)
        for action, get in plugin_hotkeys:
            if get() == action.hotkey:
                overrides.pop(action.key, None)
            else:
                overrides[action.key] = get()
        values["plugin_hotkeys"] = overrides
        values.update(enabled=enabled_var.get(), switch_layout=switch_var.get(),
                      reselect=reselect_var.get(), copy_timeout_ms=timeout,
                      autocorrect=autocorrect_var.get(),
                      autocorrect_exclude=", ".join(n.strip() for n in exclude_var.get().split(",") if n.strip()),
                      eye_breaks=eyes_var.get(), eye_break_minutes=eye_minutes,
                      eye_break_popup_seconds=eye_popup, work_breaks=work_var.get(),
                      work_break_minutes=work_minutes)
        error = app.apply_settings(values, autostart_var.get())
        if error:
            messagebox.showerror("Помилка", error, parent=root)
        else:
            root.destroy()

    buttons = ttk.Frame(frm)
    buttons.grid(row=row + 1, column=0, columnspan=2, sticky="e", pady=(16, 0))
    ttk.Button(buttons, text="Зберегти", command=save).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Скасувати", command=root.destroy).pack(side="left")
    root.bind("<Escape>", lambda e: root.destroy())

    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
    root.geometry("+%d+%d" % (x, y))
    root.attributes("-topmost", True)
    root.after(300, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()
