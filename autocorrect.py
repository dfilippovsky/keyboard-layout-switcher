"""Автовиправлення розкладки на льоту (як Punto Switcher).

Програма стежить за натисканнями через Raw Input (без хуків) і запам'ятовує клавіші
поточного слова. Після пробілу порівнює, як слово виглядає в поточній розкладці і в
інших: якщо набране — не слово, а в іншій розкладці виходить слово (зі словника або
за статистикою трибуквених сполучень), слово передруковується, а розкладка
перемикається. Набраний текст нікуди не записується і не зберігається.

Слова зі списку «завжди у своїй розкладці» (позивні, коди: «N01», «EVAK1101»)
виправляються ще до пробілу — щойно зрозуміло, що набирається саме таке слово.
"""
import bisect
import dataclasses
import gzip
import logging
import math
import os
import sys
import time

import layouts
from i18n import tr

log = logging.getLogger("kls")

_SCRIPTS = {"en": "latin", "uk": "cyrillic"}
_APOSTROPHES = "'ʼ’`"
_SMOOTHING = 0.05
SHORT_WORD = 2           # слова з такою кількістю літер — лише разом з наступним
MIN_TRIGRAM_LEN = 4      # коротші слова виправляються лише за словником
_SHORT_RANK = {1: 60, 2: 1500, 3: 4000}  # слова з 1–3 літер — лише досить часті
_MAX_SCORE = -2.6        # набране слово з кращою оцінкою схоже на справжнє — не чіпаємо
_MIN_GAIN = 1.6          # на скільки (лог-імовірність на триграму) варіант має бути кращим
_GOOD_SCORE = -3.0       # оцінка, вище якої варіант майже напевно справжнє слово


def data_dir():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "langdata")


class LanguageModel:
    def __init__(self, lang, lines):
        self.lang = lang
        self.script = _SCRIPTS.get(lang)
        self.rank = {}
        self.trigrams = {}
        self.contexts = {}
        alphabet = ""
        words = True
        for line in lines:
            line = line.rstrip("\n")
            if line.startswith("# alphabet "):
                alphabet = line[len("# alphabet "):]
            elif line.startswith("#"):
                continue
            elif not line:
                words = False
            elif words:
                self.rank.setdefault(line, len(self.rank) + 1)
            else:
                tri, count = line.split(" ")
                self.trigrams[tri] = int(count)
                self.contexts[tri[:2]] = self.contexts.get(tri[:2], 0) + int(count)
        self.alphabet = frozenset(alphabet)
        self._vocab = len(self.alphabet) + 1  # + кінець слова
        self._sorted = None

    @classmethod
    def load(cls, lang, directory=None):
        path = os.path.join(directory or data_dir(), lang + ".txt.gz")
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return cls(lang, f)

    def letters(self, word):
        """Слово без апострофів, якщо воно складається лише з літер мови, інакше None."""
        core = "".join(ch for ch in word if ch not in _APOSTROPHES)
        if not core or not set(core) <= self.alphabet:
            return None
        return core

    def word_rank(self, word):
        """Місце слова в частотному словнику (1 — найчастіше) або None.
        Короткі слова (1–3 літери) вважаються словами, лише якщо вони досить часті:
        у словнику з субтитрів є й окремі літери, абревіатури тощо."""
        core = self.letters(word)
        rank = self.rank.get(word) or self.rank.get(core or "")
        if rank and rank > _SHORT_RANK.get(len(core or word), math.inf):
            return None
        return rank

    def has_prefix(self, prefix):
        """Чи починається з prefix якесь слово словника."""
        if self._sorted is None:
            self._sorted = sorted(self.rank)
        return _has_prefix(self._sorted, prefix)

    def score(self, word):
        """Середня лог-імовірність триграм слова (вище — «більш схоже» на цю мову)."""
        core = self.letters(word)
        if core is None:
            return -math.inf
        padded = "^^" + core + "$"
        total = 0.0
        for i in range(len(padded) - 2):
            tri = padded[i:i + 3]
            p = (self.trigrams.get(tri, 0) + _SMOOTHING) / (self.contexts.get(tri[:2], 0) + _SMOOTHING * self._vocab)
            total += math.log(p)
        return total / (len(padded) - 2)


def _has_prefix(sorted_words, prefix):
    i = bisect.bisect_left(sorted_words, prefix)
    return i < len(sorted_words) and sorted_words[i].startswith(prefix)


_models = {}


