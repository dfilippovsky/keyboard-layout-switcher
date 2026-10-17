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

    hotkey_var = tk.StringVar(value=cfg.hotkey)
    last_valid = [cfg.hotkey]
    switch_var = tk.BooleanVar(value=cfg.switch_layout)
    reselect_var = tk.BooleanVar(value=cfg.reselect)
    enabled_var = tk.BooleanVar(value=cfg.enabled)
    autostart_var = tk.BooleanVar(value=config.autostart_enabled())
    timeout_var = tk.StringVar(value=str(cfg.copy_timeout_ms))

    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="Гаряча клавіша:").grid(row=0, column=0, sticky="w", padx=(0, 10))
    entry = ttk.Entry(frm, textvariable=hotkey_var, width=26, justify="center")
    entry.grid(row=0, column=1, sticky="ew")
    ttk.Label(frm, text="Клацніть у поле й натисніть потрібну комбінацію",
              foreground="gray").grid(row=1, column=1, sticky="w", pady=(2, 10))

    def on_key(event):
        vk = event.keycode  # у Tk на Windows це віртуальний код клавіші
        mods = hk.current_mods()
        if vk in _MODIFIER_VKS:
            hotkey_var.set(hk.format(mods, 0) + "…")
        else:
            hotkey_var.set(hk.format(mods, vk))
            last_valid[0] = hotkey_var.get()
        return "break"

    def on_key_release(event):
        if event.keycode in _MODIFIER_VKS and hotkey_var.get().endswith("…") and not hk.current_mods():
            hotkey_var.set(last_valid[0])
        return "break"

    entry.bind("<KeyPress>", on_key)
    entry.bind("<KeyRelease>", on_key_release)
    entry.bind("<FocusOut>", lambda e: hotkey_var.set(last_valid[0]))

    checks = (
        (enabled_var, "Увімкнено (реагувати на гарячу клавішу)"),
        (switch_var, "Перемикати розкладку після конвертації"),
        (reselect_var, "Виділяти конвертований текст (повторне натискання — наступна розкладка)"),
        (autostart_var, "Запускати разом з Windows"),
    )
    for i, (var, text) in enumerate(checks, start=2):
        ttk.Checkbutton(frm, text=text, variable=var).grid(row=i, column=0, columnspan=2, sticky="w", pady=2)

    row = 2 + len(checks)
    ttk.Label(frm, text="Очікування Ctrl+C, мс:").grid(row=row, column=0, sticky="w", pady=(10, 0))
    ttk.Spinbox(frm, from_=50, to=5000, increment=50, width=8,
                textvariable=timeout_var).grid(row=row, column=1, sticky="w", pady=(10, 0))

    names = ", ".join(layouts.name(h) for h in layouts.installed())
    ttk.Label(frm, text="Розкладки в системі (по колу): " + names,
              foreground="gray").grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def save():
        try:
            timeout = max(50, min(5000, int(timeout_var.get())))
        except ValueError:
            messagebox.showerror("Помилка", "Затримка має бути числом.", parent=root)
            return
        values = dict(hotkey=last_valid[0], enabled=enabled_var.get(), switch_layout=switch_var.get(),
                      reselect=reselect_var.get(), copy_timeout_ms=timeout)
        error = app.apply_settings(values, autostart_var.get())
        if error:
            messagebox.showerror("Помилка", error, parent=root)
        else:
            root.destroy()

    buttons = ttk.Frame(frm)
    buttons.grid(row=row + 2, column=0, columnspan=2, sticky="e", pady=(16, 0))
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
