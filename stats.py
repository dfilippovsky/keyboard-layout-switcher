"""Статистика: скільки разів виправлено розкладку і скільки часу це приблизно зекономило.

Зберігається в stats.json поруч із програмою — лише лічильники, без жодного тексту.
Запис на диск — не на кожне виправлення, а з таймером (save_if_dirty) і при виході.

Оцінка часу. Без програми слово, набране не в тій розкладці, треба стерти й набрати
заново (≈ KEY_SECONDS на символ на обидва кроки, ~200 натискань за хвилину), а ще —
перемкнути розкладку. Автовиправлення до того ж економить час, поки помилку помічаєш.
"""
import datetime
import json
import logging
import os

import config

log = logging.getLogger("kls")

STATS_PATH = os.path.join(config.app_dir(), "stats.json")
KEY_SECONDS = 0.3      # стерти й передрукувати один символ
AUTO_SECONDS = 2.0     # помітити помилку + перемкнути розкладку
MANUAL_SECONDS = 1.0   # перемкнути розкладку (помилку користувач уже помітив сам)
_FIELDS = ("auto", "manual", "undone", "seconds")


def auto_seconds(chars):
    return AUTO_SECONDS + chars * KEY_SECONDS


def manual_seconds(chars):
    return MANUAL_SECONDS + chars * KEY_SECONDS


def _empty():
    return dict.fromkeys(_FIELDS, 0)


def _counters(raw):
    """Лічильники з JSON; некоректні значення — нулі."""
    out = _empty()
    if isinstance(raw, dict):
        for key in _FIELDS:
            value = raw.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                out[key] = value
    return out


class Stats:
    def __init__(self, path=STATS_PATH, today=datetime.date.today):
        self.path = path
        self._today = today
        self._reset()
        self._load()

    def _reset(self):
        self.since = self._today().isoformat()
        self.total = _empty()
        self.day = self.since
        self.today = _empty()
        self.dirty = False
        self.on_disk = False   # файл прочитано або записано — якщо його не стане, скинути

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.exception("cannot read %s", self.path)
            return
        self.on_disk = True
        if not isinstance(data, dict):
            return
        if isinstance(data.get("since"), str):
            self.since = data["since"]
        self.total = _counters(data.get("total"))
        today = data.get("today")
        if isinstance(today, dict) and today.get("date") == self.day:
            self.today = _counters(today)

    def _roll(self):
        """Файл видалили (скидання статистики, зокрема поки програма працює) — усе
        з нуля; новий день — з нуля лічильники «сьогодні»."""
        if self.on_disk and not os.path.exists(self.path):
            log.info("%s was deleted — statistics reset", self.path)
            self._reset()
        day = self._today().isoformat()
        if day != self.day:
            self.day, self.today = day, _empty()

    def _add(self, key, count, seconds):
        self._roll()
        for bucket in (self.total, self.today):
            bucket[key] += count
            bucket["seconds"] = max(0, bucket["seconds"] + seconds)
        self.dirty = True

    def auto(self, chars):
        """Автовиправлення під час набору (chars — довжина виправленого)."""
        self._add("auto", 1, auto_seconds(chars))

    def undo(self, chars):
        """Автовиправлення скасовано гарячою клавішею — воно не рахується й часу не економить."""
        self._add("auto", -1, -auto_seconds(chars))
        for bucket in (self.total, self.today):
            bucket["auto"] = max(0, bucket["auto"])
            bucket["undone"] += 1

    def manual(self, chars):
        """Конвертація гарячою клавішею (або з меню)."""
        self._add("manual", 1, manual_seconds(chars))

    def summary(self):
        """(загалом, сьогодні, з якої дати) — лічильники для показу."""
        self._roll()
        return dict(self.total), dict(self.today), self.since

    def save_if_dirty(self):
        self._roll()  # видалений файл не відновлюємо зі старими значеннями
        if not self.dirty:
            return
        rounded = lambda c: dict(c, seconds=round(c["seconds"], 1))
        data = {"since": self.since, "total": rounded(self.total),
                "today": dict(rounded(self.today), date=self.day)}
        try:
            config.write_atomic(self.path, json.dumps(data, indent=1) + "\n")
            self.dirty = False
            self.on_disk = True
        except OSError:
            log.exception("cannot save %s", self.path)