def model(lang):
    """Модель мови або None, якщо даних для неї немає."""
    if lang not in _models:
        try:
            _models[lang] = LanguageModel.load(lang)
        except OSError:
            log.info("no language data for %r", lang)
            _models[lang] = None
    return _models[lang]


def word_bounds(typed, conv, part=str.isalpha):
    """(початок, кінець) слова: розділові знаки по краях, які не є літерами (part) в
    жодній з розкладок, до слова не належать («lj,ht?» → «добре,»: «?»/«,» — суфікс,
    а «,» всередині — це «б»)."""
    def letter(i):
        return part(typed[i]) or part(conv[i])
    start, end = 0, min(len(typed), len(conv))
    while start < end and not letter(start):
        start += 1
    while end > start and not letter(end - 1):
        end -= 1
    return start, end


def is_better(typed, typed_model, conv, conv_model, exceptions=(), short=False):
    """Чи варто замінити набране `typed` (мова typed_model) на `conv` (мова conv_model).
    Повертає (так/ні, «впевненість» — для вибору між кількома розкладками).

    Слова з 1–2 літер («b», «ne») надто неоднозначні, щоб виправляти їх самі по собі:
    вони виправляються лише за контекстом (short=True) — разом із наступним словом,
    яке виправилося на ту саму розкладку."""
    if len(typed) != len(conv):
        return False, 0
    start, end = word_bounds(typed, conv)
    if start == end:
        return False, 0
    low, target = typed[start:end].lower(), conv[start:end].lower()
    if low in exceptions or typed_model.word_rank(low):
        return False, 0  # набране — справжнє слово
    if typed_model.script == conv_model.script:
        return False, 0  # одне письмо (напр. en/de): за окремим словом не розрізнити надійно
    if conv_model.letters(target) is None:
        return False, 0  # в іншій розкладці всередині слова розділові знаки чи цифри
    if (len(target) <= SHORT_WORD) != short:
        return False, 0
    rank = conv_model.word_rank(target)
    if rank:
        return True, 10 - math.log(rank)
    if len(target) < MIN_TRIGRAM_LEN:
        return False, 0
    conv_score = conv_model.score(target)
    if typed_model.letters(low) is None:
        # Набране з розділовими знаками всередині («he[f.cz» → «рухаюся», але й «e.g.»):
        # порівнювати нема з чим, тож варіант має бути впевнено схожим на слово.
        return (True, conv_score - _GOOD_SCORE) if conv_score > _GOOD_SCORE else (False, 0)
    typed_score = typed_model.score(low)
    gain = conv_score - typed_score
    if typed_score < _MAX_SCORE and gain > _MIN_GAIN:
        return True, gain
    return False, 0


def load_words(path):
    """Слова з файлу (по одному в рядку, # — коментар), малими літерами."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            return {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}
    except OSError:
        return set()


def add_exception(path, word):
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(tr("exceptions.header"))
        f.write(word + "\n")


class ForcedWords:
    """Слова, які завжди набираються у «своїй» розкладці (позивні, коди, номери),
    з файлу по одному в рядку. Файл перечитується, щойно змінився."""

    _CHECK_EVERY = 1.0   # с — не частіше перевіряти, чи змінився файл

    def __init__(self, path):
        self.path = path
        self.words = frozenset()
        self._sorted = []
        self._mtime = None
        self._checked = None

    def refresh(self, force=False):
        now = time.monotonic()
        if not force and self._checked is not None and now - self._checked < self._CHECK_EVERY:
            return
        self._checked = now
        try:
            mtime = os.stat(self.path).st_mtime_ns
        except OSError:
            mtime = None
        if mtime != self._mtime:
            self._mtime = mtime
            self.words = frozenset(load_words(self.path)) if mtime is not None else frozenset()
            self._sorted = sorted(self.words)

    def ensure_file(self):
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(tr("forced.header"))

    def __bool__(self):
        return bool(self.words)

    def __contains__(self, word):
        return word in self.words

    def has_prefix(self, prefix):
        return _has_prefix(self._sorted, prefix)


def lang_of(hkl):
    return layouts.name(hkl).lower()


def render(keys, hkl):
    """Текст, який дають клавіші слова в розкладці hkl, або None, якщо якась клавіша
    в ній нічого не друкує."""
    chars = layouts.keymap(hkl).key_to_char
    out = []
    for vk, shift, altgr, caps in keys:
        if VK_NUMPAD0 <= vk <= VK_NUMPAD9:
            out.append(str(vk - VK_NUMPAD0))
            continue
        ch = chars.get((vk, layouts.state_index(shift, altgr)))
        if ch is None:
            return None
        out.append(ch.swapcase() if caps and ch.isalpha() else ch)
    return "".join(out)


@dataclasses.dataclass
class Correction:
    src: int              # розкладка, в якій набрано
    dst: int              # розкладка, на яку виправлено
    typed: str            # набраний текст (одне або кілька слів через пробіл)
    fixed: str            # виправлений текст
    word: str             # головне (останнє) набране слово без розділових знаків — для винятків
    tail: str = " "       # що надруковано після слова (до пробілу — нічого)


def forced(keys, cur, hkls, words, partial=False):
    """Клавіші слова в іншій розкладці дають слово зі списку words (ForcedWords) —
    Correction на цю розкладку, інакше None. partial — слово ще набирається: досить,
    щоб із набраного починалося слово зі списку, а в поточній мові — жодне слово
    словника («т0» → «N0»: так починається «N01»). Щоб не зачепити рідкісних слів,
    яких немає в словнику («тло» і «NK701»), до пробілу — лише коли набрано цифру
    або слово зі списку повністю."""
    if not words:
        return None
    typed = render(keys, cur)
    if typed is None:
        return None
    for hkl in _cycle_after(cur, hkls):
        conv = render(keys, hkl)
        if conv is None:
            continue
        start, end = word_bounds(typed, conv, str.isalnum)  # цифри — частина слова («N01»)
        low, target = typed[start:end].lower(), conv[start:end].lower()
        if not target or low == target or low in words:
            continue
        if partial:
            if not words.has_prefix(target) or words.has_prefix(low):
                continue
            if target not in words and not any(ch.isdigit() for ch in target):
                continue
            typed_model = model(lang_of(cur))
            if typed_model is None or typed_model.has_prefix(low):
                continue  # ще може вийти звичайне слово поточної мови — чекаємо далі
        elif target not in words:
            continue
        # Розділові знаки навколо слова лишаються як набрані («Т01,» → «N01,»);
        # word="" — скасування не додає слово до винятків: воно ж зі списку
        fixed = typed[:start] + conv[start:end] + typed[end:]
        return Correction(cur, hkl, typed, fixed, "", "" if partial else " ")
    return None


def choose(words, cur, hkls, exceptions=(), forced_words=None):
    """words — клавіші останнього слова й попередніх коротких (від давніших до
    останнього). Повертає Correction або None."""
    fix = forced(words[-1], cur, hkls, forced_words)
    if fix is not None:
        return fix
    typed_model = model(lang_of(cur))
    typed = [render(k, cur) for k in words]
    if typed_model is None or None in typed:
        return None
    best = None
    for hkl in _cycle_after(cur, hkls):
        conv_model = model(lang_of(hkl))
        conv = render(words[-1], hkl)
        if conv_model is None or conv is None:
            continue
        ok, confidence = is_better(typed[-1], typed_model, conv, conv_model, exceptions)
        if ok and (best is None or confidence > best[0]):
            best = confidence, hkl, conv_model
    if best is None:
        return None
    _, dst, conv_model = best
    # Попередні короткі слова («z» перед «ljvf») — лише якщо і вони стають словами
    first = len(words) - 1
    while first > 0:
        conv = render(words[first - 1], dst)
        if conv is None or not is_better(typed[first - 1], typed_model, conv, conv_model,
                                         exceptions, short=True)[0]:
            break
        first -= 1
    fixed = [render(k, dst) for k in words[first:]]
    start, end = word_bounds(typed[-1], fixed[-1])
    return Correction(cur, dst, " ".join(typed[first:]), " ".join(fixed), typed[-1][start:end].lower())


def _cycle_after(cur, hkls):
    """Інші розкладки в порядку перемикання після поточної."""
    i = hkls.index(cur) if cur in hkls else -1
    return [hkls[(i + j) % len(hkls)] for j in range(1, len(hkls)) if hkls[(i + j) % len(hkls)] != cur]


VK_BACK, VK_SPACE, VK_CAPITAL = 0x08, 0x20, 0x14
VK_NUMPAD0, VK_NUMPAD9 = 0x60, 0x69
_SHIFTS = {0xA0, 0xA1}
_CTRLS = {0xA2, 0xA3}
_LALT, _RALT = 0xA4, 0xA5
_WINS = {0x5B, 0x5C}
_MODIFIERS = _SHIFTS | _CTRLS | _WINS | {_LALT, _RALT}
_MAX_KEYS = 40           # довше — точно не слово (або щось вставлено)
_MAX_SHORT_KEYS = 3      # «коротке» слово для контексту: 1–2 літери + розділовий знак
_MAX_HISTORY = 3


class Tracker:
    """Стежить за натисканнями й пам'ятає клавіші поточного слова та кількох
    попередніх коротких. Будь-що, що могло зсунути курсор або змінити текст не
    так, як ми бачимо (стрілки, клік мишею, гарячі клавіші, вставлене програмами),
    скидає стан — тоді просто нічого не виправляється."""

    def __init__(self):
        self.mods = set()         # фізично утримувані модифікатори (ліві/праві окремо)
        self.caps = None          # Caps Lock: None — невідомо (стан задає програма, див. main)
        self._caps_held = False   # автоповтор утримуваного Caps Lock не перемикає його знову
        self.ignore_vks = set()   # клавіші гарячої клавіші розкладки — не скидають «скасування»
        self.correction = None    # остання виправлена фраза (поки її можна скасувати)
        self.appended = False     # остання подія додала клавішу до поточного слова
        self.reset()

    def reset(self):
        self.keys = []
        self.history = []         # клавіші попередніх коротких слів
        self.fg = self.hkl = None
        self.correction = None

    @property
    def active(self):
        return bool(self.keys or self.history or self.correction)

    def key(self, vk, down, injected, fg, hkl, own=False):
        """Одна подія клавіатури (vk — з уточненням лівий/правий; own — її надіслала
        сама програма). Повертає список клавіш слів, якщо щойно натиснуто пробіл
        після слова, інакше None."""
        self.appended = False
        if own:
            return None  # наші власні передруковування враховує той, хто їх надсилає
        if vk == VK_CAPITAL:
            # Перемикач Caps Lock стежимо сами: GetKeyState у нашому потоці не бачить
            # натискань в інших програмах, а Raw Input бачить кожне
            if down and not self._caps_held and self.caps is not None:
                self.caps = not self.caps
            self._caps_held = down
            return None
        if vk in _MODIFIERS:
            if not injected:
                (self.mods.add if down else self.mods.discard)(vk)
            return None
        if not down:
            return None
        if injected:
            self.reset()  # текст змінила інша програма — що в полі, вже невідомо
            return None
        altgr = _RALT in self.mods
        # Цифри з NumPad однакові в усіх розкладках (див. render). Shift+NumPad — це
        # стрілки, Home/End…: курсор міг зсунутися, тож такі клавіші скидають слово
        numpad = VK_NUMPAD0 <= vk <= VK_NUMPAD9 and not self.mods & _SHIFTS and not altgr
        shortcut = (self.mods & _CTRLS and not altgr) or _LALT in self.mods or self.mods & _WINS
        if shortcut or not numpad and vk not in layouts.TYPING_VKS | {VK_SPACE, VK_BACK}:
            if vk not in self.ignore_vks:
                self.reset()
            return None
        if fg != self.fg or hkl != self.hkl:
            self.reset()
            self.fg, self.hkl = fg, hkl
        self.correction = None
        if vk == VK_BACK:
            if self.keys:
                self.keys.pop()
            else:
                self.history = []  # стерли пробіл перед словом — ланцюжок слів розірвано
            return None
        if vk == VK_SPACE:
            if not self.keys:
                self.history = []
                return None
            words = self.history + [self.keys]
            self.keys = []
            return words
        if len(self.keys) >= _MAX_KEYS:
            self.reset()
            return None
        self.keys.append((vk, bool(self.mods & _SHIFTS), altgr, bool(self.caps)))
        self.appended = True
        return None

    def switched(self, hkl):
        """Слово передруковано посередині й розкладку перемкнено: набір триває в hkl."""
        self.hkl = hkl

    def finished(self, words, corrected):
        """Після пробілу: corrected — чи ці слова виправляються (тоді ланцюжок коротких
        слів на них закінчується). Що можна скасувати (correction), задає той, хто
        справді передрукував текст."""
        if not corrected and len(words[-1]) <= _MAX_SHORT_KEYS:
            self.history = words[-_MAX_HISTORY:]
        else:
            self.history = []

    def mouse_click(self):
        self.reset()

    def sync_mods(self, held):
        """Звірити модифікатори з фактичним станом: їхні події могли забрати інші
        читачі Raw Input (утримання гарячої клавіші), і без цього, напр., Ctrl
        «залип» би й кожне слово вважалося б комбінацією."""
        self.mods = set(held) & _MODIFIERS
